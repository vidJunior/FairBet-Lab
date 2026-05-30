from rest_framework import serializers
from decimal import Decimal
from betting.models import Evento, Mercado, Seleccion, Apuesta, ApuestaSeleccion


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
            "minuto_actual",
            "periodo",
            "mercados",
        ]


class ApuestaSeleccionSerializer(serializers.ModelSerializer):
    seleccion_id = serializers.IntegerField(source="seleccion.id")
    seleccion_nombre = serializers.CharField(source="seleccion.nombre")
    evento_nombre = serializers.SerializerMethodField()
    cuota_fijada = serializers.DecimalField(max_digits=18, decimal_places=4)

    class Meta:
        model = ApuestaSeleccion
        fields = ["seleccion_id", "seleccion_nombre", "evento_nombre", "cuota_fijada"]

    def get_evento_nombre(self, obj):
        evento = obj.seleccion.mercado.evento
        return f"{evento.local} vs {evento.visitante}"


class ApuestaSerializer(serializers.ModelSerializer):
    seleccion_nombre = serializers.SerializerMethodField()
    evento_nombre = serializers.SerializerMethodField()
    detalles = ApuestaSeleccionSerializer(many=True, read_only=True)

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
            "tipo",
            "detalles",
            "creado",
        ]
        read_only_fields = ["usuario", "cuota_fijada", "estado", "tipo", "detalles"]

    def get_seleccion_nombre(self, obj):
        if obj.seleccion:
            return obj.seleccion.nombre
        return None

    def get_evento_nombre(self, obj):
        if obj.seleccion:
            evento = obj.seleccion.mercado.evento
            return f"{evento.local} vs {evento.visitante}"
        return "Apuesta Combinada"


class ApuestaCreateSerializer(serializers.Serializer):
    seleccion_id = serializers.IntegerField(required=False, allow_null=True)
    cuota_esperada = serializers.DecimalField(
        max_digits=18, decimal_places=4, required=False, allow_null=True
    )

    seleccion_ids = serializers.ListField(
        child=serializers.IntegerField(), required=False, allow_empty=True
    )
    cuotas_esperadas = serializers.DictField(
        child=serializers.DecimalField(max_digits=18, decimal_places=4),
        required=False,
        allow_empty=True,
    )

    monto = serializers.DecimalField(max_digits=18, decimal_places=4)

    def validate_monto(self, value):
        if value <= Decimal("0.0000"):
            raise serializers.ValidationError("El monto debe ser mayor a cero.")
        return value

    def validate(self, attrs):
        seleccion_id = attrs.get("seleccion_id")
        seleccion_ids = attrs.get("seleccion_ids")

        if not seleccion_id and not seleccion_ids:
            raise serializers.ValidationError(
                "Debe especificar 'seleccion_id' para apuestas simples o 'seleccion_ids' para apuestas combinadas."
            )
        if seleccion_id and seleccion_ids:
            raise serializers.ValidationError(
                "No puede enviar 'seleccion_id' y 'seleccion_ids' a la vez."
            )
        return attrs
