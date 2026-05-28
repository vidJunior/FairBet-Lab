import uuid
from decimal import Decimal
from django.db import transaction as db_transaction, models
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.contrib.auth.models import User
from config.choices import (
    DireccionLedger,
    TipoCuenta,
    TipoTransaccion,
    EstadoPerfil,
)
from .models import LedgerEntry


def _verificar_estado_usuario(user):
    if not hasattr(user, "perfil"):
        raise ValidationError("El usuario no tiene un perfil configurado.")

    perfil = user.perfil
    perfil.aplicar_limite_pendiente()

    if perfil.estado == EstadoPerfil.BLOQUEADO:
        raise ValidationError("Tu cuenta esta bloqueada. Contacta a soporte.")
    if perfil.estado == EstadoPerfil.PENDIENTE_VERIFICACION:
        raise ValidationError("Tu cuenta esta pendiente de verificacion KYC.")
    if perfil.esta_autoexcluido:
        raise ValidationError(
            "Tu cuenta esta autoexcluida. No puedes realizar transacciones."
        )


def _verificar_limite_deposito(user, monto):
    perfil = user.perfil
    ahora = timezone.now()

    limites = [
        ("diario", perfil.limite_deposito_diario, ahora - timezone.timedelta(days=1)),
        (
            "semanal",
            perfil.limite_deposito_semanal,
            ahora - timezone.timedelta(weeks=1),
        ),
        (
            "mensual",
            perfil.limite_deposito_mensual,
            ahora - timezone.timedelta(days=30),
        ),
    ]

    for periodo, limite, fecha_inicio in limites:
        depositos_periodo = LedgerEntry.objects.filter(
            user=user,
            account=TipoCuenta.WALLET_USUARIO,
            direction=DireccionLedger.CREDIT,
            tipo_transaccion=TipoTransaccion.DEPOSITO,
            creado_en__gte=fecha_inicio,
        ).aggregate(total=models.Sum("amount"))["total"] or Decimal("0.0000")

        if depositos_periodo + monto > limite:
            raise ValidationError(
                f"El deposito excede el limite {periodo} configurado "
                f"(actual: {depositos_periodo}, limite: {limite}, solicitado: {monto})."
            )


def depositar(user, monto, descripcion="Deposito de fichas"):
    _verificar_estado_usuario(user)
    _verificar_limite_deposito(user, monto)

    if monto <= 0:
        raise ValidationError("El monto del deposito debe ser mayor a cero.")

    entradas = [
        {
            "user": user,
            "account": TipoCuenta.WALLET_USUARIO,
            "amount": monto,
            "direction": DireccionLedger.CREDIT,
        },
        {
            "user": None,
            "account": TipoCuenta.CASA,
            "amount": monto,
            "direction": DireccionLedger.DEBIT,
        },
    ]

    return LedgerEntry.crear_transaccion(
        entradas=entradas,
        tipo_transaccion=TipoTransaccion.DEPOSITO,
        user=user,
        descripcion=descripcion,
    )


def retirar(user, monto, descripcion="Retiro de fichas"):
    _verificar_estado_usuario(user)

    if monto <= 0:
        raise ValidationError("El monto del retiro debe ser mayor a cero.")

    with db_transaction.atomic():
        try:
            saldo = LedgerEntry.objects.select_for_update(nowait=True).filter(
                user=user
            ).aggregate(
                total=models.Sum(
                    models.Case(
                        models.When(
                            direction=DireccionLedger.CREDIT,
                            then=models.F("amount"),
                        ),
                        models.When(
                            direction=DireccionLedger.DEBIT,
                            then=models.F("amount") * -1,
                        ),
                        output_field=models.DecimalField(
                            max_digits=18, decimal_places=4
                        ),
                    )
                )
            )["total"] or Decimal("0.0000")
        except Exception:
            raise ValidationError(
                "No se pudo procesar el retiro. Intenta de nuevo en unos segundos."
            )

        if saldo < monto:
            raise ValidationError(
                f"Saldo insuficiente. Disponible: {saldo}, solicitado: {monto}."
            )

        transaction_id = uuid.uuid4()
        LedgerEntry.objects.create(
            user=user,
            account=TipoCuenta.WALLET_USUARIO,
            amount=monto,
            direction=DireccionLedger.DEBIT,
            transaction_id=transaction_id,
            tipo_transaccion=TipoTransaccion.RETIRO,
            descripcion=descripcion,
        )
        LedgerEntry.objects.create(
            user=None,
            account=TipoCuenta.CASA,
            amount=monto,
            direction=DireccionLedger.CREDIT,
            transaction_id=transaction_id,
            tipo_transaccion=TipoTransaccion.RETIRO,
            descripcion=descripcion,
        )

        return transaction_id, LedgerEntry.objects.filter(
            transaction_id=transaction_id
        )


def bloquear_fondos_apuesta(user, stake, descripcion="Bloqueo de fondos para apuesta"):
    _verificar_estado_usuario(user)

    if stake <= 0:
        raise ValidationError("El monto de la apuesta debe ser mayor a cero.")

    with db_transaction.atomic():
        try:
            saldo = LedgerEntry.objects.select_for_update(nowait=True).filter(
                user=user
            ).aggregate(
                total=models.Sum(
                    models.Case(
                        models.When(
                            direction=DireccionLedger.CREDIT,
                            then=models.F("amount"),
                        ),
                        models.When(
                            direction=DireccionLedger.DEBIT,
                            then=models.F("amount") * -1,
                        ),
                        output_field=models.DecimalField(
                            max_digits=18, decimal_places=4
                        ),
                    )
                )
            )["total"] or Decimal("0.0000")
        except Exception:
            raise ValidationError(
                "No se pudo procesar la apuesta. Intenta de nuevo en unos segundos."
            )

        if saldo < stake:
            raise ValidationError(
                f"Saldo insuficiente para apostar. Disponible: {saldo}, necesario: {stake}."
            )

        transaction_id = uuid.uuid4()
        LedgerEntry.objects.create(
            user=user,
            account=TipoCuenta.WALLET_USUARIO,
            amount=stake,
            direction=DireccionLedger.DEBIT,
            transaction_id=transaction_id,
            tipo_transaccion=TipoTransaccion.APUESTA,
            descripcion=descripcion,
        )
        LedgerEntry.objects.create(
            user=user,
            account=TipoCuenta.APUESTAS_PENDIENTES,
            amount=stake,
            direction=DireccionLedger.CREDIT,
            transaction_id=transaction_id,
            tipo_transaccion=TipoTransaccion.APUESTA,
            descripcion=descripcion,
        )

        return transaction_id, LedgerEntry.objects.filter(
            transaction_id=transaction_id
        )


def liberar_fondos_apuesta_perdida(
    user, stake, descripcion="Liberacion de apuesta perdida"
):
    entradas = [
        {
            "user": user,
            "account": TipoCuenta.APUESTAS_PENDIENTES,
            "amount": stake,
            "direction": DireccionLedger.DEBIT,
        },
        {
            "user": None,
            "account": TipoCuenta.CASA,
            "amount": stake,
            "direction": DireccionLedger.CREDIT,
        },
    ]

    return LedgerEntry.crear_transaccion(
        entradas=entradas,
        tipo_transaccion=TipoTransaccion.LIQUIDACION_PERDIDA,
        user=user,
        descripcion=descripcion,
    )


def pagar_apuesta_ganada(
    user, stake, ganancia_neta, descripcion="Pago de apuesta ganada"
):
    total_retorno = stake + ganancia_neta

    entradas = [
        {
            "user": user,
            "account": TipoCuenta.APUESTAS_PENDIENTES,
            "amount": stake,
            "direction": DireccionLedger.DEBIT,
        },
        {
            "user": None,
            "account": TipoCuenta.CASA,
            "amount": ganancia_neta,
            "direction": DireccionLedger.DEBIT,
        },
        {
            "user": user,
            "account": TipoCuenta.WALLET_USUARIO,
            "amount": total_retorno,
            "direction": DireccionLedger.CREDIT,
        },
    ]

    return LedgerEntry.crear_transaccion(
        entradas=entradas,
        tipo_transaccion=TipoTransaccion.LIQUIDACION_GANADA,
        user=user,
        descripcion=descripcion,
    )


def devolver_apuesta_cancelada(
    user, stake, descripcion="Devolucion por apuesta cancelada"
):
    entradas = [
        {
            "user": user,
            "account": TipoCuenta.APUESTAS_PENDIENTES,
            "amount": stake,
            "direction": DireccionLedger.DEBIT,
        },
        {
            "user": user,
            "account": TipoCuenta.WALLET_USUARIO,
            "amount": stake,
            "direction": DireccionLedger.CREDIT,
        },
    ]

    return LedgerEntry.crear_transaccion(
        entradas=entradas,
        tipo_transaccion=TipoTransaccion.CANCELACION,
        user=user,
        descripcion=descripcion,
    )


def procesar_cashout(
    user, stake, monto_cashout, descripcion="Cash-Out de apuesta"
):
    if monto_cashout <= 0:
        raise ValidationError("El monto de cash-out debe ser mayor a cero.")

    entradas = [
        {
            "user": user,
            "account": TipoCuenta.APUESTAS_PENDIENTES,
            "amount": stake,
            "direction": DireccionLedger.DEBIT,
        },
        {
            "user": None,
            "account": TipoCuenta.CASHOUT,
            "amount": monto_cashout,
            "direction": DireccionLedger.DEBIT,
        },
        {
            "user": user,
            "account": TipoCuenta.WALLET_USUARIO,
            "amount": monto_cashout,
            "direction": DireccionLedger.CREDIT,
        },
    ]

    return LedgerEntry.crear_transaccion(
        entradas=entradas,
        tipo_transaccion=TipoTransaccion.CASHOUT,
        user=user,
        descripcion=descripcion,
    )


def obtener_saldo_disponible(user):
    return LedgerEntry.get_saldo_usuario(user)


def obtener_desglose_saldos(user):
    return {
        "wallet": LedgerEntry.get_saldo_cuenta_usuario(
            user, TipoCuenta.WALLET_USUARIO
        ),
        "apuestas_pendientes": LedgerEntry.get_saldo_cuenta_usuario(
            user, TipoCuenta.APUESTAS_PENDIENTES
        ),
        "bonos": LedgerEntry.get_saldo_cuenta_usuario(user, TipoCuenta.BONOS),
    }
