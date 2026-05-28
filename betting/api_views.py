from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions, generics
from django.core.cache import cache
from django.core.exceptions import ValidationError

from betting.models import Evento, EstadoEvento
from betting.serializers import EventoSerializer, ApuestaCreateSerializer, ApuestaSerializer
from betting.services import crear_apuesta


class CatalogoEventosAPIView(generics.ListAPIView):
    serializer_class = EventoSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        # Cargar relaciones de una vez
        return Evento.objects.filter(
            estado__in=[EstadoEvento.PROGRAMADO, EstadoEvento.EN_VIVO]
        ).prefetch_related("mercados__selecciones")


class CrearApuestaAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        # Validar llave de idempotencia
        idempotency_key = request.headers.get("X-Idempotency-Key")
        if idempotency_key:
            cache_key = f"idemp_bet_{request.user.id}_{idempotency_key}"
            response_guardada = cache.get(cache_key)
            if response_guardada is not None:
                return Response(response_guardada, status=status.HTTP_200_OK)

        serializer = ApuestaCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        seleccion_id = serializer.validated_data["seleccion_id"]
        monto = serializer.validated_data["monto"]

        try:
            apuesta = crear_apuesta(request.user, seleccion_id, monto)
        except ValidationError as e:
            return Response({"detail": str(e.message if hasattr(e, "message") else e)}, status=status.HTTP_400_BAD_REQUEST)

        response_data = ApuestaSerializer(apuesta).data

        if idempotency_key:
            cache.set(cache_key, response_data, timeout=300)

        return Response(response_data, status=status.HTTP_201_CREATED)
