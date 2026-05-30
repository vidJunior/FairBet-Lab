from django.urls import path

from panel import api_views, views

app_name = "operator"

urlpatterns = [
    path("dashboard/", views.dashboard_view, name="dashboard"),
    path("reporte-mensual/", views.reporte_mensual_view, name="reporte_mensual"),
]

api_urlpatterns = [
    path("metrics/", api_views.DashboardMetricsAPIView.as_view(), name="api_metrics"),
    path("reporte-mensual/", api_views.MonthlyReportAPIView.as_view(), name="api_reporte_mensual"),
    path("alertas-abuso/", api_views.AlertasAbusoAPIView.as_view(), name="api_alertas_abuso"),
    path(
        "alertas-abuso/<uuid:alerta_id>/revisar/",
        api_views.MarcarAlertaRevisadaAPIView.as_view(),
        name="api_alerta_revisar",
    ),
    path("bonos/", api_views.BonosAPIView.as_view(), name="api_bonos"),
    path("bonos/<uuid:bono_id>/", api_views.BonoDetailView.as_view(), name="api_bono_detail"),
]
