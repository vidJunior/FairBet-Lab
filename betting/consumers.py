import json
from channels.generic.websocket import AsyncWebsocketConsumer

class LiveOddsConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.group_name = "live_odds"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        
        user = self.scope.get("user")
        if user and user.is_authenticated:
            self.user_group_name = f"user_{user.id}"
            await self.channel_layer.group_add(self.user_group_name, self.channel_name)
            
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)
        if hasattr(self, "user_group_name"):
            await self.channel_layer.group_discard(self.user_group_name, self.channel_name)

    async def receive(self, text_data):
        # No esperamos mensajes del cliente de forma interactiva en este challenge,
        # pero dejamos el handler estructurado para re-cotizaciones futuras.
        pass

    async def odds_update(self, event):
        # Enviar actualización de cuotas al cliente conectado
        data = event["data"]
        await self.send(text_data=json.dumps(data))

    async def user_update(self, event):
        data = event["data"]
        await self.send(text_data=json.dumps(data))
