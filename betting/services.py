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


def obtener_seleccion_ganadora_1x2(evento):
    """
    Retorna la selección ganadora (Local, Empate, Visitante)
    basado en los goles del evento finalizado.
    """
    mercado_1x2 = evento.mercados.filter(nombre="1X2").first()
    if not mercado_1x2:
        return None
        
    if evento.goles_local > evento.goles_visitante:
        return mercado_1x2.selecciones.filter(nombre="Local").first()
    elif evento.goles_local < evento.goles_visitante:
        return mercado_1x2.selecciones.filter(nombre="Visitante").first()
    else:
        return mercado_1x2.selecciones.filter(nombre="Empate").first()


@transaction.atomic
def crear_apuesta(user, seleccion_id, monto, cuota_esperada=None):
    """
    Crea una apuesta simple. Valida límites de apuestas, saldo, 
    estado del perfil, autoexclusión y la política de re-cotización.
    """
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
    """
    Crea una apuesta combinada (acumuladora).
    Valida exclusión mutua de eventos, cuotas y límites transaccionales.
    """
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

    eventos_vistos = set()
    cuota_acumulada = Decimal("1.0000")

    for sel in selecciones:
        # Validación de exclusión mutua
        evento_id = sel.mercado.evento_id
        if evento_id in eventos_vistos:
            raise ValidationError("No se pueden combinar selecciones del mismo partido en un solo ticket.")
        eventos_vistos.add(evento_id)

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


@transaction.atomic
def liquidar_apuestas_evento(evento_id, seleccion_ganadora_id):
    """
    Liquida apuestas simples y evalúa apuestas combinadas que contienen
    selecciones asociadas a este evento.
    """
    try:
        evento = Evento.objects.get(pk=evento_id)
    except Evento.DoesNotExist:
        raise ValidationError("El evento no existe.")

    if evento.estado == EstadoEvento.FINALIZADO:
        raise ValidationError("Este evento ya ha sido finalizado y liquidado previamente.")

    if seleccion_ganadora_id:
        try:
            seleccion_ganadora = Seleccion.objects.get(pk=seleccion_ganadora_id, mercado__evento=evento)
        except Seleccion.DoesNotExist:
            raise ValidationError("La selección ganadora especificada no pertenece a este evento.")
    else:
        # Si es nula, intentamos calcularla para 1X2 si el estado cambió a FINALIZADO
        seleccion_ganadora = obtener_seleccion_ganadora_1x2(evento)

    # 1. LIQUIDAR APUESTAS SIMPLES
    apuestas_simples = Apuesta.objects.filter(
        tipo="SIMPLE",
        seleccion__mercado__evento=evento,
        estado=EstadoApuesta.ACCEPTED
    ).select_related("usuario", "seleccion")

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

        if seleccion_ganadora and apuesta.seleccion == seleccion_ganadora:
            payout = stake * apuesta.cuota_fijada
            tid = uuid.uuid4()
            registrar_movimiento(tid, user, TipoCuenta.APUESTAS_PENDIENTES, None, TipoCuenta.CASA, stake)
            registrar_movimiento(tid, None, TipoCuenta.CASA, user, TipoCuenta.WALLET_USUARIO, payout)
            apuesta.estado = EstadoApuesta.WON
            apuesta.save()
        else:
            tid = uuid.uuid4()
            registrar_movimiento(tid, user, TipoCuenta.APUESTAS_PENDIENTES, None, TipoCuenta.CASA, stake)
            apuesta.estado = EstadoApuesta.LOST
            apuesta.save()

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
                ganador_det = obtener_seleccion_ganadora_1x2(ev_det)
                if ganador_det and det.seleccion == ganador_det:
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



@transaction.atomic
def actualizar_cuota_seleccion(seleccion_id, nueva_cuota):
    """
    Actualiza la cuota de una selección y transmite los cambios por WebSocket
    para mantener cuotas en tiempo real.
    """
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
def registrar_evento_critico(evento_id, tipo_evento_critico):
    """
    Registra un evento crítico (GOL, ROJA).
    Actualiza marcador/tarjetas, suspende el mercado del evento,
    transmite la suspensión y programa su reactivación automática tras 15s.
    """
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
    evento.save()

    # Suspender los mercados
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
                    "evento_critico": tipo_evento_critico,
                    "goles_local": evento.goles_local,
                    "goles_visitante": evento.goles_visitante,
                    "estado_mercados": "SUSPENDIDOS"
                }
            }
        )

    # Programar reactivación asíncrona de los mercados tras 15 segundos
    reactivar_mercados_evento.delay(evento.id)

    return evento
