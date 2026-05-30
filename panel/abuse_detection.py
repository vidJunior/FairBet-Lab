from decimal import Decimal
from collections import defaultdict

from django.db.models import Q

from config.choices import EstadoApuesta, TipoAlertaAbuso, EstadoBono
from betting.models import Apuesta, ApuestaSeleccion
from panel.models import Bono, BonoApuesta, AlertaAbuso


def detect_risk_free_betting(usuario, bono=None):
    """Detecta apuestas sin riesgo (cubre todos los resultados)."""
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


def _analizar_cobertura(bono, usuario):
    """Analiza cobertura de mercado."""
    alertas = []
    apuestas = Apuesta.objects.filter(
        usuario=usuario,
        usar_bono=True,
        estado=EstadoApuesta.ACCEPTED,
    ).prefetch_related(
        "selecciones__seleccion__mercado__selecciones"
    ).select_related("seleccion__mercado")

    if not apuestas.exists():
        return alertas

    from collections import defaultdict
    apuestas_por_mercado = defaultdict(list)

    for apuesta in apuestas:
        if apuesta.tipo == "SIMPLE" and apuesta.seleccion:
            apuestas_por_mercado[apuesta.seleccion.mercado].append(apuesta)
        elif apuesta.tipo == "COMBINADA":
            # Omitir combinadas por ahora
            pass

    for mercado, apuestas_mercado in apuestas_por_mercado.items():
        selecciones_cubiertas = set()
        payout_por_seleccion = {}
        total_apostado = Decimal("0.0000")

        for apuesta in apuestas_mercado:
            sel_id = apuesta.seleccion.id
            selecciones_cubiertas.add(sel_id)
            payout_potencial = apuesta.monto * apuesta.cuota_fijada
            if sel_id not in payout_por_seleccion:
                payout_por_seleccion[sel_id] = Decimal("0.0000")
            payout_por_seleccion[sel_id] += payout_potencial
            total_apostado += apuesta.monto

        total_selecciones = mercado.selecciones.filter(activo=True).count()

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
                break

    return alertas


def detectar_arbitraje(usuario, bono=None):
    """Detecta arbitraje matemático."""
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

        from collections import defaultdict
        apuestas_por_mercado = defaultdict(list)
        
        for apuesta in apuestas:
            if apuesta.tipo == "SIMPLE" and apuesta.seleccion:
                mercado_id = apuesta.seleccion.mercado_id
                apuestas_por_mercado[mercado_id].append(apuesta)

        for mercado_id, apuestas_mercado in apuestas_por_mercado.items():
            if len(apuestas_mercado) < 2:
                continue

            suma_probabilidades = Decimal("0.0000")
            total_apostado = Decimal("0.0000")

            for apuesta in apuestas_mercado:
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
                        "mercado_id": mercado_id,
                        "suma_probabilidades": str(suma_probabilidades.quantize(Decimal("0.0004"))),
                        "total_apostado": str(total_apostado.quantize(Decimal("0.0001"))),
                        "ganancia_garantizada": str(ganancia_garantizada.quantize(Decimal("0.0001"))),
                        "num_apuestas": len(apuestas_mercado),
                    },
                )
                alertas.append(alerta)

                bono_activo.estado = EstadoBono.REVOCADO
                bono_activo.save()
                break # Revocar una vez

    return alertas


def run_abuse_check(usuario=None):
    """Ejecuta todas las detecciones de abuso."""
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

    return todas_alertas
