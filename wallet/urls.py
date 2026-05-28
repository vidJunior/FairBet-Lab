from django.urls import path
from .views import (
    DepositoHTMLView,
    RetiroHTMLView,
    SaldoHTMLView,
    WalletHomeHTMLView,
)

urlpatterns = [
    path("wallet/", WalletHomeHTMLView.as_view(), name="wallet_home_html"),
    path("wallet/deposito/", DepositoHTMLView.as_view(), name="wallet_deposito_html"),
    path("wallet/retiro/", RetiroHTMLView.as_view(), name="wallet_retiro_html"),
    path("wallet/saldo/", SaldoHTMLView.as_view(), name="wallet_saldo_html"),
]
