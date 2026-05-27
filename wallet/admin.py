from django.contrib import admin
from wallet.models import LedgerEntry


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display = (
        "id_transaccion",
        "usuario",
        "cuenta",
        "direccion",
        "monto",
        "creado",
    )
    list_filter = ("cuenta", "direccion")
    search_fields = ("id_transaccion", "usuario__username")
    readonly_fields = ("id_transaccion", "creado")
    ordering = ("-creado",)
