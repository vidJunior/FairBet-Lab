import time
from celery import shared_task
from django.db import transaction
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from betting.models import Mercado

@shared_task
def reactivar_mercados_evento(evento_id):
    # Esperar 15 segundos para simular el cooldown de suspensión por evento crítico
    time.sleep(15)
    
    with transaction.atomic():
        # Reactivar todos los mercados del evento
        Mercado.objects.filter(evento_id=evento_id).update(activo=True)
        
    # Transmitir la reactivación a través de WebSockets
    channel_layer = get_channel_layer()
    if channel_layer:
        async_to_sync(channel_layer.group_send)(
            "live_odds",
            {
                "type": "odds_update",
                "data": {
                    "evento_id": evento_id,
                    "estado_mercados": "ACTIVOS"
                }
            }
        )
    print(f"Mercados del evento #{evento_id} han sido reactivados automáticamente.")
