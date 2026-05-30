import time
from celery import shared_task
from django.db import transaction
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from betting.models import Mercado

@shared_task
def reactivar_mercados_evento(evento_id):
    # cooldown de suspension
    time.sleep(15)
    
    with transaction.atomic():
        Mercado.objects.filter(evento_id=evento_id, resuelto=False).update(activo=True)
        
    channel_layer = get_channel_layer()
    if channel_layer:
        from betting.models import Seleccion
        selecciones = Seleccion.objects.filter(mercado__evento_id=evento_id)
        cuotas_data = {s.id: str(s.cuota) for s in selecciones}
        
        async_to_sync(channel_layer.group_send)(
            "live_odds",
            {
                "type": "odds_update",
                "data": {
                    "evento_id": evento_id,
                    "estado_mercados": "ACTIVOS",
                    "tipo_evento": "MERCADOS_ACTIVOS",
                    "nuevas_cuotas": cuotas_data
                }
            }
        )
    print(f"Mercados evento {evento_id} reactivados")


@shared_task
def actualizar_partidos_a_en_vivo():
    from django.utils import timezone
    from betting.models import Evento
    from config.choices import EstadoEvento
    from betting.services import liquidar_apuestas_evento
    
    ahora = timezone.now()
    partidos = Evento.objects.filter(
        estado=EstadoEvento.PROGRAMADO,
        fecha_inicio__lte=ahora
    )
    
    for partido in partidos:
        with transaction.atomic():
            partido.estado = EstadoEvento.EN_VIVO
            partido.minuto_actual = 0
            partido.periodo = "1T"
            partido.save()
            
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                "live_odds",
                {
                    "type": "odds_update",
                    "data": {
                        "tipo_evento": "EVENTO_EN_VIVO",
                        "evento_id": partido.id,
                        "estado": "en_vivo",
                        "minuto_actual": partido.minuto_actual,
                        "periodo": partido.periodo
                    }
                }
            )
        print(f"Init evento {partido.id} a las {partido.minuto_actual}'")


@shared_task
def simular_minuto_partidos_en_vivo():
    import random
    from django.db import transaction
    from config.choices import EstadoEvento
    from betting.models import Evento
    from betting.services import liquidar_apuestas_evento
    
    partidos_en_vivo = Evento.objects.filter(estado=EstadoEvento.EN_VIVO)
    
    for partido in partidos_en_vivo:
        with transaction.atomic():
            partido.minuto_actual += 1
            
            if partido.minuto_actual < 45:
                partido.periodo = "1T"
            elif partido.minuto_actual == 45:
                partido.periodo = "ET"
            elif partido.minuto_actual <= 90:
                partido.periodo = "2T"
            else:
                partido.periodo = "FINALIZADO"
                partido.save()
                
                liquidar_apuestas_evento(partido.id, None)
                
                channel_layer = get_channel_layer()
                if channel_layer:
                    async_to_sync(channel_layer.group_send)(
                        "live_odds",
                        {
                            "type": "odds_update",
                            "data": {
                                "tipo_evento": "EVENTO_FINALIZADO",
                                "evento_id": partido.id,
                                "estado": "finalizado"
                            }
                        }
                    )
                continue
            
            # random goals (probabilidad del 2% y tope máximo de 5 goles por partido)
            goles_totales = partido.goles_local + partido.goles_visitante
            gol_local = False
            gol_visitante = False
            
            if goles_totales < 5:
                gol_local = random.random() < 0.02
                gol_visitante = random.random() < 0.02
            
            goles_loc_nuevos = 0
            goles_vis_nuevos = 0
            
            if gol_local and partido.periodo in ["1T", "2T"]:
                partido.goles_local += 1
                goles_loc_nuevos = 1
            if gol_visitante and partido.periodo in ["1T", "2T"] and not gol_local:
                partido.goles_visitante += 1
                goles_vis_nuevos = 1
                
            # Guardar el estado del partido
            partido.save()

            # Recalcular todas las cuotas de forma dinámica según el minuto actual y goles
            from betting.services import recalcular_cuotas_dinamicas, liquidar_apuestas_resueltas_temprano
            nuevas_cuotas = recalcular_cuotas_dinamicas(partido)

            # Liquidar automáticamente apuestas ya resueltas matemáticamente
            # (ej: "Ambos Anotan Sí" cuando ambos ya anotaron, "Más de 2.5" con 3+ goles)
            liquidar_apuestas_resueltas_temprano(partido)
            
            channel_layer = get_channel_layer()
            if channel_layer:
                periodo_display = "Entretiempo" if partido.periodo == "ET" else f"{partido.minuto_actual}' - {partido.periodo}"
                async_to_sync(channel_layer.group_send)(
                    "live_odds",
                    {
                        "type": "odds_update",
                        "data": {
                            "tipo_evento": "EVENTO_TIEMPO",
                            "evento_id": partido.id,
                            "minuto_actual": partido.minuto_actual,
                            "periodo": partido.periodo,
                            "periodo_display": periodo_display,
                            "goles_local": partido.goles_local,
                            "goles_visitante": partido.goles_visitante,
                            "nuevas_cuotas": nuevas_cuotas
                        }
                    }
                )


