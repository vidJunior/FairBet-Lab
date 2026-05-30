from decimal import Decimal

from django.db.models import Sum

from config.choices import EstadoBono
from panel.models import Bono, BonoApuesta


def actualizar_rollover_apuesta(apuesta):
    """
    Actualiza el rollover de todos los bonos activos del usuario cuando se resuelve una apuesta.
    Solo cuentan apuestas con cuota >= cuota_minima_rollover del bono.
    """
    if apuesta.estado not in ("won", "lost"):
        return

    bonos_activos = Bono.objects.filter(
        usuario=apuesta.usuario,
        estado=EstadoBono.ACTIVO,
    )

    for bono in bonos_activos:
        ya_registrada = BonoApuesta.objects.filter(
            bono=bono,
            apuesta=apuesta,
        ).exists()

        if ya_registrada:
            continue

        if apuesta.cuota_fijada < bono.cuota_minima_rollover:
            continue

        monto_cuenta = apuesta.monto

        BonoApuesta.objects.create(
            bono=bono,
            apuesta=apuesta,
            monto_aportado=monto_cuenta,
        )

        bono.rollover_apostado += monto_cuenta

        if bono.rollover_completado:
            bono.estado = EstadoBono.COMPLETADO
            
            # Transferir todo el saldo de bonos a la billetera principal
            from wallet.models import LedgerEntry
            from wallet.services import transferencia_interna
            from config.choices import TipoCuenta
            
            saldo_bono = LedgerEntry.get_balance(apuesta.usuario, TipoCuenta.BONOS)
            if saldo_bono > 0:
                transferencia_interna(
                    apuesta.usuario, 
                    TipoCuenta.BONOS, 
                    TipoCuenta.WALLET_USUARIO, 
                    saldo_bono
                )

        bono.save()


def tiene_bono_activo_sin_rollover(usuario):
    """
    Retorna True si el usuario tiene algun bono activo cuyo rollover no ha sido completado.
    """
    return Bono.objects.filter(
        usuario=usuario,
        estado=EstadoBono.ACTIVO,
    ).exclude(
        rollover_apostado__gte=Bono.objects.filter(
            usuario=usuario,
            estado=EstadoBono.ACTIVO,
        ).values("rollover_requerido")
    ).exists()


def get_bono_info_usuario(usuario):
    """
    Retorna informacion de bonos activos del usuario para mostrar en el frontend.
    """
    bonos_activos = Bono.objects.filter(
        usuario=usuario,
        estado=EstadoBono.ACTIVO,
    )

    info = []
    for bono in bonos_activos:
        bono.expirar_si_corresponde()
        if bono.estado != EstadoBono.ACTIVO:
            continue

        info.append({
            "bono_id": str(bono.id),
            "tipo": bono.tipo,
            "monto": bono.monto,
            "rollover_requerido": bono.rollover_requerido,
            "rollover_apostado": bono.rollover_apostado,
            "rollover_progreso": bono.rollover_progreso,
            "rollover_completado": bono.rollover_completado,
            "expira": bono.expira,
        })

    return info
