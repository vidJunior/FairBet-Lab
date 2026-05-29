from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ValidationError
from decimal import Decimal

from config.choices import TipoCuenta, EstadoEvento
from wallet.models import LedgerEntry
from betting.models import Evento, Seleccion, Apuesta, Equipo
from betting.services import crear_apuesta
from betting.forms import CrearEventoForm


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
    ).select_related("seleccion__mercado__evento").prefetch_related("detalles__seleccion__mercado__evento")

    apuestas_resueltas = Apuesta.objects.filter(
        usuario=request.user, 
        estado__in=[EstadoApuesta.WON, EstadoApuesta.LOST, EstadoApuesta.CANCELLED]
    ).select_related("seleccion__mercado__evento").prefetch_related("detalles__seleccion__mercado__evento").order_by('-creado')

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
        seleccion_ids_raw = request.POST.get("seleccion_ids")
        cuotas_esperadas_raw = request.POST.get("cuotas_esperadas")
        monto_raw = request.POST.get("monto")

        if not seleccion_ids_raw or not monto_raw:
            messages.error(request, "Faltan datos obligatorios para la apuesta.")
        else:
            try:
                monto = Decimal(monto_raw)
                seleccion_ids = [int(x.strip()) for x in seleccion_ids_raw.split(",") if x.strip()]

                if len(seleccion_ids) == 0:
                    messages.error(request, "Debes seleccionar al menos una cuota.")
                elif len(seleccion_ids) == 1:
                    crear_apuesta(request.user, seleccion_ids[0], monto)
                    messages.success(request, "¡Tu apuesta ha sido aceptada con éxito!")
                else:
                    cuotas_esperadas = {}
                    if cuotas_esperadas_raw:
                        import json
                        cuotas_esperadas = json.loads(cuotas_esperadas_raw)
                    from betting.services import crear_apuesta_combinada
                    crear_apuesta_combinada(request.user, seleccion_ids, monto, cuotas_esperadas=cuotas_esperadas)
                    messages.success(request, "¡Tu apuesta combinada ha sido aceptada con éxito!")
            except ValidationError as e:
                detail = str(e.message if hasattr(e, "message") else e)
                messages.error(request, detail)
            except Exception:
                messages.error(request, "Ocurrió un error inesperado al procesar la apuesta.")

    return redirect("catalogo_html")


@login_required(login_url="login_html")
def crear_evento_html(request):
    from betting.services import crear_mercados_para_evento

    if request.method == "POST":
        form = CrearEventoForm(request.POST)
        if form.is_valid():
            try:
                evento = form.save()
                crear_mercados_para_evento(evento)
                messages.success(
                    request,
                    f"Evento '{evento.local} vs {evento.visitante}' creado exitosamente."
                )
                return redirect("catalogo_html")
            except ValidationError as e:
                messages.error(request, str(e))
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, error)
    else:
        form = CrearEventoForm()

    equipos = Equipo.objects.all()
    context = {
        "form": form,
        "equipos": equipos,
    }
    return render(request, "betting/crear_evento.html", context)
