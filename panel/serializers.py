from decimal import Decimal

from rest_framework import serializers

from config.choices import TipoBono, EstadoBono
from panel.models import Bono, AlertaAbuso


class BonoSerializer(serializers.ModelSerializer):
    usuario_username = serializers.CharField(source="usuario.username", read_only=True)
    rollover_progreso = serializers.ReadOnlyField()
    rollover_completado = serializers.ReadOnlyField()

    class Meta:
        model = Bono
        fields = [
            "id",
            "usuario",
            "usuario_username",
            "tipo",
            "monto",
            "rollover_multiplier",
            "rollover_requerido",
            "rollover_apostado",
            "rollover_progreso",
            "rollover_completado",
            "cuota_minima_rollover",
            "estado",
            "creado",
            "expira",
        ]
        read_only_fields = ["id", "creado", "rollover_requerido"]


class BonoCreateSerializer(serializers.Serializer):
    usuario_id = serializers.IntegerField()
    tipo = serializers.ChoiceField(choices=TipoBono.choices)
    monto = serializers.DecimalField(max_digits=10, decimal_places=4)
    rollover_multiplier = serializers.DecimalField(
        max_digits=6, decimal_places=2, default=Decimal("5.00"), required=False
    )
    expira = serializers.DateTimeField(required=False, allow_null=True)

    def create(self, validated_data):
        from django.contrib.auth import get_user_model
        from panel.models import Bono
        from config.choices import TipoCuenta
        from wallet.services import registrar_movimiento
        import uuid

        User = get_user_model()
        usuario = User.objects.get(pk=validated_data["usuario_id"])

        bono = Bono.objects.create(
            usuario=usuario,
            tipo=validated_data["tipo"],
            monto=validated_data["monto"],
            rollover_multiplier=validated_data.get("rollover_multiplier", Decimal("5.00")),
            expira=validated_data.get("expira"),
        )

        # Registrar los asientos contables en Billetera (Partida Doble)
        # Débito a la Casa (pérdida promocional) y Crédito a la cuenta de Bonos del Usuario
        tid = uuid.uuid4()
        registrar_movimiento(
            tid,
            usuario_debito=None,
            cuenta_debito=TipoCuenta.CASA,
            usuario_credito=usuario,
            cuenta_credito=TipoCuenta.BONOS,
            monto=validated_data["monto"],
        )

        return bono


class AlertaAbusoSerializer(serializers.ModelSerializer):
    usuario_username = serializers.CharField(source="usuario.username", read_only=True)
    bono_tipo = serializers.CharField(source="bono.tipo", read_only=True)
    bono_monto = serializers.CharField(source="bono.monto", read_only=True)

    class Meta:
        model = AlertaAbuso
        fields = [
            "id",
            "usuario",
            "usuario_username",
            "bono",
            "bono_tipo",
            "bono_monto",
            "tipo",
            "detalle",
            "revisado",
            "creado",
        ]
        read_only_fields = ["id", "creado"]
