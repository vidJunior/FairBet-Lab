import uuid
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from config.choices import TipoCuenta, EstadoPerfil, EstadoEvento, EstadoApuesta, EstadoBono
from wallet.models import LedgerEntry
from wallet.services import transferencia_interna, registrar_movimiento
from betting.models import Evento, Seleccion, Apuesta, ApuestaSeleccion, Mercado
from betting.tasks import reactivar_mercados_evento
from panel.rollover import actualizar_rollover_apuesta
from panel.models import Bono

def determinar_cuenta_destino(user, usar_bono):
    """
    Determina si las ganancias/reembolsos deben ir a bonos o dinero real.
    Si el bono fue revocado, las ganancias se confiscan (CASA).
    """
    if not usar_bono:
        return TipoCuenta.WALLET_USUARIO
        
    tiene_activo = Bono.objects.filter(usuario=user, estado=EstadoBono.ACTIVO).exists()
    if tiene_activo:
        return TipoCuenta.BONOS
        
    tiene_revocado = Bono.objects.filter(usuario=user, estado=EstadoBono.REVOCADO).exists()
    if tiene_revocado:
        return TipoCuenta.CASA
        
    return TipoCuenta.WALLET_USUARIO

def notificar_usuario_actualizacion(user_id):
    """Envía un evento WebSocket al usuario para actualizar su vista (billetera/apuestas)"""
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f"user_{user_id}",
        {"type": "user_update", "data": {"type": "WALLET_UPDATE", "msg": "Tus apuestas han sido liquidadas"}}
    )


def obtener_seleccion_ganadora_1x2(evento):
    mercado_1x2 = evento.mercados.filter(nombre="1X2").first()
    if not mercado_1x2:
        return None

    seleccion_local = mercado_1x2.selecciones.filter(nombre__icontains="local").first()
    seleccion_empate = mercado_1x2.selecciones.filter(
        nombre__icontains="empate"
    ).first()
    seleccion_visitante = mercado_1x2.selecciones.filter(
        nombre__icontains="visitante"
    ).first()

    # Fallback por orden de creación si no hay nombre reconocible
    selecciones = list(mercado_1x2.selecciones.all().order_by("id"))
    if len(selecciones) == 3:
        if not seleccion_local:
            seleccion_local = selecciones[0]
        if not seleccion_empate:
            seleccion_empate = selecciones[1]
        if not seleccion_visitante:
            seleccion_visitante = selecciones[2]

    if evento.goles_local > evento.goles_visitante:
        return seleccion_local
    elif evento.goles_local < evento.goles_visitante:
        return seleccion_visitante
    else:
        return seleccion_empate


def es_seleccion_ganadora(seleccion, evento):
    """Evalúa si una selección resultó ganadora según el marcador final."""
    goles_loc = evento.goles_local
    goles_vis = evento.goles_visitante
    total_goles = goles_loc + goles_vis

    mercado = seleccion.mercado.nombre.upper()
    sel_nombre = seleccion.nombre.upper()

    if mercado == "1X2":
        if goles_loc > goles_vis and "LOCAL" in sel_nombre:
            return True
        if goles_loc < goles_vis and "VISITANTE" in sel_nombre:
            return True
        if goles_loc == goles_vis and "EMPATE" in sel_nombre:
            return True
        return False

    elif "DOBLE OPORTUNIDAD" in mercado:
        if goles_loc >= goles_vis and "1X" in sel_nombre:
            return True
        if goles_loc <= goles_vis and "X2" in sel_nombre:
            return True
        if goles_loc != goles_vis and "12" in sel_nombre:
            return True
        return False

    elif "MÁS/MENOS 2.5" in mercado or "MAS/MENOS 2.5" in mercado:
        if total_goles > 2.5 and ("MÁS" in sel_nombre or "MAS" in sel_nombre):
            return True
        if total_goles < 2.5 and "MENOS" in sel_nombre:
            return True
        return False

    elif "AMBOS EQUIPOS ANOTAN" in mercado:
        anotan_ambos = goles_loc > 0 and goles_vis > 0
        if anotan_ambos and "SÍ" in sel_nombre:
            return True
        if anotan_ambos and "SI" in sel_nombre:
            return True  # Fallback sin tilde
        if not anotan_ambos and "NO" in sel_nombre:
            return True
        return False

    return False


@transaction.atomic
def crear_apuesta(user, seleccion_id, monto, cuota_esperada=None, usar_bono=False):
    monto = Decimal(str(monto))
    if monto <= Decimal("0.0000"):
        raise ValidationError("El monto de la apuesta debe ser mayor a cero.")

    if not hasattr(user, "perfil") or user.perfil is None:
        raise ValidationError("El usuario no tiene un perfil asociado.")

    perfil = user.perfil

    # select_for_update evita condiciones de carrera
    from accounts.models import PerfilUsuario

    perfil = PerfilUsuario.objects.select_for_update().get(pk=perfil.pk)

    if perfil.estado != EstadoPerfil.VERIFICADO:
        raise ValidationError(
            "La cuenta debe estar en estado verificado para realizar apuestas."
        )

    if perfil.esta_autoexcluido:
        raise ValidationError(
            "No se permiten apuestas de usuarios bajo autoexclusión activa."
        )

    try:
        seleccion = Seleccion.objects.select_related("mercado__evento").get(
            pk=seleccion_id
        )
    except Seleccion.DoesNotExist:
        raise ValidationError("La selección especificada no existe.")

    if not seleccion.mercado.activo:
        raise ValidationError(
            "El mercado se encuentra suspendido temporalmente por un evento en curso."
        )

    evento = seleccion.mercado.evento
    if evento.estado not in [EstadoEvento.PROGRAMADO, EstadoEvento.EN_VIVO]:
        raise ValidationError(
            "Solo se permite apostar en eventos programados o en vivo."
        )

    # Verificar que la cuota no haya cambiado desde que el usuario la vio
    if cuota_esperada is not None:
        cuota_esp_dec = Decimal(str(cuota_esperada))
        if seleccion.cuota != cuota_esp_dec:
            raise ValidationError(
                f"La cuota cambió de {cuota_esp_dec} a {seleccion.cuota}. Por favor, confirme la nueva cuota."
            )

    MIN_APUESTA = Decimal("0.5000")
    MAX_APUESTA = Decimal("5000.0000")
    if monto < MIN_APUESTA or monto > MAX_APUESTA:
        raise ValidationError(
            f"El monto debe estar entre {MIN_APUESTA} y {MAX_APUESTA} fichas."
        )

    cuenta_origen = TipoCuenta.BONOS if usar_bono else TipoCuenta.WALLET_USUARIO

    LedgerEntry.objects.select_for_update().filter(usuario=user, cuenta=cuenta_origen)
    saldo = LedgerEntry.get_balance(user, cuenta_origen)
    if saldo < monto:
        raise ValidationError(
            f"Saldo insuficiente. Saldo disponible en {'bono' if usar_bono else 'billetera'}: {saldo}, solicitado: {monto}."
        )

    # Mover fondos a cuenta de apuestas pendientes
    transferencia_interna(user, cuenta_origen, TipoCuenta.APUESTAS_PENDIENTES, monto)

    apuesta = Apuesta.objects.create(
        usuario=user,
        seleccion=seleccion,
        monto=monto,
        cuota_fijada=seleccion.cuota,
        estado=EstadoApuesta.ACCEPTED,
        tipo="SIMPLE",
        usar_bono=usar_bono,
    )

    ApuestaSeleccion.objects.create(
        apuesta=apuesta, seleccion=seleccion, cuota_fijada=seleccion.cuota
    )

    from panel.abuse_detection import run_abuse_check

    run_abuse_check(usuario=user)

    return apuesta


@transaction.atomic
def crear_apuesta_combinada(
    user, seleccion_ids, monto, cuotas_esperadas=None, usar_bono=False
):
    monto = Decimal(str(monto))
    if monto <= Decimal("0.0000"):
        raise ValidationError("El monto de la apuesta debe ser mayor a cero.")

    if not seleccion_ids or len(seleccion_ids) < 2:
        raise ValidationError(
            "Una apuesta combinada debe tener al menos 2 selecciones."
        )

    if not hasattr(user, "perfil") or user.perfil is None:
        raise ValidationError("El usuario no tiene un perfil asociado.")

    from accounts.models import PerfilUsuario

    perfil = PerfilUsuario.objects.select_for_update().get(pk=user.perfil.pk)

    if perfil.estado != EstadoPerfil.VERIFICADO:
        raise ValidationError(
            "La cuenta debe estar en estado verificado para realizar apuestas."
        )

    if perfil.esta_autoexcluido:
        raise ValidationError(
            "No se permiten apuestas de usuarios bajo autoexclusión activa."
        )

    selecciones = list(
        Seleccion.objects.filter(id__in=seleccion_ids).select_related("mercado__evento")
    )
    if len(selecciones) != len(seleccion_ids):
        raise ValidationError("Una o más selecciones especificadas no existen.")

    mercados_vistos = set()
    cuota_acumulada = Decimal("1.0000")

    for sel in selecciones:
        mercado_id = sel.mercado_id
        if mercado_id in mercados_vistos:
            raise ValidationError(
                "No se pueden combinar selecciones del mismo mercado en un solo ticket."
            )
        mercados_vistos.add(mercado_id)

        if sel.mercado.evento.estado not in [
            EstadoEvento.PROGRAMADO,
            EstadoEvento.EN_VIVO,
        ]:
            raise ValidationError(
                f"El evento de la seleccion {sel.nombre} no se encuentra programado o en vivo."
            )

        if not sel.mercado.activo:
            raise ValidationError(
                f"El mercado de la selección {sel.nombre} se encuentra suspendido."
            )

        if cuotas_esperadas is not None:
            sel_id_str = str(sel.id)
            sel_id_int = int(sel.id)
            expected = cuotas_esperadas.get(sel_id_str) or cuotas_esperadas.get(
                sel_id_int
            )
            if expected is not None:
                expected_dec = Decimal(str(expected))
                if sel.cuota != expected_dec:
                    raise ValidationError(
                        f"La cuota de {sel.nombre} cambió de {expected_dec} a {sel.cuota}. Reconfirme la apuesta."
                    )

        cuota_acumulada = (cuota_acumulada * sel.cuota).quantize(Decimal("0.0001"))

    MIN_APUESTA = Decimal("0.5000")
    MAX_APUESTA = Decimal("5000.0000")
    if monto < MIN_APUESTA or monto > MAX_APUESTA:
        raise ValidationError(
            f"El monto debe estar entre {MIN_APUESTA} y {MAX_APUESTA} fichas."
        )

    cuenta_origen = TipoCuenta.BONOS if usar_bono else TipoCuenta.WALLET_USUARIO
    LedgerEntry.objects.select_for_update().filter(usuario=user, cuenta=cuenta_origen)
    saldo = LedgerEntry.get_balance(user, cuenta_origen)
    if saldo < monto:
        raise ValidationError(
            f"Saldo insuficiente. Saldo disponible en {'bono' if usar_bono else 'billetera'}: {saldo}, solicitado: {monto}."
        )

    transferencia_interna(user, cuenta_origen, TipoCuenta.APUESTAS_PENDIENTES, monto)

    apuesta = Apuesta.objects.create(
        usuario=user,
        monto=monto,
        cuota_fijada=cuota_acumulada,
        estado=EstadoApuesta.ACCEPTED,
        tipo="COMBINADA",
        usar_bono=usar_bono,
    )

    for sel in selecciones:
        ApuestaSeleccion.objects.create(
            apuesta=apuesta, seleccion=sel, cuota_fijada=sel.cuota
        )

    from panel.abuse_detection import run_abuse_check

    run_abuse_check(usuario=user)

    return apuesta


FACTOR_CASA = Decimal("0.95")


def calcular_cashout(apuesta):
    if apuesta.estado != EstadoApuesta.ACCEPTED or apuesta.usar_bono:
        return Decimal("0.0000")

    if apuesta.tipo == "SIMPLE" and apuesta.seleccion:
        return _calcular_cashout_simple(apuesta)
    elif apuesta.tipo == "COMBINADA":
        return _calcular_cashout_combinada(apuesta)
    return Decimal("0.0000")


def _calcular_cashout_simple(apuesta):
    sel = apuesta.seleccion
    evento = sel.mercado.evento
    if evento.estado in (EstadoEvento.FINALIZADO, EstadoEvento.ANULADO):
        return Decimal("0.0000")

    cuota_original = apuesta.cuota_fijada
    cuota_actual = sel.cuota
    stake = apuesta.monto

    if cuota_original <= 0 or cuota_actual <= 0:
        return Decimal("0.0000")

    cashout = stake * cuota_original / cuota_actual * FACTOR_CASA
    return max(cashout, Decimal("0.0000")).quantize(Decimal("0.01"))


def _calcular_cashout_combinada(apuesta):
    detalles = apuesta.detalles.select_related("seleccion__mercado__evento")
    cuota_original_acum = apuesta.cuota_fijada
    cuota_actual_acum = Decimal("1.0000")

    for det in detalles:
        ev = det.seleccion.mercado.evento
        if ev.estado in (EstadoEvento.FINALIZADO, EstadoEvento.ANULADO):
            cuota_actual_acum *= Decimal("1.0000")
        else:
            cuota_actual_acum *= det.seleccion.cuota

    if cuota_original_acum <= 0 or cuota_actual_acum <= 0:
        return Decimal("0.0000")

    stake = apuesta.monto
    cashout = stake * cuota_original_acum / cuota_actual_acum * FACTOR_CASA
    return max(cashout, Decimal("0.0000")).quantize(Decimal("0.01"))


@transaction.atomic
def procesar_cashout(apuesta, user):
    from wallet.services import registrar_movimiento
    import uuid

    if apuesta.usuario != user:
        raise ValidationError("Esta apuesta no te pertenece.")
    if apuesta.estado != EstadoApuesta.ACCEPTED:
        raise ValidationError("Solo puedes retirar apuestas activas.")
    if apuesta.usar_bono:
        raise ValidationError("Las apuestas realizadas con bono no admiten Cash Out.")

    cashout = calcular_cashout(apuesta)
    if cashout <= 0:
        raise ValidationError(
            "El cashout no está disponible para esta apuesta en este momento."
        )

    monto_original = apuesta.monto
    tid = uuid.uuid4()
    registrar_movimiento(
        tid, user, TipoCuenta.APUESTAS_PENDIENTES, None, TipoCuenta.CASA, monto_original
    )
    cuenta_destino = (
        TipoCuenta.BONOS if apuesta.usar_bono else TipoCuenta.WALLET_USUARIO
    )
    registrar_movimiento(tid, None, TipoCuenta.CASA, user, cuenta_destino, cashout)

    apuesta.estado = EstadoApuesta.CASHED_OUT
    apuesta.save()

    return apuesta, cashout


@transaction.atomic
def crear_mercados_para_evento(evento):
    from decimal import Decimal

    mercado_1x2, _ = Mercado.objects.get_or_create(evento=evento, nombre="1X2")
    if mercado_1x2.selecciones.count() == 0:
        Seleccion.objects.create(
            mercado=mercado_1x2, nombre="Local", cuota=Decimal("2.0000")
        )
        Seleccion.objects.create(
            mercado=mercado_1x2, nombre="Empate", cuota=Decimal("3.5000")
        )
        Seleccion.objects.create(
            mercado=mercado_1x2, nombre="Visitante", cuota=Decimal("2.0000")
        )

    mercado_doble_op, _ = Mercado.objects.get_or_create(
        evento=evento, nombre="Doble Oportunidad"
    )
    if mercado_doble_op.selecciones.count() == 0:
        Seleccion.objects.create(
            mercado=mercado_doble_op, nombre="1X", cuota=Decimal("1.3000")
        )
        Seleccion.objects.create(
            mercado=mercado_doble_op, nombre="12", cuota=Decimal("1.2500")
        )
        Seleccion.objects.create(
            mercado=mercado_doble_op, nombre="X2", cuota=Decimal("1.3000")
        )

    mercado_myg, _ = Mercado.objects.get_or_create(
        evento=evento, nombre="Más/Menos 2.5"
    )
    if mercado_myg.selecciones.count() == 0:
        Seleccion.objects.create(
            mercado=mercado_myg, nombre="Más de 2.5", cuota=Decimal("1.9000")
        )
        Seleccion.objects.create(
            mercado=mercado_myg, nombre="Menos de 2.5", cuota=Decimal("1.9000")
        )

    mercado_btts, _ = Mercado.objects.get_or_create(
        evento=evento, nombre="Ambos Equipos Anotan"
    )
    if mercado_btts.selecciones.count() == 0:
        Seleccion.objects.create(
            mercado=mercado_btts, nombre="Sí", cuota=Decimal("2.0000")
        )
        Seleccion.objects.create(
            mercado=mercado_btts, nombre="No", cuota=Decimal("1.7500")
        )


@transaction.atomic
def liquidar_apuestas_evento(evento_id, seleccion_ganadora_id=None):
    try:
        evento = Evento.objects.get(pk=evento_id)
    except Evento.DoesNotExist:
        raise ValidationError("El evento no existe.")

    if evento.estado == EstadoEvento.FINALIZADO:
        raise ValidationError(
            "Este evento ya ha sido finalizado y liquidado previamente."
        )

    # --- Apuestas simples ---
    apuestas_simples = Apuesta.objects.filter(
        tipo="SIMPLE", seleccion__mercado__evento=evento, estado=EstadoApuesta.ACCEPTED
    ).select_related("usuario", "seleccion__mercado")

    usuarios_afectados = set()

    for apuesta in apuestas_simples:
        user = apuesta.usuario
        usuarios_afectados.add(user.id)
        stake = apuesta.monto

        LedgerEntry.objects.select_for_update().filter(
            usuario=user, cuenta=TipoCuenta.APUESTAS_PENDIENTES
        )

        if evento.estado == EstadoEvento.ANULADO:
            cuenta_destino = determinar_cuenta_destino(user, apuesta.usar_bono)
            if cuenta_destino != TipoCuenta.CASA:
                transferencia_interna(
                    user, TipoCuenta.APUESTAS_PENDIENTES, cuenta_destino, stake
                )
            apuesta.estado = EstadoApuesta.CANCELLED
            apuesta.save()
            continue

        if es_seleccion_ganadora(apuesta.seleccion, evento):
            payout = stake * apuesta.cuota_fijada
            tid = uuid.uuid4()
            registrar_movimiento(
                tid, user, TipoCuenta.APUESTAS_PENDIENTES, None, TipoCuenta.CASA, stake
            )
            cuenta_destino = determinar_cuenta_destino(user, apuesta.usar_bono)
            if cuenta_destino != TipoCuenta.CASA:
                registrar_movimiento(
                    tid, None, TipoCuenta.CASA, user, cuenta_destino, payout
                )
            apuesta.estado = EstadoApuesta.WON
            apuesta.save()
            actualizar_rollover_apuesta(apuesta)
        else:
            tid = uuid.uuid4()
            registrar_movimiento(
                tid, user, TipoCuenta.APUESTAS_PENDIENTES, None, TipoCuenta.CASA, stake
            )
            apuesta.estado = EstadoApuesta.LOST
            apuesta.save()
            actualizar_rollover_apuesta(apuesta)

    if evento.estado != EstadoEvento.ANULADO:
        evento.estado = EstadoEvento.FINALIZADO
    evento.save()
    evento.mercados.update(resuelto=True, activo=False)

    # --- Apuestas combinadas ---
    apuestas_combinadas = Apuesta.objects.filter(
        tipo="COMBINADA",
        selecciones__mercado__evento=evento,
        estado=EstadoApuesta.ACCEPTED,
    ).distinct()

    for combinada in apuestas_combinadas:
        user = combinada.usuario
        usuarios_afectados.add(user.id)
        detalles = combinada.detalles.select_related("seleccion__mercado__evento")

        estado_final = EstadoApuesta.WON
        cuota_ajustada = Decimal("1.0000")
        has_pending = False

        for det in detalles:
            ev_det = det.seleccion.mercado.evento

            if ev_det.estado in [
                EstadoEvento.PROGRAMADO,
                EstadoEvento.EN_VIVO,
                EstadoEvento.SUSPENDIDO,
            ]:
                has_pending = True
            elif ev_det.estado == EstadoEvento.ANULADO:
                pass  # cuota anulada = 1.00 (neutral)
            elif ev_det.estado == EstadoEvento.FINALIZADO:
                if es_seleccion_ganadora(det.seleccion, ev_det):
                    cuota_ajustada = (cuota_ajustada * det.cuota_fijada).quantize(
                        Decimal("0.0001")
                    )
                else:
                    estado_final = EstadoApuesta.LOST
                    break

        if estado_final == EstadoApuesta.LOST:
            LedgerEntry.objects.select_for_update().filter(
                usuario=user, cuenta=TipoCuenta.APUESTAS_PENDIENTES
            )
            tid = uuid.uuid4()
            registrar_movimiento(
                tid,
                user,
                TipoCuenta.APUESTAS_PENDIENTES,
                None,
                TipoCuenta.CASA,
                combinada.monto,
            )
            combinada.estado = EstadoApuesta.LOST
            combinada.save()
            actualizar_rollover_apuesta(combinada)

        elif not has_pending:  # todas resueltas y ninguna perdida: combinada ganadora
            LedgerEntry.objects.select_for_update().filter(
                usuario=user, cuenta=TipoCuenta.APUESTAS_PENDIENTES
            )
            payout = combinada.monto * cuota_ajustada
            tid = uuid.uuid4()
            registrar_movimiento(
                tid,
                user,
                TipoCuenta.APUESTAS_PENDIENTES,
                None,
                TipoCuenta.CASA,
                combinada.monto,
            )
            cuenta_destino = determinar_cuenta_destino(user, combinada.usar_bono)
            if cuenta_destino != TipoCuenta.CASA:
                registrar_movimiento(
                    tid, None, TipoCuenta.CASA, user, cuenta_destino, payout
                )
            combinada.estado = EstadoApuesta.WON
            combinada.cuota_fijada = cuota_ajustada
            combinada.save()
            actualizar_rollover_apuesta(combinada)

    def _notificar_usuarios():
        for uid in usuarios_afectados:
            notificar_usuario_actualizacion(uid)

    transaction.on_commit(_notificar_usuarios)


@transaction.atomic
def actualizar_cuota_seleccion(seleccion_id, nueva_cuota):
    nueva_cuota = Decimal(str(nueva_cuota))
    try:
        seleccion = Seleccion.objects.select_related("mercado__evento").get(
            pk=seleccion_id
        )
    except Seleccion.DoesNotExist:
        raise ValidationError("La selección no existe.")

    seleccion.cuota = nueva_cuota
    seleccion.save()

    # Notificar vía WebSocket
    channel_layer = get_channel_layer()
    if channel_layer:
        async_to_sync(channel_layer.group_send)(
            "live_odds",
            {
                "type": "odds_update",
                "data": {
                    "tipo_evento": "ODDS_UPDATE",
                    "seleccion_id": seleccion.id,
                    "mercado_id": seleccion.mercado_id,
                    "evento_id": seleccion.mercado.evento_id,
                    "nueva_cuota": str(nueva_cuota),
                },
            },
        )
    return seleccion


@transaction.atomic
def recalcular_cuotas_dinamicas(evento):
    """Recalcula cuotas de todos los mercados según minuto, marcador y variación aleatoria."""
    import random
    from decimal import Decimal
    from betting.models import Mercado, Seleccion

    MIN_CUOTA = Decimal("1.01")

    minuto = max(0, min(evento.minuto_actual, 90))
    m_factor = Decimal(str(minuto / 90.0))
    g_local = evento.goles_local
    g_visitante = evento.goles_visitante
    g_total = g_local + g_visitante
    diff = g_local - g_visitante

    margen = Decimal("1.08")  # 8% de margen de casa

    def prob_a_cuota(prob):
        if prob <= Decimal("0.0"):
            return Decimal("99.00")
        raw = (Decimal("1.0") / (prob * margen)).quantize(Decimal("0.01"))
        return max(MIN_CUOTA, min(raw, Decimal("99.00")))

    mercados_dict = {m.nombre: m for m in evento.mercados.all()}
    mercado_1x2 = mercados_dict.get("1X2")
    mercado_doble = mercados_dict.get("Doble Oportunidad")
    mercado_myg = mercados_dict.get("Más/Menos 2.5")
    mercado_btts = mercados_dict.get("Ambos Equipos Anotan")

    selecciones = list(
        Seleccion.objects.filter(mercado__evento=evento).select_related("mercado")
    )

    from collections import defaultdict

    selecciones_por_mercado = defaultdict(list)
    for sel in selecciones:
        selecciones_por_mercado[sel.mercado_id].append(sel)

    updated_selecciones = []
    updated_mercados = []

    p_local, p_empate, p_visitante = Decimal("0.33"), Decimal("0.33"), Decimal("0.33")

    # Mercado 1X2
    if mercado_1x2:
        if diff == 0:
            p_empate = Decimal("0.30") + Decimal("0.55") * m_factor
            random_offset = Decimal(str(random.uniform(-0.03, 0.03)))
            p_local = ((Decimal("1.0") - p_empate) / Decimal("2.0")) + random_offset
            p_visitante = Decimal("1.0") - p_empate - p_local
        elif diff > 0:  # local ganando
            p_local = Decimal("0.50") + Decimal("0.45") * m_factor * Decimal(
                str(min(diff, 3))
            )
            p_local += Decimal(str(random.uniform(-0.02, 0.02)))
            p_empate = (
                (Decimal("1.0") - p_local)
                * Decimal("0.70")
                * (Decimal("1.0") - m_factor)
            )
            p_visitante = Decimal("1.0") - p_local - p_empate
        else:  # visitante ganando
            p_visitante = Decimal("0.50") + Decimal("0.45") * m_factor * Decimal(
                str(min(-diff, 3))
            )
            p_visitante += Decimal(str(random.uniform(-0.02, 0.02)))
            p_empate = (
                (Decimal("1.0") - p_visitante)
                * Decimal("0.70")
                * (Decimal("1.0") - m_factor)
            )
            p_local = Decimal("1.0") - p_visitante - p_empate

        p_local = max(Decimal("0.02"), min(p_local, Decimal("0.96")))
        p_empate = max(Decimal("0.02"), min(p_empate, Decimal("0.96")))
        p_visitante = max(Decimal("0.02"), min(p_visitante, Decimal("0.96")))

        # Normalizar a 1 y convertir a cuotas
        p_sum = p_local + p_empate + p_visitante
        p_local /= p_sum
        p_empate /= p_sum
        p_visitante /= p_sum

        c_local = prob_a_cuota(p_local)
        c_empate = prob_a_cuota(p_empate)
        c_visitante = prob_a_cuota(p_visitante)

        for sel in selecciones_por_mercado[mercado_1x2.id]:
            nombre_lower = sel.nombre.lower()
            if "local" in nombre_lower:
                sel.cuota = c_local
            elif "empate" in nombre_lower:
                sel.cuota = c_empate
            elif "visitante" in nombre_lower:
                sel.cuota = c_visitante
            updated_selecciones.append(sel)

    # Mercado Doble Oportunidad (combinaciones de 1X2)
    if mercado_doble:
        p_1X = p_local + p_empate
        p_12 = p_local + p_visitante
        p_X2 = p_empate + p_visitante

        c_1X = prob_a_cuota(p_1X)
        c_12 = prob_a_cuota(p_12)
        c_X2 = prob_a_cuota(p_X2)

        for sel in selecciones_por_mercado[mercado_doble.id]:
            if sel.nombre == "1X":
                sel.cuota = c_1X
            elif sel.nombre == "12":
                sel.cuota = c_12
            elif sel.nombre == "X2":
                sel.cuota = c_X2
            updated_selecciones.append(sel)

    # Mercado Más/Menos 2.5
    if mercado_myg:
        if g_total >= 3:  # ya superado el umbral: mercado resuelto
            c_mas = MIN_CUOTA
            c_menos = Decimal("99.00")
            if not mercado_myg.resuelto:
                mercado_myg.resuelto = True
                mercado_myg.activo = False
                updated_mercados.append(mercado_myg)
        else:
            needed = 3 - g_total
            tiempo_restante = Decimal("1.0") - m_factor
            if needed == 3:
                p_mas = Decimal("0.45") * tiempo_restante
            elif needed == 2:
                p_mas = Decimal("0.55") * tiempo_restante
            else:
                p_mas = Decimal("0.70") * tiempo_restante

            p_mas = max(Decimal("0.03"), min(p_mas, Decimal("0.95")))
            p_menos = Decimal("1.0") - p_mas

            c_mas = prob_a_cuota(p_mas)
            c_menos = prob_a_cuota(p_menos)

        for sel in selecciones_por_mercado[mercado_myg.id]:
            if "más" in sel.nombre.lower():
                sel.cuota = c_mas
            elif "menos" in sel.nombre.lower():
                sel.cuota = c_menos
            updated_selecciones.append(sel)

    # Mercado Ambos Equipos Anotan
    if mercado_btts:
        if g_local > 0 and g_visitante > 0:  # ambos anotaron: resuelto
            c_si = MIN_CUOTA
            c_no = Decimal("99.00")
            if not mercado_btts.resuelto:
                mercado_btts.resuelto = True
                mercado_btts.activo = False
                updated_mercados.append(mercado_btts)
        else:
            tiempo_restante = Decimal("1.0") - m_factor
            if g_local == 0 and g_visitante == 0:
                p_si = Decimal("0.45") * tiempo_restante  # ninguno anotó aún
            else:
                p_si = Decimal("0.50") * tiempo_restante  # uno ya anotó, falta el otro

            p_si = max(Decimal("0.03"), min(p_si, Decimal("0.95")))
            p_no = Decimal("1.0") - p_si

            c_si = prob_a_cuota(p_si)
            c_no = prob_a_cuota(p_no)

        for sel in selecciones_por_mercado[mercado_btts.id]:
            if sel.nombre == "Sí":
                sel.cuota = c_si
            elif sel.nombre == "No":
                sel.cuota = c_no
            updated_selecciones.append(sel)

    # bulk_update para minimizar queries
    if updated_mercados:
        Mercado.objects.bulk_update(updated_mercados, ["resuelto", "activo"])
    if updated_selecciones:
        Seleccion.objects.bulk_update(updated_selecciones, ["cuota"])

    return {str(s.id): str(s.cuota) for s in selecciones}


@transaction.atomic
def liquidar_apuestas_resueltas_temprano(evento):
    """Liquida apuestas garantizadas (BTTS y Más/Menos) antes del final del partido."""
    goles_loc = evento.goles_local
    goles_vis = evento.goles_visitante
    total_goles = goles_loc + goles_vis

    selecciones_ganadas = []
    selecciones_perdidas = []

    if goles_loc > 0 and goles_vis > 0:
        selecciones_ganadas.extend(
            list(
                Seleccion.objects.filter(
                    mercado__evento=evento,
                    mercado__nombre__icontains="ambos equipos anotan",
                    nombre__in=["Sí", "SI"],
                )
            )
        )
        selecciones_perdidas.extend(
            list(
                Seleccion.objects.filter(
                    mercado__evento=evento,
                    mercado__nombre__icontains="ambos equipos anotan",
                    nombre__icontains="no",
                )
            )
        )

    if total_goles >= 3:
        selecciones_ganadas.extend(
            list(
                Seleccion.objects.filter(
                    mercado__evento=evento,
                    mercado__nombre__icontains="2.5",
                    nombre__icontains="2.5",
                ).exclude(nombre__icontains="menos")
            )
        )
        selecciones_perdidas.extend(
            list(
                Seleccion.objects.filter(
                    mercado__evento=evento,
                    mercado__nombre__icontains="2.5",
                    nombre__icontains="menos",
                )
            )
        )

    if not selecciones_ganadas and not selecciones_perdidas:
        return

    # Bloquear los mercados resueltos tempranamente
    mercados_ids = set()
    for s in selecciones_ganadas + selecciones_perdidas:
        mercados_ids.add(s.mercado_id)
    if mercados_ids:
        Mercado.objects.filter(id__in=mercados_ids).update(resuelto=True, activo=False)

    usuarios_afectados = set()

    # Simples
    for sel in selecciones_ganadas:
        apuestas = Apuesta.objects.filter(
            tipo="SIMPLE", seleccion=sel, estado=EstadoApuesta.ACCEPTED
        ).select_related("usuario")
        for apuesta in apuestas:
            user = apuesta.usuario
            usuarios_afectados.add(user.id)
            stake = apuesta.monto
            LedgerEntry.objects.select_for_update().filter(
                usuario=user, cuenta=TipoCuenta.APUESTAS_PENDIENTES
            )
            payout = stake * apuesta.cuota_fijada
            tid = uuid.uuid4()
            registrar_movimiento(
                tid, user, TipoCuenta.APUESTAS_PENDIENTES, None, TipoCuenta.CASA, stake
            )
            cuenta_destino = determinar_cuenta_destino(user, apuesta.usar_bono)
            if cuenta_destino != TipoCuenta.CASA:
                registrar_movimiento(
                    tid, None, TipoCuenta.CASA, user, cuenta_destino, payout
                )
            apuesta.estado = EstadoApuesta.WON
            apuesta.save()
            actualizar_rollover_apuesta(apuesta)

    for sel in selecciones_perdidas:
        apuestas = Apuesta.objects.filter(
            tipo="SIMPLE", seleccion=sel, estado=EstadoApuesta.ACCEPTED
        ).select_related("usuario")
        for apuesta in apuestas:
            user = apuesta.usuario
            usuarios_afectados.add(user.id)
            stake = apuesta.monto
            LedgerEntry.objects.select_for_update().filter(
                usuario=user, cuenta=TipoCuenta.APUESTAS_PENDIENTES
            )
            tid = uuid.uuid4()
            registrar_movimiento(
                tid, user, TipoCuenta.APUESTAS_PENDIENTES, None, TipoCuenta.CASA, stake
            )
            apuesta.estado = EstadoApuesta.LOST
            apuesta.save()
            actualizar_rollover_apuesta(apuesta)

    # Combinadas perdedoras
    for sel in selecciones_perdidas:
        combinadas = Apuesta.objects.filter(
            tipo="COMBINADA", selecciones=sel, estado=EstadoApuesta.ACCEPTED
        ).distinct()
        for combinada in combinadas:
            user = combinada.usuario
            usuarios_afectados.add(user.id)
            LedgerEntry.objects.select_for_update().filter(
                usuario=user, cuenta=TipoCuenta.APUESTAS_PENDIENTES
            )
            tid = uuid.uuid4()
            registrar_movimiento(
                tid,
                user,
                TipoCuenta.APUESTAS_PENDIENTES,
                None,
                TipoCuenta.CASA,
                combinada.monto,
            )
            combinada.estado = EstadoApuesta.LOST
            combinada.save()
            actualizar_rollover_apuesta(combinada)

    for uid in usuarios_afectados:
        notificar_usuario_actualizacion(uid)


@transaction.atomic
def recalcular_cuotas_por_goles(evento, goles_local_nuevos, goles_visitante_nuevos):
    if goles_local_nuevos <= 0 and goles_visitante_nuevos <= 0:
        return

    liquidar_apuestas_resueltas_temprano(evento)
    cuotas_data = recalcular_cuotas_dinamicas(evento)

    # Suspender mercados durante el recálculo
    Mercado.objects.filter(evento=evento).update(activo=False)

    # Notificar suspensión vía WebSocket
    channel_layer = get_channel_layer()
    if channel_layer:
        async_to_sync(channel_layer.group_send)(
            "live_odds",
            {
                "type": "odds_update",
                "data": {
                    "tipo_evento": "EVENTO_CRITICO",
                    "evento_id": evento.id,
                    "evento_critico": "GOLES_ACTUALIZADOS",
                    "goles_local": evento.goles_local,
                    "goles_visitante": evento.goles_visitante,
                    "estado_mercados": "SUSPENDIDOS",
                    "nuevas_cuotas": cuotas_data,
                },
            },
        )

    reactivar_mercados_evento.delay(evento.id)


@transaction.atomic
def registrar_evento_critico(evento_id, tipo_evento_critico):
    try:
        evento = Evento.objects.get(pk=evento_id)
    except Evento.DoesNotExist:
        raise ValidationError("El evento no existe.")

    if tipo_evento_critico == "GOL_LOCAL":
        evento.goles_local += 1
    elif tipo_evento_critico == "GOL_VISITANTE":
        evento.goles_visitante += 1

    evento.estado = EstadoEvento.EN_VIVO
    evento.save()  # dispara recalcular_cuotas_por_goles via Evento.save()

    return evento


@transaction.atomic
def crear_evento_operador(local, visitante, fecha_inicio):
    """Crea evento, equipos y mercado 1X2 inicial."""
    from betting.models import Equipo, Evento, Mercado, Seleccion
    from config.choices import EstadoEvento

    local_nombre = local.strip()
    visitante_nombre = visitante.strip()

    local_eq, _ = Equipo.objects.get_or_create(nombre=local_nombre)
    visitante_eq, _ = Equipo.objects.get_or_create(nombre=visitante_nombre)

    evento = Evento.objects.create(
        local=local_nombre,
        visitante=visitante_nombre,
        local_equipo=local_eq,
        visitante_equipo=visitante_eq,
        fecha_inicio=fecha_inicio,
        estado=EstadoEvento.PROGRAMADO,
    )

    mercado = Mercado.objects.create(evento=evento, nombre="1X2", activo=True)
    Seleccion.objects.create(mercado=mercado, nombre="Local", cuota=Decimal("2.0000"))
    Seleccion.objects.create(mercado=mercado, nombre="Empate", cuota=Decimal("3.2000"))
    Seleccion.objects.create(
        mercado=mercado, nombre="Visitante", cuota=Decimal("2.5000")
    )

    # Notificar al catálogo en tiempo real
    channel_layer = get_channel_layer()
    if channel_layer:
        async_to_sync(channel_layer.group_send)(
            "live_odds",
            {
                "type": "odds_update",
                "data": {
                    "tipo_evento": "CATALOGO_ACTUALIZADO",
                    "motivo": "EVENTO_CREADO",
                    "evento_id": evento.id,
                    "descripcion": f"{local_nombre} vs {visitante_nombre}",
                },
            },
        )

    return evento


@transaction.atomic
def actualizar_evento_operador(
    evento_id, goles_local, goles_visitante, estado, minuto_actual=0, periodo="1T", fecha_inicio=None
):
    """Actualiza marcador, minuto y estado; liquida apuestas si el evento finaliza o se anula."""
    from betting.models import Evento
    from config.choices import EstadoEvento

    try:
        evento = Evento.objects.select_for_update().get(pk=evento_id)
    except Evento.DoesNotExist:
        raise ValidationError("El evento no existe.")

    previo_estado = evento.estado

    evento.goles_local = int(goles_local)
    evento.goles_visitante = int(goles_visitante)

    if fecha_inicio is not None:
        evento.fecha_inicio = fecha_inicio

    # No marcar FINALIZADO antes de liquidar para evitar conflictos en validaciones
    if estado == EstadoEvento.FINALIZADO:
        evento.estado = previo_estado
        evento.minuto_actual = 90
        evento.periodo = "FINALIZADO"
    elif estado == EstadoEvento.PROGRAMADO:
        evento.estado = estado
        evento.minuto_actual = 0
        evento.periodo = "1T"
        evento.goles_local = 0
        evento.goles_visitante = 0
        # Resetear mercados si se vuelve a PROGRAMADO
        evento.mercados.update(resuelto=False, activo=True)
    else:
        evento.estado = estado
        evento.minuto_actual = int(minuto_actual) if minuto_actual is not None else 0
        evento.periodo = periodo
    evento.save()

    # Pagar apuestas de mercados resueltos tempranamente (BTTS, Más/Menos) si hubo goles
    if estado == EstadoEvento.EN_VIVO:
        liquidar_apuestas_resueltas_temprano(evento)

    # Broadcast marcador y cuotas actualizadas
    channel_layer = get_channel_layer()
    if channel_layer:
        periodo_display = (
            "Entretiempo"
            if evento.periodo == "ET"
            else f"{evento.minuto_actual}' - {evento.periodo}"
        )
        nuevas_cuotas = recalcular_cuotas_dinamicas(evento)
        
        # Enviar actualización de catálogo para refrescar los locks (candados) de los mercados
        async_to_sync(channel_layer.group_send)(
            "live_odds",
            {
                "type": "odds_update",
                "data": {
                    "tipo_evento": "CATALOGO_ACTUALIZADO",
                    "motivo": "ACTUALIZACION_OPERADOR",
                    "evento_id": evento.id,
                },
            },
        )
        
        async_to_sync(channel_layer.group_send)(
            "live_odds",
            {
                "type": "odds_update",
                "data": {
                    "tipo_evento": "EVENTO_TIEMPO",
                    "evento_id": evento.id,
                    "minuto_actual": evento.minuto_actual,
                    "periodo": evento.periodo,
                    "periodo_display": periodo_display,
                    "goles_local": evento.goles_local,
                    "goles_visitante": evento.goles_visitante,
                    "nuevas_cuotas": nuevas_cuotas,
                },
            },
        )

    if estado in [
        EstadoEvento.FINALIZADO,
        EstadoEvento.ANULADO,
    ] and previo_estado not in [EstadoEvento.FINALIZADO, EstadoEvento.ANULADO]:
        liquidar_apuestas_evento(evento_id)

    # Notificar cambio de pestaña en catálogo cuando cambia el estado relevante
    estados_que_cambian_pestana = [
        EstadoEvento.EN_VIVO,
        EstadoEvento.FINALIZADO,
        EstadoEvento.ANULADO,
    ]
    if estado != previo_estado and (
        estado in estados_que_cambian_pestana
        or previo_estado in estados_que_cambian_pestana
    ):
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                "live_odds",
                {
                    "type": "odds_update",
                    "data": {
                        "tipo_evento": "CATALOGO_ACTUALIZADO",
                        "motivo": "ESTADO_CAMBIADO",
                        "evento_id": evento_id,
                        "estado_anterior": previo_estado,
                        "estado_nuevo": estado,
                    },
                },
            )

    return Evento.objects.get(pk=evento_id)


@transaction.atomic
def crear_mercado_operador(evento_id, mercado_nombre, selecciones_datos):
    """Crea un mercado con sus selecciones para el evento dado."""
    from betting.models import Evento, Mercado, Seleccion

    try:
        evento = Evento.objects.get(pk=evento_id)
    except Evento.DoesNotExist:
        raise ValidationError("El evento no existe.")

    mercado_nombre = mercado_nombre.strip()
    if Mercado.objects.filter(evento=evento, nombre__iexact=mercado_nombre).exists():
        raise ValidationError(
            f"El mercado '{mercado_nombre}' ya existe para este evento."
        )

    mercado = Mercado.objects.create(evento=evento, nombre=mercado_nombre, activo=True)

    for sel in selecciones_datos:
        Seleccion.objects.create(
            mercado=mercado,
            nombre=sel["nombre"].strip(),
            cuota=Decimal(str(sel["cuota"])),
        )

    return mercado
