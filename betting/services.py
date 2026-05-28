import uuid
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from config.choices import TipoCuenta, EstadoPerfil
from wallet.models import LedgerEntry
from wallet.services import transferencia_interna, registrar_movimiento
from betting.models import Evento, Seleccion, Apuesta, EstadoEvento, EstadoApuesta


@transaction.atomic
def crear_apuesta(user, seleccion_id, monto):
    monto = Decimal(str(monto))
    if monto <= Decimal("0.0000"):
        raise ValidationError("El monto de la apuesta debe ser mayor a cero.")

    if not hasattr(user, "perfil") or user.perfil is None:
        raise ValidationError("El usuario no tiene un perfil asociado.")
    
    perfil = user.perfil

    # Bloquear perfil para evitar doble proceso
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

    evento = seleccion.mercado.evento
    if evento.estado != EstadoEvento.PROGRAMADO:
        raise ValidationError("Solo se permite apostar en eventos programados que no hayan comenzado.")

    MIN_APUESTA = Decimal("0.5000")
    MAX_APUESTA = Decimal("5000.0000")
    if monto < MIN_APUESTA or monto > MAX_APUESTA:
        raise ValidationError(f"El monto debe estar entre {MIN_APUESTA} y {MAX_APUESTA} fichas.")

    # Validar saldo con select_for_update
    LedgerEntry.objects.select_for_update().filter(usuario=user, cuenta=TipoCuenta.WALLET_USUARIO)
    saldo = LedgerEntry.get_balance(user, TipoCuenta.WALLET_USUARIO)
    if saldo < monto:
        raise ValidationError(f"Saldo insuficiente. Saldo disponible: {saldo}, solicitado: {monto}.")

    # Retener saldo del usuario a pendientes
    transferencia_interna(user, TipoCuenta.WALLET_USUARIO, TipoCuenta.APUESTAS_PENDIENTES, monto)

    apuesta = Apuesta.objects.create(
        usuario=user,
        seleccion=seleccion,
        monto=monto,
        cuota_fijada=seleccion.cuota,
        estado=EstadoApuesta.ACCEPTED
    )

    return apuesta


@transaction.atomic
def liquidar_apuestas_evento(evento_id, seleccion_ganadora_id):
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
        seleccion_ganadora = None

    apuestas = Apuesta.objects.filter(
        seleccion__mercado__evento=evento,
        estado=EstadoApuesta.ACCEPTED
    ).select_related("usuario")

    for apuesta in apuestas:
        user = apuesta.usuario
        stake = apuesta.monto

        LedgerEntry.objects.select_for_update().filter(usuario=user, cuenta=TipoCuenta.APUESTAS_PENDIENTES)

        # Reembolso si se anula
        if evento.estado == EstadoEvento.ANULADO:
            transferencia_interna(user, TipoCuenta.APUESTAS_PENDIENTES, TipoCuenta.WALLET_USUARIO, stake)
            apuesta.estado = EstadoApuesta.CANCELLED
            apuesta.save()
            continue

        if seleccion_ganadora and apuesta.seleccion == seleccion_ganadora:
            payout = stake * apuesta.cuota_fijada
            tid = uuid.uuid4()
            
            # Pasar stake a la casa y pagar premio al usuario
            registrar_movimiento(
                tid,
                user, TipoCuenta.APUESTAS_PENDIENTES,
                None, TipoCuenta.CASA,
                stake
            )
            registrar_movimiento(
                tid,
                None, TipoCuenta.CASA,
                user, TipoCuenta.WALLET_USUARIO,
                payout
            )

            apuesta.estado = EstadoApuesta.WON
            apuesta.save()

        else:
            # Pasar stake a la casa (apuesta perdida)
            tid = uuid.uuid4()
            registrar_movimiento(
                tid,
                user, TipoCuenta.APUESTAS_PENDIENTES,
                None, TipoCuenta.CASA,
                stake
            )
            apuesta.estado = EstadoApuesta.LOST
            apuesta.save()

    if evento.estado != EstadoEvento.ANULADO:
        evento.estado = EstadoEvento.FINALIZADO
    evento.save()
