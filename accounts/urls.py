from django.urls import path
from .views import (
    RegistroHTMLView,
    LoginHTMLView,
    LogoutHTMLView,
    HomeHTMLView,
    KYCSuccessHTMLView,
)

urlpatterns = [
    # Vistas HTML
    path("", HomeHTMLView.as_view(), name="home"),
    path("kyc-success/", KYCSuccessHTMLView.as_view(), name="kyc_success_html"),
    path("register/", RegistroHTMLView.as_view(), name="register_html"),
    path("login/", LoginHTMLView.as_view(), name="login_html"),
    path("logout/", LogoutHTMLView.as_view(), name="logout_html"),
]
