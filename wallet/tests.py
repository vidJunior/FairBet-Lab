from decimal import Decimal
import uuid
from django.contrib.auth.models import User
from django.test import TestCase

from config.choices import TipoCuenta, Direccion
from wallet.models import LedgerEntry


class LedgerEntryModelTest(TestCase):
    """Pruebas del modelo LedgerEntry y de la función get_balance usando inserciones directas."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="password")

    def test_model_fields_and_get_balance(self):
        # El saldo inicial debe ser cero
        self.assertEqual(
            LedgerEntry.get_balance(self.user, TipoCuenta.WALLET_USUARIO),
            Decimal("0.0000"),
        )

        tid = uuid.uuid4()
        # Agregar crédito manual
        LedgerEntry.objects.create(
            id_transaccion=tid,
            usuario=self.user,
            cuenta=TipoCuenta.WALLET_USUARIO,
            monto=Decimal("150.0000"),
            direccion=Direccion.CREDIT,
        )
        self.assertEqual(
            LedgerEntry.get_balance(self.user, TipoCuenta.WALLET_USUARIO),
            Decimal("150.0000"),
        )

        # Agregar débito manual
        LedgerEntry.objects.create(
            id_transaccion=tid,
            usuario=self.user,
            cuenta=TipoCuenta.WALLET_USUARIO,
            monto=Decimal("50.0000"),
            direccion=Direccion.DEBIT,
        )
        self.assertEqual(
            LedgerEntry.get_balance(self.user, TipoCuenta.WALLET_USUARIO),
            Decimal("100.0000"),
        )
