from decimal import Decimal
import uuid
from hypothesis.extra.django import TestCase
from django.contrib.auth.models import User
from hypothesis import given, settings
import hypothesis.strategies as st
from django.core.exceptions import ValidationError

from wallet.models import LedgerEntry
from wallet.services import recargar, retirar, transferencia_interna
from config.choices import TipoCuenta, Direccion
from accounts.models import PerfilUsuario
from datetime import date

class WalletFinancialInvariantsTest(TestCase):
    """
    Property-based testing con hypothesis para las invariantes financieras:
    ◦ “La suma global de débitos y créditos siempre es cero.”
    ◦ “Ningún wallet termina con saldo negativo.”
    """
    
    def setUp(self):
        self.user1 = User.objects.create_user(username="hypo_user1", password="pw")
        PerfilUsuario.objects.create(
            user=self.user1,
            fecha_nacimiento=date(1990, 1, 1),
            dni=str(uuid.uuid4())[:8],
        )
        self.user2 = User.objects.create_user(username="hypo_user2", password="pw")
        PerfilUsuario.objects.create(
            user=self.user2,
            fecha_nacimiento=date(1990, 1, 1),
            dni=str(uuid.uuid4())[:8],
        )

    def tearDown(self):
        LedgerEntry.objects.all().delete()

    @given(
        recargas=st.lists(st.decimals(min_value=Decimal('0.00'), max_value=Decimal('1000.00'), places=2), min_size=0, max_size=10),
        retiros=st.lists(st.decimals(min_value=Decimal('0.00'), max_value=Decimal('1000.00'), places=2), min_size=0, max_size=10),
        transferencias=st.lists(st.decimals(min_value=Decimal('0.00'), max_value=Decimal('1000.00'), places=2), min_size=0, max_size=10)
    )
    @settings(max_examples=50, deadline=None)
    def test_invariantes_financieras_wallet(self, recargas, retiros, transferencias):
        """
        Ejecuta una serie de operaciones aleatorias y verifica que el sistema no permite
        estados inválidos y que la suma de partidas dobles es cero.
        """
        for r in recargas:
            try:
                recargar(self.user1, r)
            except ValidationError:
                pass
            
        for r in retiros:
            try:
                retirar(self.user1, r)
            except ValidationError:
                pass
                
        for t in transferencias:
            try:
                transferencia_interna(self.user1, TipoCuenta.WALLET_USUARIO, TipoCuenta.CASA, t)
            except ValidationError:
                pass

        # Invariante 1: Suma global de débitos y créditos siempre es cero.
        debitos = sum(e.monto for e in LedgerEntry.objects.filter(direccion=Direccion.DEBIT))
        creditos = sum(e.monto for e in LedgerEntry.objects.filter(direccion=Direccion.CREDIT))
        self.assertEqual(debitos, creditos, "La suma global de débitos y créditos no es cero.")

        # Invariante 2: Ningún wallet termina con saldo negativo.
        for cuenta in TipoCuenta.values:
            saldo1 = LedgerEntry.get_balance(self.user1, cuenta)
            self.assertGreaterEqual(saldo1, Decimal('0.0000'), f"El wallet de user1 ({cuenta}) tiene saldo negativo: {saldo1}")
            
            saldo2 = LedgerEntry.get_balance(self.user2, cuenta)
            self.assertGreaterEqual(saldo2, Decimal('0.0000'), f"El wallet de user2 ({cuenta}) tiene saldo negativo: {saldo2}")
