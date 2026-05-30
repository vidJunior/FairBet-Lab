from django.urls import path
from django.views.generic import RedirectView
from .views import (
    RegistroHTMLView,
    LoginHTMLView,
    LogoutHTMLView,
    KYCSuccessHTMLView,
    JuegoResponsableHTMLView,
)

urlpatterns = [
    # Vistas HTML
    path(
        "",
        RedirectView.as_view(pattern_name="catalogo_html", permanent=False),
        name="home",
    ),
    path("kyc-success/", KYCSuccessHTMLView.as_view(), name="kyc_success_html"),
    path("register/", RegistroHTMLView.as_view(), name="register_html"),
    path("login/", LoginHTMLView.as_view(), name="login_html"),
    path("logout/", LogoutHTMLView.as_view(), name="logout_html"),
    path(
        "juego-responsable/",
        JuegoResponsableHTMLView.as_view(),
        name="juego_responsable_html",
    ),
]
