from decimal import Decimal
from collections import defaultdict

from django.db.models import Q

from config.choices import EstadoApuesta, TipoAlertaAbuso, EstadoBono, Direccion
from betting.models import Apuesta, ApuestaSeleccion, Seleccion
from panel.models import Bono, BonoApuesta, AlertaAbuso
from wallet.models import LedgerEntry


def detect_risk_free_betting(usuario, bono=None):
    """
    Detecta apuestas sin riesgo: usuario cubre todos los resultados de un mismo mercado
    garantizando ganancia independientemente del resultado.

    Retorna lista de alertas generadas.
    """
    if bono is None:
        bonos_activos = Bono.objects.filter(
            usuario=usuario,
            estado=EstadoBono.ACTIVO,
        )
    else:
        bonos_activos = [bono]

    alertas_generadas = []

    for bono_activo in bonos_activos:
        apuestas_bono = Apuesta.objects.filter(
            usuario=usuario,
            estado=EstadoApuesta.ACCEPTED,
        ).filter(
            Q(seleccion__isnull=False) | Q(selecciones__isnull=False)
        ).distinct()

        if not apuestas_bono.exists():
            continue

        cobertura_por_evento = defaultdict(list)

        for apuesta in apuestas_bono:
            if apuesta.tipo == "SIMPLE" and apuesta.seleccion:
                evento_id = apuesta.seleccion.mercado.evento_id
                mercado_id = apuesta.seleccion.mercado_id
                cobertura_por_evento[(evento_id, mercado_id)].append(apuesta)
            elif apuesta.tipo == "COMBINADA":
                detalles = apuesta.selecciones.select_related(
                    "seleccion__mercado"
                ).all()
                for det in detalles:
                    evento_id = det.seleccion.mercado.evento_id
                    mercado_id = det.seleccion.mercado_id
                    cobertura_por_evento[(evento_id, mercado_id)].append(apuesta)

        for (evento_id, mercado_id), apuestas_grupo in cobertura_por_evento.items():
            alertas = _analizar_cobertura(apuestas_grupo, bono_activo, usuario)
            alertas_generadas.extend(alertas)

    return alertas_generadas


def _analizar_cobertura(apuestas, bono, usuario):
    """
    Analiza si las apuestas en un mismo mercado cubren todos los resultados posibles.
    """
    alertas = []

    selecciones_cubiertas = set()
    total_apostado = Decimal("0.0000")
    payout_por_seleccion = {}

    for apuesta in apuestas:
        selecciones = []
        if apuesta.tipo == "SIMPLE" and apuesta.seleccion:
            selecciones = [apuesta.seleccion]
        elif apuesta.tipo == "COMBINADA":
            selecciones = [
                det.seleccion
                for det in apuesta.selecciones.select_related("seleccion").all()
            ]

        for sel in selecciones:
            selecciones_cubiertas.add(sel.id)
            payout_potencial = apuesta.monto * apuesta.cuota_fijada
            if sel.id not in payout_por_seleccion:
                payout_por_seleccion[sel.id] = Decimal("0.0000")
            payout_por_seleccion[sel.id] += payout_potencial

        total_apostado += apuesta.monto

    if not selecciones_cubiertas:
        return alertas

    mercado = None
    for apuesta in apuestas:
        if apuesta.tipo == "SIMPLE" and apuesta.seleccion:
            mercado = apuesta.seleccion.mercado
            break
        elif apuesta.tipo == "COMBINADA":
            primer_det = apuesta.selecciones.select_related("seleccion__mercado").first()
            if primer_det:
                mercado = primer_det.seleccion.mercado
                break

    if not mercado:
        return alertas

    total_selecciones = mercado.selecciones.filter(mercado__activo=True).count()

    if len(selecciones_cubiertas) >= total_selecciones and total_selecciones > 1:
        ganancia_minima = min(payout_por_seleccion.values()) - total_apostado

        umbral_abuso = bono.monto * Decimal("0.05")

        if ganancia_minima > umbral_abuso:
            alerta = AlertaAbuso.objects.create(
                usuario=usuario,
                bono=bono,
                tipo=TipoAlertaAbuso.RISK_FREE,
                detalle={
                    "evento_id": mercado.evento_id,
                    "mercado_id": mercado.id,
                    "mercado_nombre": mercado.nombre,
                    "selecciones_cubiertas": list(selecciones_cubiertas),
                    "total_apostado": str(total_apostado),
                    "ganancia_minima": str(ganancia_minima.quantize(Decimal("0.0001"))),
                    "payouts_por_seleccion": {
                        str(k): str(v.quantize(Decimal("0.0001")))
                        for k, v in payout_por_seleccion.items()
                    },
                },
            )
            alertas.append(alerta)

            bono.estado = EstadoBono.REVOCADO
            bono.save()

    return alertas


def detectar_arbitraje(usuario, bono=None):
    """
    Detecta arbitraje entre múltiples eventos/mercados donde el usuario
    garantiza ganancia combinando apuestas de cuotas altas y bajas.
    """
    if bono is None:
        bonos_activos = Bono.objects.filter(
            usuario=usuario,
            estado=EstadoBono.ACTIVO,
        )
    else:
        bonos_activos = [bono]

    alertas = []

    for bono_activo in bonos_activos:
        apuestas = Apuesta.objects.filter(
            usuario=usuario,
            estado=EstadoApuesta.ACCEPTED,
        ).distinct()

        if apuestas.count() < 2:
            continue

        suma_probabilidades = Decimal("0.0000")
        total_apostado = Decimal("0.0000")

        for apuesta in apuestas:
            cuota = apuesta.cuota_fijada
            if cuota > 0:
                probabilidad_implied = Decimal("1.0000") / cuota
                suma_probabilidades += probabilidad_implied
                total_apostado += apuesta.monto

        if suma_probabilidades < Decimal("1.0000"):
            ganancia_garantizada = (Decimal("1.0000") - suma_probabilidades) * total_apostado

            alerta = AlertaAbuso.objects.create(
                usuario=usuario,
                bono=bono_activo,
                tipo=TipoAlertaAbuso.ARBITRAGE,
                detalle={
                    "suma_probabilidades": str(suma_probabilidades.quantize(Decimal("0.0004"))),
                    "total_apostado": str(total_apostado.quantize(Decimal("0.0001"))),
                    "ganancia_garantizada": str(ganancia_garantizada.quantize(Decimal("0.0001"))),
                    "num_apuestas": apuestas.count(),
                },
            )
            alertas.append(alerta)

            bono_activo.estado = EstadoBono.REVOCADO
            bono_activo.save()

    return alertas


def detect_matched_betting(usuario, bono=None):
    """
    Detecta matched betting: el usuario financia apuestas con bono en un mercado
    y simultáneamente apuesta en contra con fondos reales en el mismo mercado,
    garantizando ganancia sin riesgo.
    """
    if bono is None:
        bonos_activos = Bono.objects.filter(
            usuario=usuario,
            estado=EstadoBono.ACTIVO,
        )
    else:
        bonos_activos = [bono]

    alertas = []

    for bono_activo in bonos_activos:
        apuestas_con_bono = Apuesta.objects.filter(
            usuario=usuario,
            usar_bono=True,
            estado=EstadoApuesta.ACCEPTED,
        )
        apuestas_sin_bono = Apuesta.objects.filter(
            usuario=usuario,
            usar_bono=False,
            estado=EstadoApuesta.ACCEPTED,
        )

        if not apuestas_con_bono.exists() or not apuestas_sin_bono.exists():
            continue

        selecciones_bono = _obtener_selecciones_ids(apuestas_con_bono)
        selecciones_sin_bono = _obtener_selecciones_ids(apuestas_sin_bono)

        for sel_bono_id in selecciones_bono:
            sel_bono = Seleccion.objects.select_related("mercado__evento").get(pk=sel_bono_id)
            mercado = sel_bono.mercado
            total_mercado = mercado.selecciones.count()

            selecciones_contrarias = set()
            for sel_sin_id in selecciones_sin_bono:
                sel_sin = Seleccion.objects.select_related("mercado__evento").get(pk=sel_sin_id)
                if sel_sin.mercado_id == mercado.id and sel_sin.id != sel_bono_id:
                    selecciones_contrarias.add(sel_sin_id)

            if len(selecciones_contrarias) + 1 >= total_mercado and total_mercado > 1:
                total_apostado_bono = sum(
                    a.monto for a in apuestas_con_bono
                    if _apuesta_tiene_seleccion(a, sel_bono_id)
                )
                total_apostado_sin_bono = sum(
                    a.monto for a in apuestas_sin_bono
                    if any(_apuesta_tiene_seleccion(a, sid) for sid in selecciones_contrarias)
                )

                payout_bono = sum(
                    a.monto * a.cuota_fijada for a in apuestas_con_bono
                    if _apuesta_tiene_seleccion(a, sel_bono_id)
                )

                ganancia_garantizada = payout_bono - total_apostado_bono - total_apostado_sin_bono

                if ganancia_garantizada > bono_activo.monto * Decimal("0.05"):
                    alerta = AlertaAbuso.objects.create(
                        usuario=usuario,
                        bono=bono_activo,
                        tipo=TipoAlertaAbuso.MATCHED_BETTING,
                        detalle={
                            "evento_id": mercado.evento_id,
                            "evento_nombre": f"{mercado.evento.local} vs {mercado.evento.visitante}",
                            "mercado_id": mercado.id,
                            "mercado_nombre": mercado.nombre,
                            "seleccion_bono_id": sel_bono_id,
                            "seleccion_bono_nombre": sel_bono.nombre,
                            "selecciones_contrarias": list(selecciones_contrarias),
                            "total_apostado_bono": str(total_apostado_bono.quantize(Decimal("0.0001"))),
                            "total_apostado_sin_bono": str(total_apostado_sin_bono.quantize(Decimal("0.0001"))),
                            "ganancia_garantizada": str(ganancia_garantizada.quantize(Decimal("0.0001"))),
                        },
                    )
                    alertas.append(alerta)

                    bono_activo.estado = EstadoBono.REVOCADO
                    bono_activo.save()
                    break

    return alertas


def _apuesta_tiene_seleccion(apuesta, seleccion_id):
    if apuesta.tipo == "SIMPLE" and apuesta.seleccion:
        return apuesta.seleccion_id == seleccion_id
    elif apuesta.tipo == "COMBINADA":
        return apuesta.selecciones.filter(seleccion_id=seleccion_id).exists()
    return False


def _obtener_selecciones_ids(apuestas):
    ids = set()
    for apuesta in apuestas:
        if apuesta.tipo == "SIMPLE" and apuesta.seleccion:
            ids.add(apuesta.seleccion_id)
        elif apuesta.tipo == "COMBINADA":
            for det in apuesta.selecciones.all():
                ids.add(det.seleccion_id)
    return ids


def run_abuse_check(usuario=None):
    """
    Ejecuta todas las detecciones de abuso.
    Si usuario es None, revisa todos los usuarios con bonos activos.
    """
    if usuario:
        usuarios_con_bono = [usuario]
    else:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        usuarios_con_bono = User.objects.filter(
            bonos__estado=EstadoBono.ACTIVO,
        ).distinct()

    todas_alertas = []

    for u in usuarios_con_bono:
        bonos_activos = Bono.objects.filter(usuario=u, estado=EstadoBono.ACTIVO)
        for bono in bonos_activos:
            todas_alertas.extend(detect_risk_free_betting(u, bono))
            todas_alertas.extend(detectar_arbitraje(u, bono))
            todas_alertas.extend(detect_matched_betting(u, bono))

    return todas_alertas
