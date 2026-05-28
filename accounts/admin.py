from django.contrib import admin
from accounts.models import PerfilUsuario


@admin.register(PerfilUsuario)
class PerfilUsuarioAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "dni", "estado", "tipo_autoexclusion"]
    list_filter = ["estado", "tipo_autoexclusion"]
    search_fields = ["user__username", "dni"]
