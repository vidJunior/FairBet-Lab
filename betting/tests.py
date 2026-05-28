from decimal import Decimal
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from django.db import models

from config.choices import TipoCuenta, EstadoPerfil, TipoAutoexclusion, Direccion, EstadoEvento, EstadoApuesta
from accounts.models import PerfilUsuario
from wallet.models import LedgerEntry
from wallet.services import recargar
from betting.models import Evento, Mercado, Seleccion, Apuesta
from betting.services import crear_apuesta, liquidar_apuestas_evento


class BettingServicesTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="jugador1", password="securepassword123")
        
        self.perfil = PerfilUsuario.objects.create(
            user=self.user,
            fecha_nacimiento=timezone.now().date() - timezone.timedelta(days=365 * 25),
            dni="12345678",
            estado=EstadoPerfil.VERIFICADO
        )

        recargar(self.user, Decimal("100.0000"))

        self.evento = Evento.objects.create(
            local="Perú",
            visitante="Chile",
            fecha_inicio=timezone.now() + timezone.timedelta(days=1),
            estado=EstadoEvento.PROGRAMADO
        )
        self.mercado = Mercado.objects.create(evento=self.evento, nombre="1X2")
        self.seleccion_local = Seleccion.objects.create(
            mercado=self.mercado,
            nombre="Local",
            cuota=Decimal("2.5000")
        )
        self.seleccion_visitante = Seleccion.objects.create(
            mercado=self.mercado,
            nombre="Visitante",
            cuota=Decimal("3.0000")
        )

    def test_creacion_apuesta_exitosa(self):
        monto = Decimal("10.0000")
        apuesta = crear_apuesta(self.user, self.seleccion_local.id, monto)

        self.assertEqual(apuesta.usuario, self.user)
        self.assertEqual(apuesta.seleccion, self.seleccion_local)
        self.assertEqual(apuesta.monto, monto)
        self.assertEqual(apuesta.cuota_fijada, self.seleccion_local.cuota)
        self.assertEqual(apuesta.estado, EstadoApuesta.ACCEPTED)

        saldo_usuario = LedgerEntry.get_balance(self.user, TipoCuenta.WALLET_USUARIO)
        saldo_congelado = LedgerEntry.get_balance(self.user, TipoCuenta.APUESTAS_PENDIENTES)
        
        self.assertEqual(saldo_usuario, Decimal("90.0000"))
        self.assertEqual(saldo_congelado, Decimal("10.0000"))

        # Partida doble suma cero
        total_ledger = LedgerEntry.objects.aggregate(
            total=models.Sum(
                models.Case(
                    models.When(direccion=Direccion.CREDIT, then="monto"),
                    models.When(direccion=Direccion.DEBIT, then=Decimal("0") - models.F("monto")),
                    output_field=models.DecimalField()
                )
            )
        )["total"]
        self.assertEqual(total_ledger or Decimal("0"), Decimal("0"))

    def test_rechazo_apuesta_saldo_insuficiente(self):
        monto = Decimal("150.0000")
        with self.assertRaises(ValidationError):
            crear_apuesta(self.user, self.seleccion_local.id, monto)

    def test_rechazo_apuesta_usuario_autoexcluido(self):
        self.perfil.tipo_autoexclusion = TipoAutoexclusion.DIAS_7
        self.perfil.save()

        with self.assertRaises(ValidationError):
            crear_apuesta(self.user, self.seleccion_local.id, Decimal("10.0000"))

    def test_rechazo_apuesta_evento_comenzado(self):
        self.evento.estado = EstadoEvento.EN_VIVO
        self.evento.save()

        with self.assertRaises(ValidationError):
            crear_apuesta(self.user, self.seleccion_local.id, Decimal("10.0000"))

    def test_liquidacion_apuesta_ganadora(self):
        monto = Decimal("20.0000")
        apuesta = crear_apuesta(self.user, self.seleccion_local.id, monto)

        self.evento.goles_local = 2
        self.evento.goles_visitante = 1
        self.evento.save()

        liquidar_apuestas_evento(self.evento.id, self.seleccion_local.id)

        apuesta.refresh_from_db()
        self.assertEqual(apuesta.estado, EstadoApuesta.WON)

        saldo_usuario = LedgerEntry.get_balance(self.user, TipoCuenta.WALLET_USUARIO)
        saldo_congelado = LedgerEntry.get_balance(self.user, TipoCuenta.APUESTAS_PENDIENTES)

        self.assertEqual(saldo_usuario, Decimal("130.0000"))
        self.assertEqual(saldo_congelado, Decimal("0.0000"))

        # Partida doble suma cero
        total_ledger = LedgerEntry.objects.aggregate(
            total=models.Sum(
                models.Case(
                    models.When(direccion=Direccion.CREDIT, then="monto"),
                    models.When(direccion=Direccion.DEBIT, then=Decimal("0") - models.F("monto")),
                    output_field=models.DecimalField()
                )
            )
        )["total"]
        self.assertEqual(total_ledger or Decimal("0"), Decimal("0"))

    def test_liquidacion_apuesta_perdedora(self):
        monto = Decimal("20.0000")
        apuesta = crear_apuesta(self.user, self.seleccion_local.id, monto)

        liquidar_apuestas_evento(self.evento.id, self.seleccion_visitante.id)

        apuesta.refresh_from_db()
        self.assertEqual(apuesta.estado, EstadoApuesta.LOST)

        saldo_usuario = LedgerEntry.get_balance(self.user, TipoCuenta.WALLET_USUARIO)
        saldo_congelado = LedgerEntry.get_balance(self.user, TipoCuenta.APUESTAS_PENDIENTES)

        self.assertEqual(saldo_usuario, Decimal("80.0000"))
        self.assertEqual(saldo_congelado, Decimal("0.0000"))

        # Partida doble suma cero
        total_ledger = LedgerEntry.objects.aggregate(
            total=models.Sum(
                models.Case(
                    models.When(direccion=Direccion.CREDIT, then="monto"),
                    models.When(direccion=Direccion.DEBIT, then=Decimal("0") - models.F("monto")),
                    output_field=models.DecimalField()
                )
            )
        )["total"]
        self.assertEqual(total_ledger or Decimal("0"), Decimal("0"))
