from django.contrib import admin

from panel.models import Bono, BonoApuesta, AlertaAbuso


@admin.register(Bono)
class BonoAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "usuario",
        "tipo",
        "monto",
        "rollover_apostado",
        "rollover_requerido",
        "estado",
        "creado",
        "expira",
    ]
    list_filter = ["tipo", "estado", "creado"]
    search_fields = ["usuario__username", "usuario__email"]
    readonly_fields = ["id", "creado", "rollover_requerido"]
    date_hierarchy = "creado"


@admin.register(BonoApuesta)
class BonoApuestaAdmin(admin.ModelAdmin):
    list_display = ["id", "bono", "apuesta", "monto_aportado", "creado"]
    list_filter = ["creado"]
    readonly_fields = ["id", "creado"]


@admin.register(AlertaAbuso)
class AlertaAbusoAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "usuario",
        "bono",
        "tipo",
        "revisado",
        "creado",
    ]
    list_filter = ["tipo", "revisado", "creado"]
    search_fields = ["usuario__username"]
    readonly_fields = ["id", "creado", "detalle"]
    actions = ["marcar_revisadas"]

    def marcar_revisadas(self, request, queryset):
        queryset.update(revisado=True)
        self.message_user(request, f"{queryset.count()} alertas marcadas como revisadas.")

    marcar_revisadas.short_description = "Marcar seleccionadas como revisadas"
