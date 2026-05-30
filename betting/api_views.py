from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions, generics
from django.core.cache import cache
from django.core.exceptions import ValidationError

from config.choices import EstadoEvento
from betting.models import Evento
from betting.serializers import EventoSerializer, ApuestaCreateSerializer, ApuestaSerializer
from betting.services import crear_apuesta, crear_apuesta_combinada


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

        seleccion_id = serializer.validated_data.get("seleccion_id")
        seleccion_ids = serializer.validated_data.get("seleccion_ids")
        monto = serializer.validated_data["monto"]

        try:
            if seleccion_id:
                cuota_esperada = serializer.validated_data.get("cuota_esperada")
                apuesta = crear_apuesta(
                    request.user,
                    seleccion_id,
                    monto,
                    cuota_esperada=cuota_esperada
                )
            else:
                cuotas_esperadas = serializer.validated_data.get("cuotas_esperadas")
                apuesta = crear_apuesta_combinada(
                    request.user,
                    seleccion_ids,
                    monto,
                    cuotas_esperadas=cuotas_esperadas
                )
        except ValidationError as e:
            return Response(
                {"detail": str(e.message if hasattr(e, "message") else e)},
                status=status.HTTP_400_BAD_REQUEST
            )

        response_data = ApuestaSerializer(apuesta).data

        if idempotency_key:
            cache.set(cache_key, response_data, timeout=300)

        return Response(response_data, status=status.HTTP_201_CREATED)


class OperatorEventosAPIView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        eventos = Evento.objects.prefetch_related("mercados__selecciones").all().order_by("-fecha_inicio")
        serializer = EventoSerializer(eventos, many=True)
        return Response(serializer.data)

    def post(self, request):
        local = request.data.get("local")
        visitante = request.data.get("visitante")
        fecha_inicio = request.data.get("fecha_inicio")

        if not local or not visitante or not fecha_inicio:
            return Response(
                {"error": "Los campos local, visitante y fecha_inicio son obligatorios."},
                status=status.HTTP_400_BAD_REQUEST
            )

        from django.utils.dateparse import parse_datetime
        fecha_dt = parse_datetime(fecha_inicio)
        if not fecha_dt:
            return Response(
                {"error": "Formato de fecha_inicio inválido."},
                status=status.HTTP_400_BAD_REQUEST
            )

        from betting.services import crear_evento_operador
        try:
            evento = crear_evento_operador(local, visitante, fecha_dt)
            return Response(EventoSerializer(evento).data, status=status.HTTP_201_CREATED)
        except ValidationError as e:
            return Response({"error": str(e.message if hasattr(e, "message") else e)}, status=status.HTTP_400_BAD_REQUEST)


class OperatorEventoDetailAPIView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def put(self, request, evento_id):
        goles_local = request.data.get("goles_local")
        goles_visitante = request.data.get("goles_visitante")
        estado = request.data.get("estado")
        minuto_actual = request.data.get("minuto_actual", 0)
        periodo = request.data.get("periodo", "1T")
        fecha_inicio = request.data.get("fecha_inicio")

        if goles_local is None or goles_visitante is None or not estado:
            return Response(
                {"error": "Los campos goles_local, goles_visitante y estado son obligatorios."},
                status=status.HTTP_400_BAD_REQUEST
            )

        fecha_dt = None
        if fecha_inicio:
            from django.utils.dateparse import parse_datetime
            fecha_dt = parse_datetime(fecha_inicio)
            if not fecha_dt:
                return Response(
                    {"error": "Formato de fecha_inicio inválido."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        from betting.services import actualizar_evento_operador
        try:
            evento = actualizar_evento_operador(
                evento_id, goles_local, goles_visitante, estado, minuto_actual, periodo, fecha_inicio=fecha_dt
            )
            return Response(EventoSerializer(evento).data, status=status.HTTP_200_OK)
        except ValidationError as e:
            return Response({"error": str(e.message if hasattr(e, "message") else e)}, status=status.HTTP_400_BAD_REQUEST)


class OperatorMercadosAPIView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, evento_id):
        mercado_nombre = request.data.get("nombre")
        automatico = request.data.get("automatico", False)

        if not automatico:
            selecciones_datos = request.data.get("selecciones") # Lista de dicts [{"nombre": "...", "cuota": ...}]
            if not mercado_nombre or not selecciones_datos:
                return Response(
                    {"error": "El nombre del mercado y la lista de selecciones son obligatorios."},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            if not mercado_nombre:
                return Response(
                    {"error": "El nombre del mercado es obligatorio."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        from betting.services import crear_mercado_operador
        try:
            if automatico:
                # Generar borrador de selecciones según el nombre de mercado
                if mercado_nombre == "Doble Oportunidad":
                    selecciones_datos = [
                        {"nombre": "1X", "cuota": 1.0},
                        {"nombre": "12", "cuota": 1.0},
                        {"nombre": "X2", "cuota": 1.0}
                    ]
                elif "ambos" in mercado_nombre.lower():
                    mercado_nombre = "Ambos Equipos Anotan"
                    selecciones_datos = [
                        {"nombre": "Sí", "cuota": 1.0},
                        {"nombre": "No", "cuota": 1.0}
                    ]
                elif "2.5" in mercado_nombre:
                    mercado_nombre = "Más/Menos 2.5"
                    selecciones_datos = [
                        {"nombre": "Más de 2.5", "cuota": 1.0},
                        {"nombre": "Menos de 2.5", "cuota": 1.0}
                    ]
                else:
                    return Response({"error": "Generación automática no soportada para este mercado."}, status=status.HTTP_400_BAD_REQUEST)

            mercado = crear_mercado_operador(evento_id, mercado_nombre, selecciones_datos)
            
            if automatico:
                # Recalcular cuotas dinámicamente reutilizando el algoritmo existente
                from betting.models import Evento
                from betting.services import recalcular_cuotas_dinamicas
                evento = Evento.objects.get(pk=evento_id)
                recalcular_cuotas_dinamicas(evento)

            # Notificar al catálogo sobre el nuevo mercado
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    "live_odds",
                    {
                        "type": "odds_update",
                        "data": {
                            "tipo_evento": "CATALOGO_ACTUALIZADO",
                            "motivo": "MERCADO_CREADO",
                            "evento_id": int(evento_id),
                        }
                    }
                )
            
            return Response({"message": f"Mercado '{mercado.nombre}' creado con éxito."}, status=status.HTTP_201_CREATED)
        except ValidationError as e:
            return Response({"error": str(e.message if hasattr(e, "message") else e)}, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, evento_id):
        # Permitir leer de query params o del request body json
        mercado_id = request.data.get("mercado_id") or request.query_params.get("mercado_id")
        if not mercado_id:
            return Response(
                {"error": "El ID del mercado es obligatorio."},
                status=status.HTTP_400_BAD_REQUEST
            )

        from betting.models import Mercado
        try:
            mercado = Mercado.objects.get(id=mercado_id, evento_id=evento_id)
            from django.db.models import ProtectedError
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            
            try:
                mercado.delete()
                
                # Notificar al catálogo sobre la eliminación del mercado
                channel_layer = get_channel_layer()
                if channel_layer:
                    async_to_sync(channel_layer.group_send)(
                        "live_odds",
                        {
                            "type": "odds_update",
                            "data": {
                                "tipo_evento": "CATALOGO_ACTUALIZADO",
                                "motivo": "MERCADO_ELIMINADO",
                                "evento_id": int(evento_id),
                            }
                        }
                    )
                return Response({"message": "Mercado eliminado con éxito."}, status=status.HTTP_200_OK)
            except ProtectedError:
                mercado.activo = False
                mercado.save()
                
                # Notificar al catálogo sobre la desactivación del mercado
                channel_layer = get_channel_layer()
                if channel_layer:
                    async_to_sync(channel_layer.group_send)(
                        "live_odds",
                        {
                            "type": "odds_update",
                            "data": {
                                "tipo_evento": "CATALOGO_ACTUALIZADO",
                                "motivo": "MERCADO_ELIMINADO",
                                "evento_id": int(evento_id),
                            }
                        }
                    )
                return Response({"message": "Mercado desactivado ya que tiene apuestas asociadas."}, status=status.HTTP_200_OK)
        except Mercado.DoesNotExist:
            return Response(
                {"error": "El mercado no existe o no pertenece a este evento."},
                status=status.HTTP_404_NOT_FOUND
            )

