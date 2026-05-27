from django.urls import path
from wallet.views import (
    BilleteraHTMLView,
    RecargaHTMLView,
    RetiroHTMLView,
)

urlpatterns = [
    # Vistas HTML — Wallet
    path("", BilleteraHTMLView.as_view(), name="wallet_billetera"),
    path("recargar/", RecargaHTMLView.as_view(), name="wallet_recargar"),
    path("retirar/", RetiroHTMLView.as_view(), name="wallet_retirar"),
]
