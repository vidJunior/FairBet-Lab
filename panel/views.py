from django.shortcuts import render
from django.contrib.admin.views.decorators import staff_member_required
from django.utils import timezone

from panel.services import get_dashboard_metrics
from panel.reports import get_monthly_summary


@staff_member_required
def dashboard_view(request):
    metrics = get_dashboard_metrics()
    return render(request, "operator/dashboard.html", {"metrics": metrics})


@staff_member_required
def reporte_mensual_view(request):
    year = request.GET.get("year", timezone.now().year)
    month = request.GET.get("month", timezone.now().month)

    try:
        year = int(year)
        month = int(month)
    except (ValueError, TypeError):
        year = timezone.now().year
        month = timezone.now().month

    summary = get_monthly_summary(year, month)

    meses = [
        (1, "Enero"), (2, "Febrero"), (3, "Marzo"), (4, "Abril"),
        (5, "Mayo"), (6, "Junio"), (7, "Julio"), (8, "Agosto"),
        (9, "Septiembre"), (10, "Octubre"), (11, "Noviembre"), (12, "Diciembre"),
    ]

    return render(request, "operator/reporte_mensual.html", {
        "summary": summary,
        "year": year,
        "month": month,
        "meses": meses,
    })
