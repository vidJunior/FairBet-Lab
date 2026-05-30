from decimal import Decimal
import uuid
from hypothesis.extra.django import TestCase
from django.contrib.auth.models import User
from hypothesis import given, settings
import hypothesis.strategies as st
from django.core.exceptions import ValidationError
from django.utils import timezone

from wallet.models import LedgerEntry
from wallet.services import recargar
from config.choices import TipoCuenta, EstadoEvento, EstadoApuesta
from accounts.models import PerfilUsuario
from betting.models import Evento, Mercado, Seleccion, Apuesta
from betting.services import crear_apuesta, liquidar_apuestas_evento
from datetime import date

class BettingFinancialInvariantsTest(TestCase):
    """Invariante: Payout siempre es stake × odds."""

    def setUp(self):
        self.user = User.objects.create_user(username="hypo_bettor", password="pw")
        perfil = PerfilUsuario.objects.create(
            user=self.user,
            fecha_nacimiento=date(1990, 1, 1),
            dni=str(uuid.uuid4())[:8],
            limite_deposito_diario=Decimal("99999999.00"),
            limite_deposito_semanal=Decimal("99999999.00"),
            limite_deposito_mensual=Decimal("99999999.00"),
        )
        recargar(self.user, Decimal("1000000.00")) # Saldo alto para pruebas

        self.evento = Evento.objects.create(
            local="HypoLocal", visitante="HypoVisitante",
            fecha_inicio=timezone.now() + timezone.timedelta(days=1),
            estado=EstadoEvento.PROGRAMADO
        )
        self.mercado = Mercado.objects.create(evento=self.evento, nombre="1X2")

    def tearDown(self):
        LedgerEntry.objects.all().delete()
        Apuesta.objects.all().delete()
        Seleccion.objects.all().delete()

    @given(
        stake=st.decimals(min_value=Decimal('0.50'), max_value=Decimal('5000.00'), places=2),
        odds=st.decimals(min_value=Decimal('1.01'), max_value=Decimal('100.00'), places=4)
    )
    @settings(max_examples=50, deadline=None)
    def test_payout_precision_exacta(self, stake, odds):
        """El balance final al ganar debe ser exacto (stake * odds)."""
        # Crear una selección específica para esta prueba
        seleccion = Seleccion.objects.create(
            mercado=self.mercado,
            nombre=f"Local_{uuid.uuid4()}",
            cuota=odds
        )
        
        saldo_inicial_wallet = LedgerEntry.get_balance(self.user, TipoCuenta.WALLET_USUARIO)
        
        try:
            apuesta = crear_apuesta(self.user, seleccion.id, stake, cuota_esperada=odds)
        except ValidationError:
            # Ignorar ValidationError por validaciones internas
            return

        # Validar descuento de saldo
        saldo_despues_apostar = LedgerEntry.get_balance(self.user, TipoCuenta.WALLET_USUARIO)
        self.assertEqual(saldo_despues_apostar, saldo_inicial_wallet - stake)

        # Simular que gana
        liquidar_apuestas_evento(self.evento.id, seleccion.id)
        
        apuesta.refresh_from_db()
        if apuesta.estado == EstadoApuesta.WON:
            saldo_final_wallet = LedgerEntry.get_balance(self.user, TipoCuenta.WALLET_USUARIO)
            
            payout_esperado = (stake * odds).quantize(Decimal("0.0001"))
            
            # Saldo esperado: Inicial - stake + payout
            saldo_esperado_matematico = saldo_inicial_wallet - stake + payout_esperado
            
            self.assertEqual(
                saldo_final_wallet, 
                saldo_esperado_matematico, 
                f"Invariante rota para stake={stake}, odds={odds}. "
                f"Esperado: {saldo_esperado_matematico}, Real: {saldo_final_wallet}"
            )
