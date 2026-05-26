from django.urls import path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
)
from accounts.api_views import (
    RegistroUsuarioAPIView,
    LoginAPIView,
)

urlpatterns = [
    # OpenAPI Schema
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    # Swagger UI Docs
    path("docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    # Endpoints de Autenticación y Registro
    path("accounts/register/", RegistroUsuarioAPIView.as_view(), name="api_register"),
    path("accounts/login/", LoginAPIView.as_view(), name="api_login"),
]
