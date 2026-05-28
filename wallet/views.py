from django.shortcuts import render, redirect
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.views import View
from django.views.generic import TemplateView
from .forms import DepositoForm, RetiroForm
from .models import LedgerEntry
from . import services


class DepositoHTMLView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        form = DepositoForm()
        return render(request, "wallet/deposito.html", {"form": form})

    def post(self, request, *args, **kwargs):
        form = DepositoForm(request.POST)
        if form.is_valid():
            try:
                tx_id, entries = form.save(user=request.user)
                messages.success(
                    request,
                    f"Deposito de {form.cleaned_data['monto']} fichas realizado con exito.",
                )
                return redirect("wallet_saldo_html")
            except Exception as e:
                messages.error(request, f"Error al procesar el deposito: {str(e)}")
        else:
            messages.error(request, "Corrige los errores del formulario.")

        return render(request, "wallet/deposito.html", {"form": form})


class RetiroHTMLView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        form = RetiroForm()
        return render(request, "wallet/retiro.html", {"form": form})

    def post(self, request, *args, **kwargs):
        form = RetiroForm(request.POST)
        if form.is_valid():
            try:
                tx_id, entries = form.save(user=request.user)
                messages.success(
                    request,
                    f"Retiro de {form.cleaned_data['monto']} fichas realizado con exito.",
                )
                return redirect("wallet_saldo_html")
            except Exception as e:
                messages.error(request, f"Error al procesar el retiro: {str(e)}")
        else:
            messages.error(request, "Corrige los errores del formulario.")

        return render(request, "wallet/retiro.html", {"form": form})


class SaldoHTMLView(LoginRequiredMixin, TemplateView):
    template_name = "wallet/saldo.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context["saldo_disponible"] = services.obtener_saldo_disponible(user)
        context["desglose"] = services.obtener_desglose_saldos(user)
        context["historial"] = LedgerEntry.objects.filter(user=user).order_by(
            "-creado_en"
        )[:20]
        return context


class WalletHomeHTMLView(LoginRequiredMixin, TemplateView):
    template_name = "wallet/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context["saldo_disponible"] = services.obtener_saldo_disponible(user)
        return context
