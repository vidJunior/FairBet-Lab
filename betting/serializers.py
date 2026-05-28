from rest_framework import serializers
from decimal import Decimal
from betting.models import Evento, Mercado, Seleccion, Apuesta


class SeleccionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Seleccion
        fields = ["id", "nombre", "cuota"]


class MercadoSerializer(serializers.ModelSerializer):
    selecciones = SeleccionSerializer(many=True, read_only=True)

    class Meta:
        model = Mercado
        fields = ["id", "nombre", "activo", "selecciones"]


class EventoSerializer(serializers.ModelSerializer):
    mercados = MercadoSerializer(many=True, read_only=True)

    class Meta:
        model = Evento
        fields = [
            "id",
            "local",
            "visitante",
            "fecha_inicio",
            "estado",
            "goles_local",
            "goles_visitante",
            "mercados",
        ]


class ApuestaSerializer(serializers.ModelSerializer):
    seleccion_nombre = serializers.CharField(source="seleccion.nombre", read_only=True)
    evento_nombre = serializers.SerializerMethodField()

    class Meta:
        model = Apuesta
        fields = [
            "id",
            "usuario",
            "seleccion",
            "seleccion_nombre",
            "evento_nombre",
            "monto",
            "cuota_fijada",
            "estado",
            "creado",
        ]
        read_only_fields = ["usuario", "cuota_fijada", "estado"]

    def get_evento_nombre(self, obj):
        evento = obj.seleccion.mercado.evento
        return f"{evento.local} vs {evento.visitante}"


class ApuestaCreateSerializer(serializers.Serializer):
    seleccion_id = serializers.IntegerField()
    monto = serializers.DecimalField(max_digits=18, decimal_places=4)

    def validate_monto(self, value):
        if value <= Decimal("0.0000"):
            raise serializers.ValidationError("El monto debe ser mayor a cero.")
        return value
