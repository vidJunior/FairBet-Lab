from django.urls import path
from betting import views

urlpatterns = [
    path("", views.catalogo_html, name="catalogo_html"),
    path("apostar/", views.apostar_html, name="apostar_html"),
    path("crear-evento/", views.crear_evento_html, name="crear_evento_html"),
    path("cashout/", views.cashout_html, name="cashout_html"),
]
