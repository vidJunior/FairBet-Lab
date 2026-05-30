from decimal import Decimal
from datetime import timedelta

from django.db.models import Sum, Count, Q
from django.utils import timezone

from config.choices import TipoCuenta, EstadoApuesta, EstadoEvento
from wallet.models import LedgerEntry
from betting.models import Apuesta, Evento, Seleccion


def calculate_ggr(period_hours=24):
    """
    Gross Gaming Revenue = stakes (perdidos por usuarios) - payouts (ganados por usuarios)
    Calculado sobre LedgerEntry entre la cuenta CASA y APUESTAS_PENDIENTES.
    """
    desde = timezone.now() - timedelta(hours=period_hours)

    stakes_perdidos = LedgerEntry.objects.filter(
        Q(cuenta=TipoCuenta.APUESTAS_PENDIENTES) | Q(cuenta=TipoCuenta.CASA),
        direccion="DEBIT",
        creado__gte=desde,
    ).aggregate(total=Sum("monto"))["total"] or Decimal("0.0000")

    payouts = LedgerEntry.objects.filter(
        cuenta=TipoCuenta.WALLET_USUARIO,
        direccion="CREDIT",
        creado__gte=desde,
    ).aggregate(total=Sum("monto"))["total"] or Decimal("0.0000")

    return (stakes_perdidos - payouts).quantize(Decimal("0.0001"))


def calculate_exposure_by_event():
    """
    Exposure por evento: cuánto pierde la casa si gana cada selección.
    Para cada evento activo, suma los payouts potenciales de todas las apuestas accepted.
    """
    eventos_activos = Evento.objects.filter(
        estado__in=[EstadoEvento.PROGRAMADO, EstadoEvento.EN_VIVO]
    ).prefetch_related("mercados__selecciones")

    exposure_data = []

    for evento in eventos_activos:
        selecciones = Seleccion.objects.filter(
            mercado__evento=evento,
            mercado__activo=True,
        ).select_related("mercado")

        total_exposure = Decimal("0.0000")
        detalles_seleccion = []

        for sel in selecciones:
            apuestas_a_sel = Apuesta.objects.filter(
                Q(seleccion=sel) | Q(selecciones=sel),
                estado=EstadoApuesta.ACCEPTED,
            ).distinct()

            exposure_sel = Decimal("0.0000")
            for apuesta in apuestas_a_sel:
                payout_potencial = apuesta.monto * apuesta.cuota_fijada
                exposure_sel += payout_potencial

            if exposure_sel > 0:
                detalles_seleccion.append({
                    "seleccion_id": sel.id,
                    "seleccion_nombre": sel.nombre,
                    "mercado": sel.mercado.nombre,
                    "cuota_actual": str(sel.cuota),
                    "total_apostado": str(
                        apuestas_a_sel.aggregate(total=Sum("monto"))["total"] or Decimal("0")
                    ),
                    "exposure": str(exposure_sel.quantize(Decimal("0.0001"))),
                })
                total_exposure += exposure_sel

        if detalles_seleccion:
            exposure_data.append({
                "evento_id": evento.id,
                "evento_nombre": f"{evento.local.nombre} vs {evento.visitante.nombre}",
                "estado": evento.estado,
                "minuto": evento.minuto_actual,
                "total_exposure": str(total_exposure.quantize(Decimal("0.0001"))),
                "selecciones": detalles_seleccion,
            })

    exposure_data.sort(key=lambda x: Decimal(x["total_exposure"]), reverse=True)
    return exposure_data


def calculate_volume(hours=24):
    """
    Volumen total de apuestas en las últimas N horas.
    """
    desde = timezone.now() - timedelta(hours=hours)

    resultado = Apuesta.objects.filter(
        creado__gte=desde,
    ).aggregate(
        total_staked=Sum("monto"),
        total_apuestas=Count("id"),
        apuestas_ganadas=Count("id", filter=Q(estado=EstadoApuesta.WON)),
        apuestas_perdidas=Count("id", filter=Q(estado=EstadoApuesta.LOST)),
        apuestas_pendientes=Count("id", filter=Q(estado=EstadoApuesta.ACCEPTED)),
    )

    return {
        "total_staked": str(resultado["total_staked"] or Decimal("0.0000")),
        "total_apuestas": resultado["total_apuestas"] or 0,
        "apuestas_ganadas": resultado["apuestas_ganadas"] or 0,
        "apuestas_perdidas": resultado["apuestas_perdidas"] or 0,
        "apuestas_pendientes": resultado["apuestas_pendientes"] or 0,
    }


def count_active_users(hours=1):
    """
    Número de usuarios únicos que han realizado apuestas en las últimas N horas.
    """
    desde = timezone.now() - timedelta(hours=hours)

    return (
        Apuesta.objects.filter(creado__gte=desde)
        .values("usuario")
        .distinct()
        .count()
    )


def get_dashboard_metrics():
    """
    Retorna todas las métricas del dashboard en una sola llamada.
    """
    ggr_24h = calculate_ggr(period_hours=24)
    ggr_7d = calculate_ggr(period_hours=24 * 7)
    volume_24h = calculate_volume(hours=24)
    active_users_1h = count_active_users(hours=1)
    active_users_24h = count_active_users(hours=24)
    exposure = calculate_exposure_by_event()

    total_exposure = sum(
        Decimal(e["total_exposure"]) for e in exposure
    )

    return {
        "ggr_24h": str(ggr_24h),
        "ggr_7d": str(ggr_7d),
        "volume_24h": volume_24h,
        "active_users_1h": active_users_1h,
        "active_users_24h": active_users_24h,
        "total_exposure": str(total_exposure.quantize(Decimal("0.0001"))),
        "exposure_by_event": exposure,
    }
