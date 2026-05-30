from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.views import View
from django.views.generic import TemplateView
from django.contrib.auth.models import User
from config.choices import EstadoPerfil
from .models import PerfilUsuario, TipoAutoexclusion
from .forms import LimitesDepositoForm, AutoexclusionForm

from django.utils import timezone
from datetime import timedelta

from django.db import transaction
from django.core.exceptions import ValidationError
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
                    from panel.services import crear_bono_bienvenida_automatico

                    crear_bono_bienvenida_automatico(user)
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

            if (
                perfil
                and perfil.estado == EstadoPerfil.AUTOEXCLUIDO
                and not perfil.esta_autoexcluido
            ):
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


class KYCSuccessHTMLView(LoginRequiredMixin, TemplateView):
    template_name = "accounts/kyc_success.html"
    login_url = "login_html"


class JuegoResponsableHTMLView(LoginRequiredMixin, View):
    template_name = "accounts/juego_responsable.html"
    login_url = "login_html"

    def get_perfil(self, request):
        perfil = getattr(request.user, "perfil", None)
        if not perfil:
            return None

        # Auto-aplicar límite pendiente si ya venció el cooldown
        perfil.aplicar_limite_pendiente()
        return perfil

    def get(self, request):
        perfil = self.get_perfil(request)
        if not perfil:
            messages.error(request, "No tienes un perfil creado.")
            return redirect("/")

        limites_form = LimitesDepositoForm(instance=perfil)
        autoexclusion_form = AutoexclusionForm(instance=perfil)

        # Calcular tiempo restante para el cooldown
        cooldown_restante = None
        if perfil.fecha_solicitud_incremento:
            restante = (
                perfil.fecha_solicitud_incremento + timedelta(hours=24) - timezone.now()
            )
            if restante.total_seconds() > 0:
                mins = int(restante.total_seconds() // 60)
                cooldown_restante = f"{mins // 60}h {mins % 60}m"

        return render(
            request,
            self.template_name,
            {
                "limites_form": limites_form,
                "autoexclusion_form": autoexclusion_form,
                "perfil": perfil,
                "cooldown_restante": cooldown_restante,
            },
        )

    def post(self, request):
        perfil = self.get_perfil(request)
        if not perfil:
            return redirect("/")

        action = request.POST.get("action")

        if action == "actualizar_limites":
            limites_form = LimitesDepositoForm(request.POST)
            if limites_form.is_valid():
                try:
                    limites = {
                        "diario": limites_form.cleaned_data["limite_deposito_diario"],
                        "semanal": limites_form.cleaned_data["limite_deposito_semanal"],
                        "mensual": limites_form.cleaned_data["limite_deposito_mensual"],
                    }

                    hubo_aumento = False
                    for tipo, val in limites.items():
                        if val > getattr(perfil, f"limite_deposito_{tipo}"):
                            hubo_aumento = True

                    with transaction.atomic():
                        for tipo, val in limites.items():
                            perfil.solicitar_cambio_limite(tipo, val)

                    if hubo_aumento:
                        messages.success(
                            request,
                            "Límites actualizados. Los aumentos tardarán 24 horas en procesarse.",
                        )
                    else:
                        messages.success(
                            request,
                            "Límites reducidos con éxito de forma inmediata.",
                        )
                except ValidationError as e:
                    messages.error(request, ", ".join(e.messages))
                except Exception as e:
                    messages.error(request, str(e))
            else:
                messages.error(request, "Por favor corrige los errores del formulario.")

        elif action == "autoexcluirse":
            autoexclusion_form = AutoexclusionForm(request.POST, instance=perfil)
            if autoexclusion_form.is_valid():
                try:
                    autoexclusion_form.save()
                    logout(request)
                    messages.warning(
                        request,
                        "Te has autoexcluido voluntariamente. Tu sesión ha sido cerrada.",
                    )
                    return redirect("login_html")
                except ValidationError as e:
                    messages.error(request, ", ".join(e.messages))
                except Exception as e:
                    messages.error(request, str(e))
            else:
                messages.error(request, "Selección de autoexclusión inválida.")

        elif action == "aplicar_pendiente":
            if perfil.aplicar_limite_pendiente():
                messages.success(request, "Límite pendiente aplicado correctamente.")
            else:
                messages.error(
                    request, "El periodo de cooldown de 24 horas aún no finaliza."
                )

        return redirect("juego_responsable_html")
