import csv
import io
from decimal import Decimal

from django.db.models import Sum, Count, Q
from django.utils import timezone

from config.choices import EstadoApuesta
from betting.models import Apuesta, ApuestaSeleccion


def generate_monthly_report(year, month):
    """
    Genera reporte mensual estilo MINCETUR con columnas de la normativa de juegos de azar.
    Retorna lista de dicts para serialización CSV.
    """
    inicio_mes = timezone.datetime(year, month, 1, tzinfo=timezone.get_current_timezone())
    if month == 12:
        fin_mes = inicio_mes.replace(year=year + 1, month=1)
    else:
        fin_mes = inicio_mes.replace(month=month + 1)

    apuestas = (
        Apuesta.objects.filter(
            creado__gte=inicio_mes,
            creado__lt=fin_mes,
        )
        .select_related("usuario", "usuario__perfil", "seleccion__mercado__evento")
        .prefetch_related("selecciones__seleccion__mercado__evento")
        .order_by("creado")
    )

    filas = []

    for apuesta in apuestas:
        evento = None
        seleccion_nombre = ""
        mercado_nombre = ""
        cuota = apuesta.cuota_fijada

        if apuesta.tipo == "SIMPLE" and apuesta.seleccion:
            evento = apuesta.seleccion.mercado.evento
            seleccion_nombre = apuesta.seleccion.nombre
            mercado_nombre = apuesta.seleccion.mercado.nombre
        elif apuesta.tipo == "COMBINADA":
            detalles = apuesta.selecciones.select_related(
                "seleccion__mercado__evento"
            ).all()
            if detalles.exists():
                primer_det = detalles.first()
                evento = primer_det.seleccion.mercado.evento
                seleccion_nombre = ", ".join(
                    d.seleccion.nombre for d in detalles
                )
                mercado_nombre = "Combinada"

        payout = Decimal("0.0000")
        if apuesta.estado == EstadoApuesta.WON:
            payout = apuesta.monto * apuesta.cuota_fijada

        ggr = apuesta.monto - payout

        perfil = getattr(apuesta.usuario, "perfil", None)
        dni = perfil.dni if perfil else "N/A"

        filas.append({
            "fecha": apuesta.creado.strftime("%Y-%m-%d %H:%M:%S"),
            "tipo_juego": "Apuesta Deportiva",
            "tipo_apuesta": apuesta.tipo,
            "evento_id": str(evento.id) if evento else "N/A",
            "evento": f"{evento.local} vs {evento.visitante}" if evento else "N/A",
            "mercado": mercado_nombre,
            "seleccion": seleccion_nombre,
            "monto_apostado": str(apuesta.monto.quantize(Decimal("0.0001"))),
            "cuota": str(cuota.quantize(Decimal("0.0001"))),
            "monto_ganado": str(payout.quantize(Decimal("0.0001"))),
            "ggr": str(ggr.quantize(Decimal("0.0001"))),
            "usuario_dni": dni,
            "usuario_nombre": apuesta.usuario.username,
            "estado_apuesta": apuesta.estado,
        })

    return filas


def generate_csv_content(filas):
    """
    Genera contenido CSV con encoding UTF-8 + BOM (compatible Excel).
    """
    output = io.StringIO()

    bom = "\ufeff"
    output.write(bom)

    if not filas:
        return output.getvalue()

    fieldnames = list(filas[0].keys())
    writer = csv.DictWriter(output, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)

    writer.writeheader()
    for fila in filas:
        writer.writerow(fila)

    return output.getvalue()


def get_monthly_summary(year, month):
    """
    Retorna resumen estadístico del mes sin generar el CSV completo.
    """
    inicio_mes = timezone.datetime(year, month, 1, tzinfo=timezone.get_current_timezone())
    if month == 12:
        fin_mes = inicio_mes.replace(year=year + 1, month=1)
    else:
        fin_mes = inicio_mes.replace(month=month + 1)

    resultado = Apuesta.objects.filter(
        creado__gte=inicio_mes,
        creado__lt=fin_mes,
    ).aggregate(
        total_apuestas=Sum("monto"),
        total_ganadas=Sum("monto", filter=Q(estado=EstadoApuesta.WON)),
        count=Count("id"),
    )

    total_apostado = resultado["total_apuestas"] or Decimal("0.00")
    total_ganadas_monto = resultado["total_ganadas"] or Decimal("0.00")

    return {
        "mes": f"{year}-{month:02d}",
        "total_apostado": str(total_apostado.quantize(Decimal("0.01"))),
        "total_ganadas_monto": str(total_ganadas_monto.quantize(Decimal("0.01"))),
        "ggr_mes": str((total_apostado - total_ganadas_monto).quantize(Decimal("0.01"))),
        "num_apuestas": resultado["count"] or 0,
    }
