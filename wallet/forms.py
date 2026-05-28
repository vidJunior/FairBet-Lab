from decimal import Decimal
from django import forms
from django.core.exceptions import ValidationError as DjangoValidationError
from . import services


class DepositoForm(forms.Form):
    monto = forms.DecimalField(
        label="Monto a depositar",
        max_digits=18,
        decimal_places=4,
        min_value=Decimal("0.0001"),
        widget=forms.NumberInput(
            attrs={
                "class": "w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-slate-500 focus:ring-1 focus:ring-slate-500 bg-white",
                "placeholder": "100.0000",
                "step": "0.0001",
                "id": "monto_deposito",
            }
        ),
    )

    def clean_monto(self):
        monto = self.cleaned_data.get("monto")
        if monto and monto <= 0:
            raise forms.ValidationError("El monto debe ser mayor a cero.")
        return monto

    def save(self, user):
        try:
            tx_id, entries = services.depositar(
                user=user,
                monto=self.cleaned_data["monto"],
            )
            return tx_id, entries
        except DjangoValidationError as e:
            raise forms.ValidationError(e.messages)


class RetiroForm(forms.Form):
    monto = forms.DecimalField(
        label="Monto a retirar",
        max_digits=18,
        decimal_places=4,
        min_value=Decimal("0.0001"),
        widget=forms.NumberInput(
            attrs={
                "class": "w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-slate-500 focus:ring-1 focus:ring-slate-500 bg-white",
                "placeholder": "50.0000",
                "step": "0.0001",
                "id": "monto_retiro",
            }
        ),
    )

    def clean_monto(self):
        monto = self.cleaned_data.get("monto")
        if monto and monto <= 0:
            raise forms.ValidationError("El monto debe ser mayor a cero.")
        return monto

    def save(self, user):
        try:
            tx_id, entries = services.retirar(
                user=user,
                monto=self.cleaned_data["monto"],
            )
            return tx_id, entries
        except DjangoValidationError as e:
            raise forms.ValidationError(e.messages)
