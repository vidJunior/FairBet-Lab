from decimal import Decimal

from rest_framework import serializers


class MontoSerializer(serializers.Serializer):
    """Serializer base para operaciones que reciben un monto."""

    amount = serializers.DecimalField(
        max_digits=18,
        decimal_places=4,
        min_value=Decimal("0.0001"),
        help_text="Monto en fichas (Decimal, mayor a cero).",
    )


class RecargaSerializer(MontoSerializer):
    """Valida el cuerpo de una solicitud de recarga de fichas."""

    pass


class RetiroSerializer(MontoSerializer):
    """Valida el cuerpo de una solicitud de retiro de fichas."""

    pass


class SaldoSerializer(serializers.Serializer):
    """Representa el saldo calculado dinámicamente por cuenta."""

    wallet_usuario = serializers.DecimalField(
        max_digits=18, decimal_places=4, read_only=True
    )
    apuestas_pendientes = serializers.DecimalField(
        max_digits=18, decimal_places=4, read_only=True
    )
    bonos = serializers.DecimalField(max_digits=18, decimal_places=4, read_only=True)
