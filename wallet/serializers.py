from decimal import Decimal
from rest_framework import serializers
from django.core.exceptions import ValidationError as DjangoValidationError
from . import services


class DepositoSerializer(serializers.Serializer):
    monto = serializers.DecimalField(
        max_digits=18, decimal_places=4, min_value=Decimal("0.0001")
    )

    def create(self, validated_data):
        user = self.context["request"].user
        try:
            tx_id, entries = services.depositar(
                user=user,
                monto=validated_data["monto"],
            )
            return {"transaction_id": tx_id, "monto": validated_data["monto"]}
        except DjangoValidationError as e:
            raise serializers.ValidationError(e.messages)


class RetiroSerializer(serializers.Serializer):
    monto = serializers.DecimalField(
        max_digits=18, decimal_places=4, min_value=Decimal("0.0001")
    )

    def create(self, validated_data):
        user = self.context["request"].user
        try:
            tx_id, entries = services.retirar(
                user=user,
                monto=validated_data["monto"],
            )
            return {"transaction_id": tx_id, "monto": validated_data["monto"]}
        except DjangoValidationError as e:
            raise serializers.ValidationError(e.messages)
