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
    ).prefetch_related("mercados__selecciones").order_by("fecha_inicio")
    
    eventos_programados = Evento.objects.filter(
        estado=EstadoEvento.PROGRAMADO
    ).prefetch_related("mercados__selecciones").order_by("fecha_inicio")
    
    eventos_finalizados = Evento.objects.filter(
        estado=EstadoEvento.FINALIZADO
    ).prefetch_related("mercados__selecciones").order_by('-fecha_inicio')[:20]

    from config.choices import EstadoApuesta
    apuestas_abiertas = Apuesta.objects.filter(
        usuario=request.user, 
        estado=EstadoApuesta.ACCEPTED
    ).select_related("seleccion__mercado__evento").prefetch_related("detalles__seleccion__mercado__evento").order_by("-creado")

    apuestas_resueltas = Apuesta.objects.filter(
        usuario=request.user, 
        estado__in=[EstadoApuesta.WON, EstadoApuesta.LOST, EstadoApuesta.CANCELLED, EstadoApuesta.CASHED_OUT]
    ).select_related("seleccion__mercado__evento").prefetch_related("detalles__seleccion__mercado__evento").order_by('-creado')

    from betting.services import calcular_cashout
    for ap in apuestas_abiertas:
        ap.cashout_val = calcular_cashout(ap)

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
        tipo_apuesta = request.POST.get("tipo_apuesta", "combinada")
        
        if not seleccion_ids_raw:
            messages.error(request, "Faltan selecciones para la apuesta.")
            return redirect("catalogo_html")

        try:
            seleccion_ids = [int(x.strip()) for x in seleccion_ids_raw.split(",") if x.strip()]
            
            if len(seleccion_ids) == 0:
                messages.error(request, "Debes seleccionar al menos una cuota.")
                return redirect("catalogo_html")

            cuotas_esperadas = {}
            if cuotas_esperadas_raw:
                import json
                cuotas_esperadas = json.loads(cuotas_esperadas_raw)

            if tipo_apuesta == "simples":
                montos_simples_raw = request.POST.get("montos_simples")
                if not montos_simples_raw:
                    messages.error(request, "Faltan los montos para las apuestas simples.")
                    return redirect("catalogo_html")
                import json
                montos_simples = json.loads(montos_simples_raw)
                
                exitos = 0
                errores = []
                for sid in seleccion_ids:
                    monto = montos_simples.get(str(sid))
                    if not monto:
                        continue
                    try:
                        monto_dec = Decimal(str(monto))
                        cuota_esp = cuotas_esperadas.get(str(sid))
                        crear_apuesta(request.user, sid, monto_dec, cuota_esperada=cuota_esp)
                        exitos += 1
                    except ValidationError as e:
                        errores.append(str(e.message if hasattr(e, "message") else e))
                
                if exitos > 0:
                    messages.success(request, f"¡{exitos} apuesta(s) simple(s) aceptada(s) con éxito!")
                for err in errores:
                    messages.error(request, f"Error en una selección: {err}")

            else:
                # Es Combinada
                monto_raw = request.POST.get("monto")
                if not monto_raw:
                    messages.error(request, "Falta el monto para la apuesta combinada.")
                    return redirect("catalogo_html")
                    
                monto = Decimal(monto_raw)
                if len(seleccion_ids) == 1:
                    crear_apuesta(request.user, seleccion_ids[0], monto, cuota_esperada=cuotas_esperadas.get(str(seleccion_ids[0])))
                    messages.success(request, "¡Tu apuesta simple ha sido aceptada con éxito!")
                else:
                    from betting.services import crear_apuesta_combinada
                    crear_apuesta_combinada(request.user, seleccion_ids, monto, cuotas_esperadas=cuotas_esperadas)
                    messages.success(request, "¡Tu apuesta combinada ha sido aceptada con éxito!")

        except ValidationError as e:
            detail = str(e.message if hasattr(e, "message") else e)
            messages.error(request, detail)
        except Exception as e:
            messages.error(request, "Ocurrió un error inesperado al procesar la apuesta.")

    return redirect("catalogo_html")


@login_required(login_url="login_html")
def cashout_html(request):
    if request.method == "POST":
        apuesta_id = request.POST.get("apuesta_id")
        if not apuesta_id:
            messages.error(request, "Falta el identificador de la apuesta.")
            return redirect("catalogo_html")

        from betting.services import procesar_cashout, calcular_cashout
        from betting.models import Apuesta
        from config.choices import EstadoApuesta

        try:
            apuesta = Apuesta.objects.select_related("seleccion__mercado__evento").prefetch_related(
                "detalles__seleccion__mercado__evento"
            ).get(pk=apuesta_id, usuario=request.user, estado=EstadoApuesta.ACCEPTED)
        except Apuesta.DoesNotExist:
            messages.error(request, "Apuesta no encontrada o ya no está activa.")
            return redirect("catalogo_html")

        try:
            apuesta, cashout = procesar_cashout(apuesta, request.user)
            messages.success(
                request,
                f"¡Cashout exitoso! Recibiste f. {cashout} por tu apuesta #{apuesta.id}."
            )
        except ValidationError as e:
            messages.error(request, str(e))

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
