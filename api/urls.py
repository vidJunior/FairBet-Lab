from django.urls import path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
)
from accounts.api_views import (
    RegistroUsuarioAPIView,
    LoginAPIView,
)
from wallet.api_views import (
    DepositoAPIView,
    RetiroAPIView,
    SaldoAPIView,
    HistorialAPIView,
)

urlpatterns = [
    # OpenAPI Schema
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    # Swagger UI Docs
    path("docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    # Endpoints de Autenticacion y Registro
    path("accounts/register/", RegistroUsuarioAPIView.as_view(), name="api_register"),
    path("accounts/login/", LoginAPIView.as_view(), name="api_login"),
    # Endpoints de Billetera
    path("wallet/deposito/", DepositoAPIView.as_view(), name="api_deposito"),
    path("wallet/retiro/", RetiroAPIView.as_view(), name="api_retiro"),
    path("wallet/saldo/", SaldoAPIView.as_view(), name="api_saldo"),
    path("wallet/historial/", HistorialAPIView.as_view(), name="api_historial"),
]
