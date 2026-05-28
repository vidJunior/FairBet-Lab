import os
from celery import Celery

# Establecer las variables de entorno de Django para Celery
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("fairbet")

# Cargar configuraciones de Django con el prefijo CELERY_
app.config_from_object("django.conf:settings", namespace="CELERY")

# Autodescubrir tareas registradas en cada app de Django (tasks.py)
app.autodiscover_tasks()
