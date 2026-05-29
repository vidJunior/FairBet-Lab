from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ValidationError
from decimal import Decimal

from config.choices import TipoCuenta, EstadoEvento
from wallet.models import LedgerEntry
from betting.models import Evento, Seleccion, Apuesta
from betting.services import crear_apuesta


@login_required(login_url="login_html")
def catalogo_html(request):
    saldo = LedgerEntry.get_balance(request.user, TipoCuenta.WALLET_USUARIO)
    
    eventos_en_vivo = Evento.objects.filter(
        estado=EstadoEvento.EN_VIVO
    ).prefetch_related("mercados__selecciones")
    
    eventos_programados = Evento.objects.filter(
        estado=EstadoEvento.PROGRAMADO
    ).prefetch_related("mercados__selecciones")
    
    eventos_finalizados = Evento.objects.filter(
        estado=EstadoEvento.FINALIZADO
    ).prefetch_related("mercados__selecciones").order_by('-fecha_inicio')[:20]

    from config.choices import EstadoApuesta
    apuestas_abiertas = Apuesta.objects.filter(
        usuario=request.user, 
        estado=EstadoApuesta.ACCEPTED
    ).select_related("seleccion__mercado__evento")

    apuestas_resueltas = Apuesta.objects.filter(
        usuario=request.user, 
        estado__in=[EstadoApuesta.WON, EstadoApuesta.LOST, EstadoApuesta.CANCELLED]
    ).select_related("seleccion__mercado__evento").order_by('-creado')

    context = {
        "saldo": saldo,
        "eventos_en_vivo": eventos_en_vivo,
        "eventos_programados": eventos_programados,
        "eventos_finalizados": eventos_finalizados,
        "apuestas_abiertas": apuestas_abiertas,
        "apuestas_resueltas": apuestas_resueltas,
    }
    return render(request, "betting/catalogo.html", context)


@login_required(login_url="login_html")
def apostar_html(request):
    if request.method == "POST":
        seleccion_id = request.POST.get("seleccion_id")
        monto_raw = request.POST.get("monto")

        if not seleccion_id or not monto_raw:
            messages.error(request, "Faltan datos obligatorios para la apuesta.")
            return redirect("catalogo_html")

        try:
            monto = Decimal(monto_raw)
            crear_apuesta(request.user, int(seleccion_id), monto)
            messages.success(request, "¡Tu apuesta ha sido aceptada con éxito!")
        except ValidationError as e:
            detail = str(e.message if hasattr(e, "message") else e)
            messages.error(request, detail)
        except Exception:
            messages.error(request, "Ocurrió un error inesperado al procesar la apuesta.")

    return redirect("catalogo_html")
