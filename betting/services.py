import uuid
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from config.choices import TipoCuenta, EstadoPerfil, EstadoEvento, EstadoApuesta
from wallet.models import LedgerEntry
from wallet.services import transferencia_interna, registrar_movimiento
from betting.models import Evento, Seleccion, Apuesta, ApuestaSeleccion, Mercado
from betting.tasks import reactivar_mercados_evento
from panel.rollover import actualizar_rollover_apuesta


def obtener_seleccion_ganadora_1x2(evento):
    mercado_1x2 = evento.mercados.filter(nombre="1X2").first()
    if not mercado_1x2:
        return None
        
    seleccion_local = mercado_1x2.selecciones.filter(nombre__icontains="local").first()
    seleccion_empate = mercado_1x2.selecciones.filter(nombre__icontains="empate").first()
    seleccion_visitante = mercado_1x2.selecciones.filter(nombre__icontains="visitante").first()

    # Fallback de seguridad por orden de creación (0: Local, 1: Empate, 2: Visitante)
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
    """
    Evalúa si una selección específica resultó ganadora en base al marcador final del evento.
    Soporta los mercados principales: 1X2, Doble Oportunidad, Más/Menos 2.5, Ambos Equipos Anotan.
    """
    goles_loc = evento.goles_local
    goles_vis = evento.goles_visitante
    total_goles = goles_loc + goles_vis

    mercado = seleccion.mercado.nombre.upper()
    sel_nombre = seleccion.nombre.upper()

    if mercado == "1X2":
        if goles_loc > goles_vis and "LOCAL" in sel_nombre: return True
        if goles_loc < goles_vis and "VISITANTE" in sel_nombre: return True
        if goles_loc == goles_vis and "EMPATE" in sel_nombre: return True
        return False

    elif "DOBLE OPORTUNIDAD" in mercado:
        if goles_loc >= goles_vis and "1X" in sel_nombre: return True
        if goles_loc <= goles_vis and "X2" in sel_nombre: return True
        if goles_loc != goles_vis and "12" in sel_nombre: return True
        return False

    elif "MÁS/MENOS 2.5" in mercado or "MAS/MENOS 2.5" in mercado:
        if total_goles > 2.5 and ("MÁS" in sel_nombre or "MAS" in sel_nombre): return True
        if total_goles < 2.5 and "MENOS" in sel_nombre: return True
        return False

    elif "AMBOS EQUIPOS ANOTAN" in mercado:
        anotan_ambos = (goles_loc > 0 and goles_vis > 0)
        if anotan_ambos and "SÍ" in sel_nombre: return True
        if anotan_ambos and "SI" in sel_nombre: return True # Fallback sin tilde
        if not anotan_ambos and "NO" in sel_nombre: return True
        return False

    return False


@transaction.atomic
def crear_apuesta(user, seleccion_id, monto, cuota_esperada=None):
    monto = Decimal(str(monto))
    if monto <= Decimal("0.0000"):
        raise ValidationError("El monto de la apuesta debe ser mayor a cero.")

    if not hasattr(user, "perfil") or user.perfil is None:
        raise ValidationError("El usuario no tiene un perfil asociado.")
    
    perfil = user.perfil

    # Bloquear perfil para evitar doble proceso o condiciones de carrera
    from accounts.models import PerfilUsuario
    perfil = PerfilUsuario.objects.select_for_update().get(pk=perfil.pk)

    if perfil.estado != EstadoPerfil.VERIFICADO:
        raise ValidationError("La cuenta debe estar en estado verificado para realizar apuestas.")
    
    if perfil.esta_autoexcluido:
        raise ValidationError("No se permiten apuestas de usuarios bajo autoexclusión activa.")

    try:
        seleccion = Seleccion.objects.select_related("mercado__evento").get(pk=seleccion_id)
    except Seleccion.DoesNotExist:
        raise ValidationError("La selección especificada no existe.")

    # Validar si el mercado está activo (no suspendido por evento crítico)
    if not seleccion.mercado.activo:
        raise ValidationError("El mercado se encuentra suspendido temporalmente por un evento en curso.")

    evento = seleccion.mercado.evento
    # Nivel 2: Permitimos apuestas en vivo si el evento está EN_VIVO o PROGRAMADO
    if evento.estado not in [EstadoEvento.PROGRAMADO, EstadoEvento.EN_VIVO]:
        raise ValidationError("Solo se permite apostar en eventos programados o en vivo.")

    # Política de Re-cotización (Odds Changed Verification)
    if cuota_esperada is not None:
        cuota_esp_dec = Decimal(str(cuota_esperada))
        if seleccion.cuota != cuota_esp_dec:
            raise ValidationError(
                f"La cuota cambió de {cuota_esp_dec} a {seleccion.cuota}. Por favor, confirme la nueva cuota."
            )

    MIN_APUESTA = Decimal("0.5000")
    MAX_APUESTA = Decimal("5000.0000")
    if monto < MIN_APUESTA or monto > MAX_APUESTA:
        raise ValidationError(f"El monto debe estar entre {MIN_APUESTA} y {MAX_APUESTA} fichas.")

    # Validar saldo con select_for_update
    LedgerEntry.objects.select_for_update().filter(usuario=user, cuenta=TipoCuenta.WALLET_USUARIO)
    saldo = LedgerEntry.get_balance(user, TipoCuenta.WALLET_USUARIO)
    if saldo < monto:
        raise ValidationError(f"Saldo insuficiente. Saldo disponible: {saldo}, solicitado: {monto}.")

    # Retener saldo del usuario a apuestas pendientes
    transferencia_interna(user, TipoCuenta.WALLET_USUARIO, TipoCuenta.APUESTAS_PENDIENTES, monto)

    apuesta = Apuesta.objects.create(
        usuario=user,
        seleccion=seleccion,
        monto=monto,
        cuota_fijada=seleccion.cuota,
        estado=EstadoApuesta.ACCEPTED,
        tipo="SIMPLE"
    )
    
    # También agregar a la relación ManyToMany para consistencia
    ApuestaSeleccion.objects.create(
        apuesta=apuesta,
        seleccion=seleccion,
        cuota_fijada=seleccion.cuota
    )

    return apuesta


@transaction.atomic
def crear_apuesta_combinada(user, seleccion_ids, monto, cuotas_esperadas=None):
    monto = Decimal(str(monto))
    if monto <= Decimal("0.0000"):
        raise ValidationError("El monto de la apuesta debe ser mayor a cero.")

    if not seleccion_ids or len(seleccion_ids) < 2:
        raise ValidationError("Una apuesta combinada debe tener al menos 2 selecciones.")

    if not hasattr(user, "perfil") or user.perfil is None:
        raise ValidationError("El usuario no tiene un perfil asociado.")

    from accounts.models import PerfilUsuario
    perfil = PerfilUsuario.objects.select_for_update().get(pk=user.perfil.pk)

    if perfil.estado != EstadoPerfil.VERIFICADO:
        raise ValidationError("La cuenta debe estar en estado verificado para realizar apuestas.")
    
    if perfil.esta_autoexcluido:
        raise ValidationError("No se permiten apuestas de usuarios bajo autoexclusión activa.")

    # Obtener y bloquear selecciones
    selecciones = list(Seleccion.objects.filter(id__in=seleccion_ids).select_related("mercado__evento"))
    if len(selecciones) != len(seleccion_ids):
        raise ValidationError("Una o más selecciones especificadas no existen.")

    mercados_vistos = set()
    cuota_acumulada = Decimal("1.0000")

    for sel in selecciones:
        # Validación de exclusión mutua
        mercado_id = sel.mercado_id
        if mercado_id in mercados_vistos:
            raise ValidationError("No se pueden combinar selecciones del mismo mercado en un solo ticket.")
        mercados_vistos.add(mercado_id)

        # Validar estado del evento
        if sel.mercado.evento.estado not in [EstadoEvento.PROGRAMADO, EstadoEvento.EN_VIVO]:
            raise ValidationError(f"El evento de la seleccion {sel.nombre} no se encuentra programado o en vivo.")

        # Validar si el mercado está suspendido
        if not sel.mercado.activo:
            raise ValidationError(f"El mercado de la selección {sel.nombre} se encuentra suspendido.")

        # Re-cotización individual
        if cuotas_esperadas is not None:
            # cuotas_esperadas puede ser dict {id: cuota} o {str(id): cuota}
            sel_id_str = str(sel.id)
            sel_id_int = int(sel.id)
            expected = cuotas_esperadas.get(sel_id_str) or cuotas_esperadas.get(sel_id_int)
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
        raise ValidationError(f"El monto debe estar entre {MIN_APUESTA} y {MAX_APUESTA} fichas.")

    # Validar saldo con select_for_update
    LedgerEntry.objects.select_for_update().filter(usuario=user, cuenta=TipoCuenta.WALLET_USUARIO)
    saldo = LedgerEntry.get_balance(user, TipoCuenta.WALLET_USUARIO)
    if saldo < monto:
        raise ValidationError(f"Saldo insuficiente. Saldo disponible: {saldo}, solicitado: {monto}.")

    # Retener saldo del usuario a apuestas pendientes
    transferencia_interna(user, TipoCuenta.WALLET_USUARIO, TipoCuenta.APUESTAS_PENDIENTES, monto)

    # Crear Apuesta combinada
    apuesta = Apuesta.objects.create(
        usuario=user,
        monto=monto,
        cuota_fijada=cuota_acumulada,
        estado=EstadoApuesta.ACCEPTED,
        tipo="COMBINADA"
    )

    # Crear los detalles
    for sel in selecciones:
        ApuestaSeleccion.objects.create(
            apuesta=apuesta,
            seleccion=sel,
            cuota_fijada=sel.cuota
        )

    return apuesta


FACTOR_CASA = Decimal("0.95")


def calcular_cashout(apuesta):
    if apuesta.estado != EstadoApuesta.ACCEPTED:
        return Decimal("0.0000")

    from decimal import Decimal

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

    cashout = calcular_cashout(apuesta)
    if cashout <= 0:
        raise ValidationError("El cashout no está disponible para esta apuesta en este momento.")

    monto_original = apuesta.monto
    tid = uuid.uuid4()
    registrar_movimiento(tid, user, TipoCuenta.APUESTAS_PENDIENTES, None, TipoCuenta.CASA, monto_original)
    registrar_movimiento(tid, None, TipoCuenta.CASA, user, TipoCuenta.WALLET_USUARIO, cashout)

    apuesta.estado = EstadoApuesta.CASHED_OUT
    apuesta.save()

    return apuesta, cashout


@transaction.atomic
def crear_mercados_para_evento(evento):
    from decimal import Decimal

    mercado_1x2, _ = Mercado.objects.get_or_create(evento=evento, nombre="1X2")
    if mercado_1x2.selecciones.count() == 0:
        Seleccion.objects.create(mercado=mercado_1x2, nombre="Local", cuota=Decimal("2.0000"))
        Seleccion.objects.create(mercado=mercado_1x2, nombre="Empate", cuota=Decimal("3.5000"))
        Seleccion.objects.create(mercado=mercado_1x2, nombre="Visitante", cuota=Decimal("2.0000"))

    mercado_doble_op, _ = Mercado.objects.get_or_create(evento=evento, nombre="Doble Oportunidad")
    if mercado_doble_op.selecciones.count() == 0:
        Seleccion.objects.create(mercado=mercado_doble_op, nombre="1X", cuota=Decimal("1.3000"))
        Seleccion.objects.create(mercado=mercado_doble_op, nombre="12", cuota=Decimal("1.2500"))
        Seleccion.objects.create(mercado=mercado_doble_op, nombre="X2", cuota=Decimal("1.3000"))

    mercado_myg, _ = Mercado.objects.get_or_create(evento=evento, nombre="Más/Menos 2.5")
    if mercado_myg.selecciones.count() == 0:
        Seleccion.objects.create(mercado=mercado_myg, nombre="Más de 2.5", cuota=Decimal("1.9000"))
        Seleccion.objects.create(mercado=mercado_myg, nombre="Menos de 2.5", cuota=Decimal("1.9000"))

    mercado_btts, _ = Mercado.objects.get_or_create(evento=evento, nombre="Ambos Equipos Anotan")
    if mercado_btts.selecciones.count() == 0:
        Seleccion.objects.create(mercado=mercado_btts, nombre="Sí", cuota=Decimal("2.0000"))
        Seleccion.objects.create(mercado=mercado_btts, nombre="No", cuota=Decimal("1.7500"))


@transaction.atomic
def liquidar_apuestas_evento(evento_id, seleccion_ganadora_id=None):
    try:
        evento = Evento.objects.get(pk=evento_id)
    except Evento.DoesNotExist:
        raise ValidationError("El evento no existe.")

    if evento.estado == EstadoEvento.FINALIZADO:
        raise ValidationError("Este evento ya ha sido finalizado y liquidado previamente.")

    # 1. LIQUIDAR APUESTAS SIMPLES
    apuestas_simples = Apuesta.objects.filter(
        tipo="SIMPLE",
        seleccion__mercado__evento=evento,
        estado=EstadoApuesta.ACCEPTED
    ).select_related("usuario", "seleccion__mercado")

    for apuesta in apuestas_simples:
        user = apuesta.usuario
        stake = apuesta.monto

        LedgerEntry.objects.select_for_update().filter(usuario=user, cuenta=TipoCuenta.APUESTAS_PENDIENTES)

        if evento.estado == EstadoEvento.ANULADO:
            # Reembolso íntegro
            transferencia_interna(user, TipoCuenta.APUESTAS_PENDIENTES, TipoCuenta.WALLET_USUARIO, stake)
            apuesta.estado = EstadoApuesta.CANCELLED
            apuesta.save()
            continue

        if es_seleccion_ganadora(apuesta.seleccion, evento):
            payout = stake * apuesta.cuota_fijada
            tid = uuid.uuid4()
            registrar_movimiento(tid, user, TipoCuenta.APUESTAS_PENDIENTES, None, TipoCuenta.CASA, stake)
            registrar_movimiento(tid, None, TipoCuenta.CASA, user, TipoCuenta.WALLET_USUARIO, payout)
            apuesta.estado = EstadoApuesta.WON
            apuesta.save()
            actualizar_rollover_apuesta(apuesta)
        else:
            tid = uuid.uuid4()
            registrar_movimiento(tid, user, TipoCuenta.APUESTAS_PENDIENTES, None, TipoCuenta.CASA, stake)
            apuesta.estado = EstadoApuesta.LOST
            apuesta.save()
            actualizar_rollover_apuesta(apuesta)

    # Cambiar el estado del evento antes de evaluar las combinadas
    # para que las consultas y validaciones detecten el estado actualizado
    if evento.estado != EstadoEvento.ANULADO:
        evento.estado = EstadoEvento.FINALIZADO
    evento.save()

    # 2. EVALUAR Y LIQUIDAR APUESTAS COMBINADAS
    apuestas_combinadas = Apuesta.objects.filter(
        tipo="COMBINADA",
        selecciones__mercado__evento=evento,
        estado=EstadoApuesta.ACCEPTED
    ).distinct()

    for combinada in apuestas_combinadas:
        user = combinada.usuario
        detalles = combinada.detalles.select_related("seleccion__mercado__evento")
        
        estado_final = EstadoApuesta.WON # Suposición inicial
        cuota_ajustada = Decimal("1.0000")
        has_pending = False
        
        for det in detalles:
            ev_det = det.seleccion.mercado.evento
            
            if ev_det.estado in [EstadoEvento.PROGRAMADO, EstadoEvento.EN_VIVO, EstadoEvento.SUSPENDIDO]:
                has_pending = True
            elif ev_det.estado == EstadoEvento.ANULADO:
                # La cuota de esta seleccion anulada pasa a ser 1.00
                pass
            elif ev_det.estado == EstadoEvento.FINALIZADO:
                # Calcular ganador
                if es_seleccion_ganadora(det.seleccion, ev_det):
                    cuota_ajustada = (cuota_ajustada * det.cuota_fijada).quantize(Decimal("0.0001"))
                else:
                    estado_final = EstadoApuesta.LOST
                    break

        # Si se perdió una selección, toda la combinada se pierde
        if estado_final == EstadoApuesta.LOST:
            LedgerEntry.objects.select_for_update().filter(usuario=user, cuenta=TipoCuenta.APUESTAS_PENDIENTES)
            tid = uuid.uuid4()
            registrar_movimiento(tid, user, TipoCuenta.APUESTAS_PENDIENTES, None, TipoCuenta.CASA, combinada.monto)
            combinada.estado = EstadoApuesta.LOST
            combinada.save()
            actualizar_rollover_apuesta(combinada)
            
        elif not has_pending:
            # Si no quedan partidos pendientes y no se ha perdido ninguno: combinada ganadora
            LedgerEntry.objects.select_for_update().filter(usuario=user, cuenta=TipoCuenta.APUESTAS_PENDIENTES)
            payout = combinada.monto * cuota_ajustada
            tid = uuid.uuid4()
            registrar_movimiento(tid, user, TipoCuenta.APUESTAS_PENDIENTES, None, TipoCuenta.CASA, combinada.monto)
            registrar_movimiento(tid, None, TipoCuenta.CASA, user, TipoCuenta.WALLET_USUARIO, payout)
            combinada.estado = EstadoApuesta.WON
            combinada.cuota_fijada = cuota_ajustada
            combinada.save()
            actualizar_rollover_apuesta(combinada)



@transaction.atomic
def actualizar_cuota_seleccion(seleccion_id, nueva_cuota):
    nueva_cuota = Decimal(str(nueva_cuota))
    try:
        seleccion = Seleccion.objects.select_related("mercado__evento").get(pk=seleccion_id)
    except Seleccion.DoesNotExist:
        raise ValidationError("La selección no existe.")

    seleccion.cuota = nueva_cuota
    seleccion.save()

    # Transmitir a Django Channels
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
                    "nueva_cuota": str(nueva_cuota)
                }
            }
        )
    return seleccion


@transaction.atomic
def recalcular_cuotas_dinamicas(evento):
    """
    Recalcula las cuotas de TODOS los mercados del evento basándose en:
    1. El minuto actual del partido.
    2. El marcador de goles actual.
    3. Una leve fluctuación aleatoria para simular la presión/estadísticas del en vivo.
    Sigue la lógica de casas de apuestas reales (ej. Betano):
    - Cuota mínima siempre >= 1.01
    - Mercados resueltos se bloquean permanentemente
    """
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

    # Margen de ganancia de la casa/operador (sobre las cuotas)
    margen = Decimal("1.08")  # 8% de margen

    def prob_a_cuota(prob):
        """Convierte probabilidad a cuota decimal con margen de casa. Mínimo 1.01."""
        if prob <= Decimal("0.0"):
            return Decimal("99.00")
        raw = (Decimal("1.0") / (prob * margen)).quantize(Decimal("0.01"))
        return max(MIN_CUOTA, min(raw, Decimal("99.00")))

    # 1. MERCADO: 1X2
    mercado_1x2 = evento.mercados.filter(nombre="1X2").first()
    p_local, p_empate, p_visitante = Decimal("0.33"), Decimal("0.33"), Decimal("0.33")
    if mercado_1x2:
        # Probabilidades implícitas base según el marcador y el minuto
        if diff == 0:
            # Empate: a más minuto, más probable que se mantenga el empate
            p_empate = Decimal("0.30") + Decimal("0.55") * m_factor
            # Añadir pequeña variación aleatoria por posesión/remates (+/- 3%)
            random_offset = Decimal(str(random.uniform(-0.03, 0.03)))
            p_local = ((Decimal("1.0") - p_empate) / Decimal("2.0")) + random_offset
            p_visitante = Decimal("1.0") - p_empate - p_local
        elif diff > 0:
            # Local ganando
            p_local = Decimal("0.50") + Decimal("0.45") * m_factor * Decimal(str(min(diff, 3)))
            random_offset = Decimal(str(random.uniform(-0.02, 0.02)))
            p_local += random_offset
            p_empate = (Decimal("1.0") - p_local) * Decimal("0.70") * (Decimal("1.0") - m_factor)
            p_visitante = Decimal("1.0") - p_local - p_empate
        else:
            # Visitante ganando
            p_visitante = Decimal("0.50") + Decimal("0.45") * m_factor * Decimal(str(min(-diff, 3)))
            random_offset = Decimal(str(random.uniform(-0.02, 0.02)))
            p_visitante += random_offset
            p_empate = (Decimal("1.0") - p_visitante) * Decimal("0.70") * (Decimal("1.0") - m_factor)
            p_local = Decimal("1.0") - p_visitante - p_empate

        # Asegurar límites razonables
        p_local = max(Decimal("0.02"), min(p_local, Decimal("0.96")))
        p_empate = max(Decimal("0.02"), min(p_empate, Decimal("0.96")))
        p_visitante = max(Decimal("0.02"), min(p_visitante, Decimal("0.96")))

        # Normalizar probabilidades a 1
        p_sum = p_local + p_empate + p_visitante
        p_local /= p_sum
        p_empate /= p_sum
        p_visitante /= p_sum

        # Aplicar margen y calcular cuotas
        c_local = prob_a_cuota(p_local)
        c_empate = prob_a_cuota(p_empate)
        c_visitante = prob_a_cuota(p_visitante)

        # Guardar cuotas del 1X2
        for sel in mercado_1x2.selecciones.all():
            nombre_lower = sel.nombre.lower()
            if "local" in nombre_lower:
                sel.cuota = c_local
            elif "empate" in nombre_lower:
                sel.cuota = c_empate
            elif "visitante" in nombre_lower:
                sel.cuota = c_visitante
            sel.save()

    # 2. MERCADO: Doble Oportunidad
    mercado_doble = evento.mercados.filter(nombre="Doble Oportunidad").first()
    if mercado_doble:
        # 1X = Local o Empate
        p_1X = p_local + p_empate
        # 12 = Local o Visitante
        p_12 = p_local + p_visitante
        # X2 = Empate o Visitante
        p_X2 = p_empate + p_visitante

        c_1X = prob_a_cuota(p_1X)
        c_12 = prob_a_cuota(p_12)
        c_X2 = prob_a_cuota(p_X2)

        for sel in mercado_doble.selecciones.all():
            if sel.nombre == "1X":
                sel.cuota = c_1X
            elif sel.nombre == "12":
                sel.cuota = c_12
            elif sel.nombre == "X2":
                sel.cuota = c_X2
            sel.save()

    # 3. MERCADO: Más/Menos 2.5
    mercado_myg = evento.mercados.filter(nombre="Más/Menos 2.5").first()
    if mercado_myg:
        if g_total >= 3:
            c_mas = MIN_CUOTA
            c_menos = Decimal("99.00")
            if not mercado_myg.resuelto:
                mercado_myg.resuelto = True
                mercado_myg.activo = False
                mercado_myg.save()
        else:
            needed = 3 - g_total
            # Probabilidad de que se marquen más goles basada en el tiempo restante
            tiempo_restante = Decimal("1.0") - m_factor
            if needed == 3:
                # Faltan 3 goles: probabilidad baja, disminuye con el tiempo
                p_mas = Decimal("0.45") * tiempo_restante
            elif needed == 2:
                # Faltan 2 goles: probabilidad media
                p_mas = Decimal("0.55") * tiempo_restante
            else:
                # Falta 1 gol: probabilidad alta
                p_mas = Decimal("0.70") * tiempo_restante

            # Un gol más es bastante probable al inicio, pero se reduce con el tiempo
            p_mas = max(Decimal("0.03"), min(p_mas, Decimal("0.95")))
            p_menos = Decimal("1.0") - p_mas

            c_mas = prob_a_cuota(p_mas)
            c_menos = prob_a_cuota(p_menos)

        for sel in mercado_myg.selecciones.all():
            if "más" in sel.nombre.lower():
                sel.cuota = c_mas
            elif "menos" in sel.nombre.lower():
                sel.cuota = c_menos
            sel.save()

    # 4. MERCADO: Ambos Equipos Anotan
    mercado_btts = evento.mercados.filter(nombre="Ambos Equipos Anotan").first()
    if mercado_btts:
        if g_local > 0 and g_visitante > 0:
            c_si = MIN_CUOTA
            c_no = Decimal("99.00")
            if not mercado_btts.resuelto:
                mercado_btts.resuelto = True
                mercado_btts.activo = False
                mercado_btts.save()
        else:
            tiempo_restante = Decimal("1.0") - m_factor
            if g_local == 0 and g_visitante == 0:
                # Ninguno ha anotado: necesitan ambos anotar
                p_si = Decimal("0.45") * tiempo_restante
            else:
                # Uno ya anotó, falta el otro
                p_si = Decimal("0.50") * tiempo_restante

            p_si = max(Decimal("0.03"), min(p_si, Decimal("0.95")))
            p_no = Decimal("1.0") - p_si

            c_si = prob_a_cuota(p_si)
            c_no = prob_a_cuota(p_no)

        for sel in mercado_btts.selecciones.all():
            if sel.nombre == "Sí":
                sel.cuota = c_si
            elif sel.nombre == "No":
                sel.cuota = c_no
            sel.save()

    todas_selecciones = Seleccion.objects.filter(mercado__evento=evento)
    return {str(s.id): str(s.cuota) for s in todas_selecciones}


@transaction.atomic
def liquidar_apuestas_resueltas_temprano(evento):
    """
    Liquida apuestas simples y combinadas que ya están matemáticamente garantizadas (ganadas o perdidas)
    antes de que termine el evento.
    """
    goles_loc = evento.goles_local
    goles_vis = evento.goles_visitante
    total_goles = goles_loc + goles_vis

    selecciones_ganadas = []
    selecciones_perdidas = []

    if goles_loc > 0 and goles_vis > 0:
        selecciones_ganadas.extend(list(Seleccion.objects.filter(mercado__evento=evento, mercado__nombre__icontains="ambos equipos anotan", nombre__in=["Sí", "SI"])))
        selecciones_perdidas.extend(list(Seleccion.objects.filter(mercado__evento=evento, mercado__nombre__icontains="ambos equipos anotan", nombre__icontains="no")))

    if total_goles >= 3:
        selecciones_ganadas.extend(list(Seleccion.objects.filter(mercado__evento=evento, mercado__nombre__icontains="2.5", nombre__icontains="más")))
        selecciones_perdidas.extend(list(Seleccion.objects.filter(mercado__evento=evento, mercado__nombre__icontains="2.5", nombre__icontains="menos")))

    if not selecciones_ganadas and not selecciones_perdidas:
        return

    # Liquidar Simples
    for sel in selecciones_ganadas:
        apuestas = Apuesta.objects.filter(tipo="SIMPLE", seleccion=sel, estado=EstadoApuesta.ACCEPTED).select_related("usuario")
        for apuesta in apuestas:
            user = apuesta.usuario
            stake = apuesta.monto
            LedgerEntry.objects.select_for_update().filter(usuario=user, cuenta=TipoCuenta.APUESTAS_PENDIENTES)
            payout = stake * apuesta.cuota_fijada
            tid = uuid.uuid4()
            registrar_movimiento(tid, user, TipoCuenta.APUESTAS_PENDIENTES, None, TipoCuenta.CASA, stake)
            registrar_movimiento(tid, None, TipoCuenta.CASA, user, TipoCuenta.WALLET_USUARIO, payout)
            apuesta.estado = EstadoApuesta.WON
            apuesta.save()
            actualizar_rollover_apuesta(apuesta)

    for sel in selecciones_perdidas:
        apuestas = Apuesta.objects.filter(tipo="SIMPLE", seleccion=sel, estado=EstadoApuesta.ACCEPTED).select_related("usuario")
        for apuesta in apuestas:
            user = apuesta.usuario
            stake = apuesta.monto
            LedgerEntry.objects.select_for_update().filter(usuario=user, cuenta=TipoCuenta.APUESTAS_PENDIENTES)
            tid = uuid.uuid4()
            registrar_movimiento(tid, user, TipoCuenta.APUESTAS_PENDIENTES, None, TipoCuenta.CASA, stake)
            apuesta.estado = EstadoApuesta.LOST
            apuesta.save()
            actualizar_rollover_apuesta(apuesta)

    # Liquidar Combinadas que se pierden
    for sel in selecciones_perdidas:
        combinadas = Apuesta.objects.filter(tipo="COMBINADA", selecciones=sel, estado=EstadoApuesta.ACCEPTED).distinct()
        for combinada in combinadas:
            user = combinada.usuario
            LedgerEntry.objects.select_for_update().filter(usuario=user, cuenta=TipoCuenta.APUESTAS_PENDIENTES)
            tid = uuid.uuid4()
            registrar_movimiento(tid, user, TipoCuenta.APUESTAS_PENDIENTES, None, TipoCuenta.CASA, combinada.monto)
            combinada.estado = EstadoApuesta.LOST
            combinada.save()
            actualizar_rollover_apuesta(combinada)

    # Las combinadas con selecciones ganadas se dejan pendientes hasta que TODAS las selecciones de ese ticket estén resueltas
    # (esto lo maneja liquidar_apuestas_evento al final)


@transaction.atomic
def recalcular_cuotas_por_goles(evento, goles_local_nuevos, goles_visitante_nuevos):
    if goles_local_nuevos <= 0 and goles_visitante_nuevos <= 0:
        return

    # Liquidación temprana
    liquidar_apuestas_resueltas_temprano(evento)

    # Recalcular usando la nueva lógica general
    cuotas_data = recalcular_cuotas_dinamicas(evento)

    # Suspender temporalmente mercados
    Mercado.objects.filter(evento=evento).update(activo=False)

    # Transmitir suspensión a WebSockets
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
                    "nuevas_cuotas": cuotas_data
                }
            }
        )

    # Programar reactivación asíncrona de los mercados tras 15 segundos
    reactivar_mercados_evento.delay(evento.id)


@transaction.atomic
def registrar_evento_critico(evento_id, tipo_evento_critico):
    try:
        evento = Evento.objects.get(pk=evento_id)
    except Evento.DoesNotExist:
        raise ValidationError("El evento no existe.")

    # Aplicar cambios correspondientes según el evento crítico
    if tipo_evento_critico == "GOL_LOCAL":
        evento.goles_local += 1
    elif tipo_evento_critico == "GOL_VISITANTE":
        evento.goles_visitante += 1
    
    evento.estado = EstadoEvento.EN_VIVO
    # Guardamos. Nota: Esto activará Evento.save(), que a su vez llama a recalcular_cuotas_por_goles!
    evento.save()

    return evento
