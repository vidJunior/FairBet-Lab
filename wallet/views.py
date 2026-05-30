from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.views import View

from config.choices import TipoCuenta
from wallet.models import LedgerEntry
from wallet import services


class BilleteraHTMLView(LoginRequiredMixin, View):
    """Vista de la billetera del usuario"""

    template_name = "wallet/billetera.html"
    login_url = "login_html"

    def obtener_contexto(self, user):
        from panel.rollover import get_bono_info_usuario
        return {
            "saldo_disponible": LedgerEntry.get_balance(
                user, TipoCuenta.WALLET_USUARIO
            ),
            "saldo_apuestas": LedgerEntry.get_balance(
                user, TipoCuenta.APUESTAS_PENDIENTES
            ),
            "saldo_bonos": LedgerEntry.get_balance(user, TipoCuenta.BONOS),
            "bonos_info": get_bono_info_usuario(user),
        }

    def get(self, request):
        return render(request, self.template_name, self.obtener_contexto(request.user))


class RecargaHTMLView(LoginRequiredMixin, View):
    """Procesa el formulario de recarga de fichas."""

    login_url = "login_html"

    def post(self, request):
        try:
            amount = Decimal(request.POST.get("amount", "0"))
        except InvalidOperation:
            messages.error(request, "Monto inválido.")
            return redirect("wallet_billetera")

        try:
            services.recargar(request.user, amount)
            messages.success(
                request, f"Recarga de {amount:.2f} fichas realizada con éxito."
            )
        except ValidationError as e:
            messages.error(request, e.message if hasattr(e, "message") else str(e))

        return redirect("wallet_billetera")


class RetiroHTMLView(LoginRequiredMixin, View):
    """Procesa el formulario de retiro de fichas."""

    login_url = "login_html"

    def post(self, request):
        try:
            amount = Decimal(request.POST.get("amount", "0"))
        except InvalidOperation:
            messages.error(request, "Monto inválido.")
            return redirect("wallet_billetera")

        try:
            services.retirar(request.user, amount)
            messages.success(
                request, f"Retiro de {amount:.2f} fichas realizado con éxito."
            )
        except ValidationError as e:
            messages.error(request, e.message if hasattr(e, "message") else str(e))

        return redirect("wallet_billetera")


class ReclamarCodigoBonoHTMLView(LoginRequiredMixin, View):
    """Procesa el formulario de canjeo de código promocional."""

    login_url = "login_html"

    def post(self, request):
        codigo = request.POST.get("codigo", "").strip()
        if not codigo:
            messages.error(request, "Por favor ingresa un código promocional.")
            return redirect("wallet_billetera")

        from panel.services import reclamar_codigo_bono
        try:
            reclamar_codigo_bono(request.user, codigo)
            messages.success(request, f"¡Código promocional '{codigo.upper()}' canjeado con éxito! Tu bono ha sido acreditado.")
        except ValidationError as e:
            messages.error(request, e.message if hasattr(e, "message") else str(e))
        except Exception as e:
            messages.error(request, f"Error al canjear el código: {str(e)}")

        return redirect("wallet_billetera")
