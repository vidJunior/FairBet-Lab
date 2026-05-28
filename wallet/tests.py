import uuid
from decimal import Decimal
from django.test import TestCase, TransactionTestCase
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import connection
from unittest.mock import patch
from config.choices import DireccionLedger, TipoCuenta, TipoTransaccion, EstadoPerfil
from .models import LedgerEntry
from . import services


class LedgerEntryModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass123"
        )

    def test_signed_amount_credit(self):
        entry = LedgerEntry(
            user=self.user,
            account=TipoCuenta.WALLET_USUARIO,
            amount=Decimal("100.0000"),
            direction=DireccionLedger.CREDIT,
            transaction_id=uuid.uuid4(),
            tipo_transaccion=TipoTransaccion.DEPOSITO,
        )
        self.assertEqual(entry.signed_amount, Decimal("100.0000"))

    def test_signed_amount_debit(self):
        entry = LedgerEntry(
            user=self.user,
            account=TipoCuenta.WALLET_USUARIO,
            amount=Decimal("50.0000"),
            direction=DireccionLedger.DEBIT,
            transaction_id=uuid.uuid4(),
            tipo_transaccion=TipoTransaccion.RETIRO,
        )
        self.assertEqual(entry.signed_amount, Decimal("-50.0000"))

    def test_get_saldo_usuario_vacio(self):
        saldo = LedgerEntry.get_saldo_usuario(self.user)
        self.assertEqual(saldo, Decimal("0.0000"))

    def test_get_saldo_cuenta_usuario(self):
        LedgerEntry.crear_transaccion(
            entradas=[
                {
                    "user": self.user,
                    "account": TipoCuenta.WALLET_USUARIO,
                    "amount": Decimal("100.0000"),
                    "direction": DireccionLedger.CREDIT,
                },
                {
                    "user": None,
                    "account": TipoCuenta.CASA,
                    "amount": Decimal("100.0000"),
                    "direction": DireccionLedger.DEBIT,
                },
            ],
            tipo_transaccion=TipoTransaccion.DEPOSITO,
            user=self.user,
        )
        saldo = LedgerEntry.get_saldo_cuenta_usuario(
            self.user, TipoCuenta.WALLET_USUARIO
        )
        self.assertEqual(saldo, Decimal("100.0000"))

    def test_crear_transaccion_suma_no_cero(self):
        with self.assertRaises(ValidationError):
            LedgerEntry.crear_transaccion(
                entradas=[
                    {
                        "user": self.user,
                        "account": TipoCuenta.WALLET_USUARIO,
                        "amount": Decimal("100.0000"),
                        "direction": DireccionLedger.CREDIT,
                    },
                    {
                        "user": None,
                        "account": TipoCuenta.CASA,
                        "amount": Decimal("90.0000"),
                        "direction": DireccionLedger.DEBIT,
                    },
                ],
                tipo_transaccion=TipoTransaccion.DEPOSITO,
                user=self.user,
            )

    def test_crear_transaccion_menos_dos_entradas(self):
        with self.assertRaises(ValidationError):
            LedgerEntry.crear_transaccion(
                entradas=[
                    {
                        "user": self.user,
                        "account": TipoCuenta.WALLET_USUARIO,
                        "amount": Decimal("100.0000"),
                        "direction": DireccionLedger.CREDIT,
                    },
                ],
                tipo_transaccion=TipoTransaccion.DEPOSITO,
                user=self.user,
            )


class LedgerInvariantsTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass123"
        )

    def test_partida_doble_suma_cero(self):
        tx_id, entries = LedgerEntry.crear_transaccion(
            entradas=[
                {
                    "user": self.user,
                    "account": TipoCuenta.WALLET_USUARIO,
                    "amount": Decimal("100.0000"),
                    "direction": DireccionLedger.CREDIT,
                },
                {
                    "user": None,
                    "account": TipoCuenta.CASA,
                    "amount": Decimal("100.0000"),
                    "direction": DireccionLedger.DEBIT,
                },
            ],
            tipo_transaccion=TipoTransaccion.DEPOSITO,
            user=self.user,
        )
        total = sum(e.signed_amount for e in entries)
        self.assertEqual(total, Decimal("0.0000"))

    def test_mismo_transaction_id_en_entradas(self):
        tx_id, entries = LedgerEntry.crear_transaccion(
            entradas=[
                {
                    "user": self.user,
                    "account": TipoCuenta.WALLET_USUARIO,
                    "amount": Decimal("50.0000"),
                    "direction": DireccionLedger.CREDIT,
                },
                {
                    "user": None,
                    "account": TipoCuenta.CASA,
                    "amount": Decimal("50.0000"),
                    "direction": DireccionLedger.DEBIT,
                },
            ],
            tipo_transaccion=TipoTransaccion.DEPOSITO,
            user=self.user,
        )
        ids = set(e.transaction_id for e in entries)
        self.assertEqual(len(ids), 1)


class DepositoServiceTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass123"
        )
        from accounts.models import PerfilUsuario
        from datetime import date

        self.perfil = PerfilUsuario.objects.create(
            user=self.user,
            fecha_nacimiento=date(1990, 1, 1),
            dni="12345678",
        )
        self.perfil.estado = EstadoPerfil.VERIFICADO
        self.perfil.save(update_fields=["estado"])

    def test_deposito_exitoso(self):
        tx_id, entries = services.depositar(
            user=self.user, monto=Decimal("100.0000")
        )
        saldo = LedgerEntry.get_saldo_usuario(self.user)
        self.assertEqual(saldo, Decimal("100.0000"))

    def test_deposito_monto_negativo(self):
        with self.assertRaises(ValidationError):
            services.depositar(user=self.user, monto=Decimal("-10.0000"))

    def test_deposito_sin_perfil(self):
        user_sin_perfil = User.objects.create_user(
            username="noperfil", password="testpass123"
        )
        with self.assertRaises(ValidationError):
            services.depositar(user=user_sin_perfil, monto=Decimal("50.0000"))


class RetiroServiceTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass123"
        )
        from accounts.models import PerfilUsuario
        from datetime import date

        perfil = PerfilUsuario.objects.create(
            user=self.user,
            fecha_nacimiento=date(1990, 1, 1),
            dni="12345678",
        )
        perfil.estado = EstadoPerfil.VERIFICADO
        perfil.save(update_fields=["estado"])
        services.depositar(user=self.user, monto=Decimal("100.0000"))

    def test_retiro_exitoso(self):
        tx_id, entries = services.retirar(
            user=self.user, monto=Decimal("30.0000")
        )
        saldo = LedgerEntry.get_saldo_usuario(self.user)
        self.assertEqual(saldo, Decimal("70.0000"))

    def test_retiro_saldo_insuficiente(self):
        with self.assertRaises(ValidationError):
            services.retirar(user=self.user, monto=Decimal("150.0000"))


class BloqueoFondosTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass123"
        )
        from accounts.models import PerfilUsuario
        from datetime import date

        perfil = PerfilUsuario.objects.create(
            user=self.user,
            fecha_nacimiento=date(1990, 1, 1),
            dni="12345678",
        )
        perfil.estado = EstadoPerfil.VERIFICADO
        perfil.save(update_fields=["estado"])
        services.depositar(user=self.user, monto=Decimal("100.0000"))

    def test_bloqueo_fondos_exitoso(self):
        tx_id, entries = services.bloquear_fondos_apuesta(
            user=self.user, stake=Decimal("25.0000")
        )
        wallet = LedgerEntry.get_saldo_cuenta_usuario(
            self.user, TipoCuenta.WALLET_USUARIO
        )
        pendientes = LedgerEntry.get_saldo_cuenta_usuario(
            self.user, TipoCuenta.APUESTAS_PENDIENTES
        )
        self.assertEqual(wallet, Decimal("75.0000"))
        self.assertEqual(pendientes, Decimal("25.0000"))

    def test_bloqueo_sin_saldo(self):
        with self.assertRaises(ValidationError):
            services.bloquear_fondos_apuesta(
                user=self.user, stake=Decimal("150.0000")
            )


class LiquidacionTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass123"
        )
        from accounts.models import PerfilUsuario
        from datetime import date

        perfil = PerfilUsuario.objects.create(
            user=self.user,
            fecha_nacimiento=date(1990, 1, 1),
            dni="12345678",
        )
        perfil.estado = EstadoPerfil.VERIFICADO
        perfil.save(update_fields=["estado"])
        services.depositar(user=self.user, monto=Decimal("100.0000"))
        services.bloquear_fondos_apuesta(
            user=self.user, stake=Decimal("20.0000")
        )

    def test_liquidacion_ganada(self):
        stake = Decimal("20.0000")
        ganancia_neta = Decimal("30.0000")
        services.pagar_apuesta_ganada(
            user=self.user, stake=stake, ganancia_neta=ganancia_neta
        )
        saldo = LedgerEntry.get_saldo_usuario(self.user)
        self.assertEqual(saldo, Decimal("130.0000"))

    def test_liquidacion_perdida(self):
        services.liberar_fondos_apuesta_perdida(
            user=self.user, stake=Decimal("20.0000")
        )
        pendientes = LedgerEntry.get_saldo_cuenta_usuario(
            self.user, TipoCuenta.APUESTAS_PENDIENTES
        )
        self.assertEqual(pendientes, Decimal("0.0000"))

    def test_devolucion_cancelada(self):
        services.devolver_apuesta_cancelada(
            user=self.user, stake=Decimal("20.0000")
        )
        wallet = LedgerEntry.get_saldo_cuenta_usuario(
            self.user, TipoCuenta.WALLET_USUARIO
        )
        self.assertEqual(wallet, Decimal("100.0000"))


class ConcurrencyTest(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass123"
        )
        from accounts.models import PerfilUsuario
        from datetime import date

        perfil = PerfilUsuario.objects.create(
            user=self.user,
            fecha_nacimiento=date(1990, 1, 1),
            dni="12345678",
        )
        perfil.estado = EstadoPerfil.VERIFICADO
        perfil.save(update_fields=["estado"])
        services.depositar(user=self.user, monto=Decimal("100.0000"))

    def test_select_for_update_is_configured(self):
        from wallet.services import retirar
        import inspect

        source = inspect.getsource(retirar)
        self.assertIn("select_for_update(nowait=True)", source)

    def test_retiros_secuenciales_respetan_saldo(self):
        tx1, _ = services.retirar(user=self.user, monto=Decimal("40.0000"))
        tx2, _ = services.retirar(user=self.user, monto=Decimal("40.0000"))

        with self.assertRaises(Exception):
            services.retirar(user=self.user, monto=Decimal("40.0000"))

        saldo_final = LedgerEntry.get_saldo_usuario(self.user)
        self.assertEqual(saldo_final, Decimal("20.0000"))
