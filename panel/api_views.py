import csv
import io

from django.http import HttpResponse
from django.utils import timezone
from rest_framework import permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from panel.services import get_dashboard_metrics
from panel.reports import generate_monthly_report, generate_csv_content, get_monthly_summary
from panel.models import AlertaAbuso, Bono
from panel.abuse_detection import run_abuse_check
from panel.serializers import (
    BonoSerializer,
    BonoCreateSerializer,
    AlertaAbusoSerializer,
)


class DashboardMetricsAPIView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        metrics = get_dashboard_metrics()
        return Response(metrics)


class MonthlyReportAPIView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        year = request.query_params.get("year")
        month = request.query_params.get("month")

        if not year or not month:
            ahora = timezone.now()
            year = request.query_params.get("year", ahora.year)
            month = request.query_params.get("month", ahora.month)

        try:
            year = int(year)
            month = int(month)
        except (ValueError, TypeError):
            return Response(
                {"error": "year y month deben ser enteros"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        export = request.query_params.get("export", "false").lower() == "true"

        if export:
            filas = generate_monthly_report(year, month)
            csv_content = generate_csv_content(filas)

            response = HttpResponse(csv_content, content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = (
                f'attachment; filename="reporte_mincetur_{year}_{month:02d}.csv"'
            )
            return response

        summary = get_monthly_summary(year, month)
        return Response(summary)


class AlertasAbusoAPIView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        solo_pendientes = request.query_params.get("pendientes", "false").lower() == "true"

        queryset = AlertaAbuso.objects.select_related("usuario", "bono").all()

        if solo_pendientes:
            queryset = queryset.filter(revisado=False)

        alertas = queryset.order_by("-creado")
        serializer = AlertaAbusoSerializer(alertas, many=True)
        return Response(serializer.data)

    def post(self, request):
        run_abuse_check()
        return Response({"status": "check ejecutado"})


class MarcarAlertaRevisadaAPIView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, alerta_id):
        try:
            alerta = AlertaAbuso.objects.get(pk=alerta_id)
        except AlertaAbuso.DoesNotExist:
            return Response(
                {"error": "Alerta no encontrada"},
                status=status.HTTP_404_NOT_FOUND,
            )

        alerta.revisado = True
        alerta.save()

        return Response({"status": "alerta marcada como revisada"})


class BonosAPIView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        bonos = Bono.objects.select_related("usuario").all().order_by("-creado")
        estado = request.query_params.get("estado")
        if estado:
            bonos = bonos.filter(estado=estado)

        serializer = BonoSerializer(bonos, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = BonoCreateSerializer(data=request.data)
        if serializer.is_valid():
            bono = serializer.save()
            return Response(BonoSerializer(bono).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class BonoDetailView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request, bono_id):
        try:
            bono = Bono.objects.select_related("usuario").get(pk=bono_id)
        except Bono.DoesNotExist:
            return Response(
                {"error": "Bono no encontrado"},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(BonoSerializer(bono).data)

    def post(self, request, bono_id):
        try:
            bono = Bono.objects.get(pk=bono_id)
        except Bono.DoesNotExist:
            return Response(
                {"error": "Bono no encontrado"},
                status=status.HTTP_404_NOT_FOUND,
            )

        accion = request.data.get("accion")
        if accion == "revocar":
            from config.choices import EstadoBono
            bono.estado = EstadoBono.REVOCADO
            bono.save()
            return Response({"status": "bono revocado"})
        elif accion == "completar":
            from config.choices import EstadoBono
            bono.estado = EstadoBono.COMPLETADO
            bono.save()
            return Response({"status": "bono marcado como completado"})

        return Response(
            {"error": "Accion no valida"},
            status=status.HTTP_400_BAD_REQUEST,
        )
