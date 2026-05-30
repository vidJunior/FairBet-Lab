from decimal import Decimal
from datetime import timedelta

from django.db import transaction
from django.db.models import Sum, Count, Q
from django.utils import timezone

from config.choices import TipoCuenta, EstadoApuesta, EstadoEvento
from wallet.models import LedgerEntry
from betting.models import Apuesta, Evento, Seleccion


def calculate_ggr(period_hours=24):
    """
    Gross Gaming Revenue = stakes (total apostado) − payouts (pagos a ganadores)
    Calculado sobre apuestas resueltas (WON, LOST, CASHED_OUT) en el período.
    Según la guía: GGR = stakes − payouts.
    """
    desde = timezone.now() - timedelta(hours=period_hours)

    # Stakes: suma de montos de todas las apuestas resueltas en el período
    apuestas_resueltas = Apuesta.objects.filter(
        estado__in=[EstadoApuesta.WON, EstadoApuesta.LOST, EstadoApuesta.CASHED_OUT],
        actualizado__gte=desde,
    )

    total_stakes = apuestas_resueltas.aggregate(
        total=Sum("monto")
    )["total"] or Decimal("0.0000")

    # Payouts: para apuestas ganadas = monto × cuota_fijada
    from django.db.models import F
    total_payouts_won = Apuesta.objects.filter(
        estado=EstadoApuesta.WON,
        actualizado__gte=desde,
    ).aggregate(
        total=Sum(F("monto") * F("cuota_fijada"))
    )["total"] or Decimal("0.0000")

    # Payouts: para apuestas con cash-out, el payout real se calcula
    # desde los créditos en la billetera del usuario asociados a esas apuestas
    total_payouts_cashout = Decimal("0.0000")
    apuestas_cashout = Apuesta.objects.filter(
        estado=EstadoApuesta.CASHED_OUT,
        actualizado__gte=desde,
    )
    for apuesta_co in apuestas_cashout:
        # El cashout se registró como crédito al usuario desde la casa
        # Aproximamos con la fórmula estándar de cashout
        sel = apuesta_co.seleccion
        if sel:
            cuota_actual = sel.cuota
            cuota_original = apuesta_co.cuota_fijada
            if cuota_actual > 0 and cuota_original > 0:
                cashout_val = apuesta_co.monto * cuota_original / cuota_actual * Decimal("0.95")
                total_payouts_cashout += cashout_val

    total_payouts = total_payouts_won + total_payouts_cashout
    ggr = (total_stakes - total_payouts).quantize(Decimal("0.01"))
    return ggr


def calculate_exposure_by_event():
    """
    Exposure por evento: cuánto pierde la casa si gana cada selección.
    Para cada evento activo, calcula la pérdida neta potencial de la casa.
    Exposure = máx(payout_potencial_selección - total_apostado_evento) para el peor caso.
    No filtra por mercado activo: el riesgo contable existe aunque el mercado esté suspendido.
    """
    eventos_activos = Evento.objects.filter(
        estado__in=[EstadoEvento.PROGRAMADO, EstadoEvento.EN_VIVO]
    ).prefetch_related("mercados__selecciones")

    exposure_data = []

    for evento in eventos_activos:
        # Todas las selecciones del evento, sin filtrar por mercado activo
        selecciones = Seleccion.objects.filter(
            mercado__evento=evento,
        ).select_related("mercado")

        # Total apostado en TODO el evento (todas las selecciones, apuestas accepted)
        total_apostado_evento = Decimal("0.0000")
        detalles_seleccion = []

        for sel in selecciones:
            apuestas_a_sel = Apuesta.objects.filter(
                Q(seleccion=sel) | Q(selecciones=sel),
                estado=EstadoApuesta.ACCEPTED,
            ).distinct()

            apostado_sel = apuestas_a_sel.aggregate(
                total=Sum("monto")
            )["total"] or Decimal("0.0000")
            total_apostado_evento += apostado_sel

            payout_potencial = Decimal("0.0000")
            for apuesta in apuestas_a_sel:
                payout_potencial += apuesta.monto * apuesta.cuota_fijada

            if apostado_sel > 0:
                detalles_seleccion.append(
                    {
                        "seleccion_id": sel.id,
                        "seleccion_nombre": sel.nombre,
                        "mercado": sel.mercado.nombre,
                        "cuota_actual": str(sel.cuota),
                        "total_apostado": str(apostado_sel.quantize(Decimal("0.01"))),
                        "payout_potencial": str(payout_potencial.quantize(Decimal("0.01"))),
                        "exposure": str(payout_potencial.quantize(Decimal("0.01"))),
                    }
                )

        if detalles_seleccion:
            # La exposure del evento es el peor escenario:
            # max(payout_potencial de cada selección) - total apostado en el evento
            # (si gana la selección con mayor payout, la casa pierde el payout pero
            #  se queda con los stakes de todas las demás apuestas perdidas)
            max_payout = max(
                Decimal(d["payout_potencial"]) for d in detalles_seleccion
            )
            exposure_neta = (max_payout - total_apostado_evento).quantize(Decimal("0.01"))
            # Si la exposure es negativa, la casa gana en cualquier escenario
            exposure_neta = max(exposure_neta, Decimal("0.00"))

            exposure_data.append(
                {
                    "evento_id": evento.id,
                    "evento_nombre": f"{evento.local} vs {evento.visitante}",
                    "estado": evento.estado,
                    "minuto": evento.minuto_actual,
                    "total_apostado": str(total_apostado_evento.quantize(Decimal("0.01"))),
                    "max_payout": str(max_payout.quantize(Decimal("0.01"))),
                    "total_exposure": str(exposure_neta),
                    "selecciones": detalles_seleccion,
                }
            )

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
        "total_staked": str(
            (resultado["total_staked"] or Decimal("0.00")).quantize(Decimal("0.01"))
        ),
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
        Apuesta.objects.filter(creado__gte=desde).values("usuario").distinct().count()
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
        (Decimal(e["total_exposure"]) for e in exposure), Decimal("0.00")
    )

    return {
        "ggr_24h": str(ggr_24h),
        "ggr_7d": str(ggr_7d),
        "volume_24h": volume_24h,
        "active_users_1h": active_users_1h,
        "active_users_24h": active_users_24h,
        "total_exposure": str(total_exposure.quantize(Decimal("0.01"))),
        "exposure_by_event": exposure,
    }


def crear_bono_bienvenida_automatico(user):
    """
    Crea el bono de bienvenida por defecto (60.00 con rollover x2) para el usuario
    y registra la partida doble contable en la billetera (Casa -> Bonos del Usuario).
    """
    from panel.models import Bono
    from config.choices import TipoBono, TipoCuenta
    from wallet.services import registrar_movimiento
    import uuid

    monto_bono = Decimal("60.0000")
    multiplicador = Decimal("2.00")

    # Crear bono en BD
    bono = Bono.objects.create(
        usuario=user,
        tipo=TipoBono.BIENVENIDA,
        monto=monto_bono,
        rollover_multiplier=multiplicador,
    )

    # Registrar los asientos contables en Billetera (Partida Doble)
    # Débito a la Casa (pérdida promocional) y Crédito a la cuenta de Bonos del Usuario
    tid = uuid.uuid4()
    registrar_movimiento(
        tid,
        usuario_debito=None,
        cuenta_debito=TipoCuenta.CASA,
        usuario_credito=user,
        cuenta_credito=TipoCuenta.BONOS,
        monto=monto_bono,
    )
    return bono


@transaction.atomic
def crear_bono_recarga_masivo(monto, rollover_multiplier, expira):
    """
    Asigna un Bono de Recarga a todos los usuarios verificados que hayan recargado en los últimos 7 días.
    """
    from django.contrib.auth import get_user_model
    from django.utils import timezone
    from config.choices import TipoBono, TipoCuenta, Direccion
    from panel.models import Bono
    from wallet.models import LedgerEntry
    from wallet.services import registrar_movimiento
    from accounts.models import PerfilUsuario
    import uuid

    User = get_user_model()
    monto = Decimal(str(monto))
    rollover_multiplier = Decimal(str(rollover_multiplier))

    # Filtramos usuarios que hayan recargado en los últimos 7 días
    hace_una_semana = timezone.now() - timezone.timedelta(days=7)
    usuarios_recargaron = (
        LedgerEntry.objects.filter(
            cuenta=TipoCuenta.WALLET_USUARIO,
            direccion=Direccion.CREDIT,
            creado__gte=hace_una_semana,
            usuario__isnull=False,
        )
        .values_list("usuario_id", flat=True)
        .distinct()
    )

    # Filtramos que tengan perfil verificado
    usuarios_destinatarios = User.objects.filter(
        id__in=usuarios_recargaron, perfil__estado="verificado"
    )

    bonos_creados = []
    for u in usuarios_destinatarios:
        bono = Bono.objects.create(
            usuario=u,
            tipo=TipoBono.RECARGA,
            monto=monto,
            rollover_multiplier=rollover_multiplier,
            expira=expira,
        )

        tid = uuid.uuid4()
        registrar_movimiento(
            tid,
            usuario_debito=None,
            cuenta_debito=TipoCuenta.CASA,
            usuario_credito=u,
            cuenta_credito=TipoCuenta.BONOS,
            monto=monto,
        )
        bonos_creados.append(bono)

    return bonos_creados


def crear_codigo_bono(codigo, monto, rollover_multiplier, usos_maximos, expira):
    """
    Crea un código de bono promocional con límite de usos y fecha de expiración obligatoria.
    """
    from panel.models import CodigoBono
    from django.core.exceptions import ValidationError

    codigo = codigo.strip().upper()
    if CodigoBono.objects.filter(codigo=codigo).exists():
        raise ValidationError("Este código promocional ya existe.")

    return CodigoBono.objects.create(
        codigo=codigo,
        monto=Decimal(str(monto)),
        rollover_multiplier=Decimal(str(rollover_multiplier)),
        usos_maximos=int(usos_maximos),
        expira=expira,
    )


@transaction.atomic
def reclamar_codigo_bono(user, codigo_texto):
    """
    Canjea un código promocional para el usuario, validando límites de uso, expiración y duplicidad.
    """
    from django.core.exceptions import ValidationError
    from django.utils import timezone
    from config.choices import TipoBono, TipoCuenta
    from panel.models import Bono, CodigoBono
    from wallet.services import registrar_movimiento
    import uuid

    codigo_texto = codigo_texto.strip().upper()

    try:
        # select_for_update para evitar condiciones de carrera en usos_actuales
        codigo_bono = CodigoBono.objects.select_for_update().get(codigo=codigo_texto)
    except CodigoBono.DoesNotExist:
        raise ValidationError("El código ingresado no es válido.")

    # Validar expiración
    if codigo_bono.expira < timezone.now():
        raise ValidationError("Este código promocional ha expirado.")

    # Validar usos
    if codigo_bono.usos_actuales >= codigo_bono.usos_maximos:
        raise ValidationError(
            "Este código promocional ya ha alcanzado su límite de usos."
        )

    # Validar que el usuario no lo haya canjeado previamente
    if Bono.objects.filter(usuario=user, codigo_bono=codigo_bono).exists():
        raise ValidationError("Ya has canjeado este código promocional anteriormente.")

    # Incrementar uso
    codigo_bono.usos_actuales += 1
    codigo_bono.save()

    # Crear el Bono asociado
    bono = Bono.objects.create(
        usuario=user,
        tipo=TipoBono.MANUAL,  # Usamos MANUAL como choice estándar para códigos canjeados por el usuario
        monto=codigo_bono.monto,
        rollover_multiplier=codigo_bono.rollover_multiplier,
        expira=codigo_bono.expira,
        codigo_bono=codigo_bono,
    )

    # Registrar partida doble contable
    tid = uuid.uuid4()
    registrar_movimiento(
        tid,
        usuario_debito=None,
        cuenta_debito=TipoCuenta.CASA,
        usuario_credito=user,
        cuenta_credito=TipoCuenta.BONOS,
        monto=codigo_bono.monto,
    )

    return bono
