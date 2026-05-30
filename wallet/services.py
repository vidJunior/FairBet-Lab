import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from config.choices import Direccion, TipoCuenta
from wallet.models import LedgerEntry


def registrar_movimiento(
    tid, usuario_debito, cuenta_debito, usuario_credito, cuenta_credito, monto
):
    """Crea el par de movimientos DEBIT + CREDIT en un único insert de base de datos."""
    LedgerEntry.objects.bulk_create(
        [
            LedgerEntry(
                id_transaccion=tid,
                usuario=usuario_debito,
                cuenta=cuenta_debito,
                monto=monto,
                direccion=Direccion.DEBIT,
            ),
            LedgerEntry(
                id_transaccion=tid,
                usuario=usuario_credito,
                cuenta=cuenta_credito,
                monto=monto,
                direccion=Direccion.CREDIT,
            ),
        ]
    )

def validar_limites_deposito(user, perfil, monto):
    """Valida los límites acumulados diarios, semanales y mensuales de depósito."""
    ahora = timezone.now()
    inicio_dia = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
    inicio_semana = (ahora - timezone.timedelta(days=ahora.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    inicio_mes = ahora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    periodos = [
        (inicio_dia, perfil.limite_deposito_diario, "diario"),
        (inicio_semana, perfil.limite_deposito_semanal, "semanal"),
        (inicio_mes, perfil.limite_deposito_mensual, "mensual"),
    ]

    for inicio, limite, periodo in periodos:
        ya_depositado = LedgerEntry.objects.filter(
            usuario=user,
            cuenta=TipoCuenta.WALLET_USUARIO,
            direccion=Direccion.CREDIT,
            creado__gte=inicio,
        ).aggregate(total=Sum("monto"))["total"] or Decimal("0.0000")

        if ya_depositado + monto > limite:
            raise ValidationError(
                f"Límite {periodo} superado. Ya depositado: {ya_depositado}, límite: {limite}."
            )


def obtener_perfil_usuario(user):
    """Obtiene el perfil del usuario o lanza ValidationError si no tiene uno."""
    if not hasattr(user, "perfil") or user.perfil is None:
        raise ValidationError("El usuario no tiene un perfil asociado.")
    return user.perfil


def validar_monto_positivo(amount):
    monto = Decimal(str(amount))
    if monto <= 0:
        raise ValidationError("El monto debe ser mayor a cero.")
    return monto


@transaction.atomic
def recargar(user, amount):
    """Acredita fichas al usuario (DEBIT casa -> CREDIT wallet_usuario)."""
    monto = validar_monto_positivo(amount)
    perfil = obtener_perfil_usuario(user)
    perfil.aplicar_limite_pendiente()
    validar_limites_deposito(user, perfil, monto)

    tid = uuid.uuid4()
    registrar_movimiento(
        tid, None, TipoCuenta.CASA, user, TipoCuenta.WALLET_USUARIO, monto
    )
    return tid


@transaction.atomic
def retirar(user, amount):
    """Debita fichas del usuario (DEBIT wallet_usuario -> CREDIT casa)"""
    monto = validar_monto_positivo(amount)
    obtener_perfil_usuario(user)

    from panel.rollover import tiene_bono_activo_sin_rollover
    if tiene_bono_activo_sin_rollover(user):
        raise ValidationError(
            "No se puede retirar mientras tengas un bono activo con rollover pendiente. "
            "Completa el rollover o espera a que expire el bono."
        )

    LedgerEntry.objects.select_for_update().filter(
        usuario=user, cuenta=TipoCuenta.WALLET_USUARIO
    )
    saldo_actual = LedgerEntry.get_balance(user, TipoCuenta.WALLET_USUARIO)

    if saldo_actual < monto:
        raise ValidationError(
            f"Saldo insuficiente. Disponible: {saldo_actual}, solicitado: {monto}."
        )

    tid = uuid.uuid4()
    registrar_movimiento(
        tid, user, TipoCuenta.WALLET_USUARIO, None, TipoCuenta.CASA, monto
    )
    return tid


@transaction.atomic
def transferencia_interna(user, cuenta_origen, cuenta_destino, amount):
    """Mueve fondos entre dos cuentas del mismo usuario (DEBIT cuenta_origen -> CREDIT cuenta_destino)."""
    monto = validar_monto_positivo(amount)
    obtener_perfil_usuario(user)

    if cuenta_origen == cuenta_destino:
        raise ValidationError("Las cuentas de origen y destino no pueden ser iguales.")

    saldo_origen = LedgerEntry.get_balance(user, cuenta_origen)
    if saldo_origen < monto:
        raise ValidationError(
            f"Saldo insuficiente en {cuenta_origen}. Disponible: {saldo_origen}."
        )

    tid = uuid.uuid4()
    registrar_movimiento(tid, user, cuenta_origen, user, cuenta_destino, monto)
    return tid
