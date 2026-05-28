from django.contrib import admin
from .models import LedgerEntry


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "user",
        "account",
        "amount",
        "direction",
        "tipo_transaccion",
        "creado_en",
    ]
    list_filter = ["account", "direction", "tipo_transaccion", "creado_en"]
    search_fields = ["user__username", "transaction_id", "descripcion"]
    readonly_fields = [
        "id",
        "transaction_id",
        "creado_en",
        "signed_amount",
    ]
    date_hierarchy = "creado_en"

    def signed_amount(self, obj):
        return obj.signed_amount

    signed_amount.short_description = "Monto con signo"
