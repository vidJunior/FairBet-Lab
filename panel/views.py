from django.shortcuts import render
from django.contrib.admin.views.decorators import staff_member_required
from django.utils import timezone
from django.http import HttpResponse

from panel.services import get_dashboard_metrics
from panel.reports import get_monthly_summary, generate_monthly_report, generate_csv_content


@staff_member_required
def dashboard_view(request):
    from django.contrib.auth import get_user_model
    from panel.models import Bono
    User = get_user_model()
    users = User.objects.filter(is_staff=False).order_by("username")
    bonos = Bono.objects.select_related("usuario").all().order_by("-creado")
    metrics = get_dashboard_metrics()
    return render(request, "operator/dashboard.html", {
        "metrics": metrics,
        "users": users,
        "bonos": bonos,
    })


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

    export = request.GET.get("export", "false").lower() == "true"

    if export:
        filas = generate_monthly_report(year, month)
        csv_content = generate_csv_content(filas)
        response = HttpResponse(csv_content, content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = (
            f'attachment; filename="reporte_mincetur_{year}_{month:02d}.csv"'
        )
        return response

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
