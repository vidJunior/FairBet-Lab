from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.views import View
from django.views.generic import TemplateView
from django.contrib.auth.models import User
from config.choices import EstadoPerfil
from .models import PerfilUsuario, TipoAutoexclusion

from django.db import transaction
from .forms import RegistroForm, LoginForm


class RegistroHTMLView(View):
    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("/")
        form = RegistroForm()
        return render(request, "accounts/register.html", {"form": form})

    def post(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("/")

        form = RegistroForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data["username"]
            email = form.cleaned_data["email"]
            first_name = form.cleaned_data["first_name"]
            last_name = form.cleaned_data["last_name"]
            password = form.cleaned_data["password"]
            fecha_nacimiento = form.cleaned_data["fecha_nacimiento"]
            dni = form.cleaned_data["dni"]

            try:
                with transaction.atomic():
                    user = User.objects.create_user(
                        username=username,
                        email=email,
                        password=password,
                        first_name=first_name,
                        last_name=last_name,
                    )
                    PerfilUsuario.objects.create(
                        user=user,
                        fecha_nacimiento=fecha_nacimiento,
                        dni=dni,
                        estado=EstadoPerfil.VERIFICADO,
                    )
                # Auto-login
                login(request, user)
                messages.success(request, "¡Cuenta creada y verificado con éxito!")
                return redirect("kyc_success_html")
            except Exception as e:
                messages.error(request, f"Error interno: {str(e)}")
        else:
            messages.error(request, "Corrige los errores del formulario.")

        return render(request, "accounts/register.html", {"form": form})


class LoginHTMLView(View):
    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("/")
        form = LoginForm()
        return render(request, "accounts/login.html", {"form": form})

    def post(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("/")

        form = LoginForm(request.POST)
        if form.is_valid():
            user = form.cleaned_data["user"]
            perfil = getattr(user, "perfil", None)

            if perfil and perfil.estado == EstadoPerfil.AUTOEXCLUIDO and not perfil.esta_autoexcluido:
                perfil.estado = EstadoPerfil.VERIFICADO
                perfil.tipo_autoexclusion = TipoAutoexclusion.NINGUNA
                perfil.save()

            login(request, user)
            messages.success(request, f"¡Bienvenido de nuevo, {user.username}!")
            return redirect("/")
        else:
            non_field_errs = form.non_field_errors()
            if non_field_errs:
                for error in non_field_errs:
                    messages.error(request, error)
            else:
                messages.error(request, "Nombre de usuario o contraseña incorrectos.")

        return render(request, "accounts/login.html", {"form": form})


class LogoutHTMLView(View):
    def get(self, request):
        logout(request)
        return redirect("login_html")


class HomeHTMLView(LoginRequiredMixin, TemplateView):
    template_name = "accounts/index.html"
    login_url = "login_html"


class KYCSuccessHTMLView(LoginRequiredMixin, TemplateView):
    template_name = "accounts/kyc_success.html"
    login_url = "login_html"
