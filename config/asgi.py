import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# Inicializar Django ASGI antes de importar ruteadores que usan modelos
django_asgi_app = get_asgi_application()

import betting.routing

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(
            betting.routing.websocket_urlpatterns
        )
    ),
})
