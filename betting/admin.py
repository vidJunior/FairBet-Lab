from django.contrib import admin
from betting.models import Evento, Mercado, Seleccion, Apuesta


@admin.register(Evento)
class EventoAdmin(admin.ModelAdmin):
    list_display = ["id", "local", "visitante", "fecha_inicio", "estado", "goles_local", "goles_visitante"]
    list_filter = ["estado", "fecha_inicio"]
    search_fields = ["local", "visitante"]


@admin.register(Mercado)
class MercadoAdmin(admin.ModelAdmin):
    list_display = ["id", "nombre", "evento", "activo"]
    list_filter = ["activo"]


@admin.register(Seleccion)
class SeleccionAdmin(admin.ModelAdmin):
    list_display = ["id", "nombre", "cuota", "mercado"]
    search_fields = ["nombre"]


@admin.register(Apuesta)
class ApuestaAdmin(admin.ModelAdmin):
    list_display = ["id", "usuario", "seleccion", "monto", "cuota_fijada", "estado", "creado"]
    list_filter = ["estado", "creado"]
    search_fields = ["usuario__username"]
