import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

from django.conf import settings
from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# Inicializar Django ASGI antes de importar ruteadores que usan modelos
django_asgi_app = get_asgi_application()

if settings.DEBUG:
    django_asgi_app = ASGIStaticFilesHandler(django_asgi_app)

import betting.routing

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(
            betting.routing.websocket_urlpatterns
        )
    ),
})
