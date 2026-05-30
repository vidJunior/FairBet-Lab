from django.urls import path
from api.views import verify_audit_chain_api
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
)
from accounts.api_views import (
    RegistroUsuarioAPIView,
    LoginAPIView,
)
from wallet.api_views import (
    SaldoAPIView,
    RecargaAPIView,
    RetiroAPIView,
)
from betting.api_views import (
    CatalogoEventosAPIView,
    CrearApuestaAPIView,
)
from panel.urls import api_urlpatterns as panel_api_urls

urlpatterns = [
    # OpenAPI Schema
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    # Swagger UI Docs
    path("docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    # Endpoints de Autenticación y Registro
    path("accounts/register/", RegistroUsuarioAPIView.as_view(), name="api_register"),
    path("accounts/login/", LoginAPIView.as_view(), name="api_login"),
    # Endpoints de Billetera
    path("wallet/saldo/", SaldoAPIView.as_view(), name="api_wallet_saldo"),
    path("wallet/recargar/", RecargaAPIView.as_view(), name="api_wallet_recargar"),
    path("wallet/retirar/", RetiroAPIView.as_view(), name="api_wallet_retirar"),
    # Endpoints de Apuestas
    path("betting/catalogo/", CatalogoEventosAPIView.as_view(), name="api_betting_catalogo"),
    path("betting/apostar/", CrearApuestaAPIView.as_view(), name="api_betting_apostar"),
    path('admin/audit/verify/', verify_audit_chain_api, name='audit_verify_chain'),
]