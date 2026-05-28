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
        self.evento.estado = EstadoEvento.FINALIZADO
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


from betting.services import crear_apuesta_combinada

class CombinedAndLiveBettingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="jugador2", password="securepassword123")
        self.perfil = PerfilUsuario.objects.create(
            user=self.user,
            fecha_nacimiento=timezone.now().date() - timezone.timedelta(days=365 * 25),
            dni="87654321",
            estado=EstadoPerfil.VERIFICADO
        )
        recargar(self.user, Decimal("200.0000"))

        # Evento 1
        self.ev1 = Evento.objects.create(
            local="Real Madrid", visitante="Barcelona",
            fecha_inicio=timezone.now() + timezone.timedelta(days=1),
            estado=EstadoEvento.PROGRAMADO
        )
        self.m1 = Mercado.objects.create(evento=self.ev1, nombre="1X2")
        self.sel1_local = Seleccion.objects.create(mercado=self.m1, nombre="Local", cuota=Decimal("2.0000"))
        self.sel1_visitante = Seleccion.objects.create(mercado=self.m1, nombre="Visitante", cuota=Decimal("3.0000"))

        # Evento 2
        self.ev2 = Evento.objects.create(
            local="Arsenal", visitante="Chelsea",
            fecha_inicio=timezone.now() + timezone.timedelta(days=1),
            estado=EstadoEvento.PROGRAMADO
        )
        self.m2 = Mercado.objects.create(evento=self.ev2, nombre="1X2")
        self.sel2_local = Seleccion.objects.create(mercado=self.m2, nombre="Local", cuota=Decimal("1.5000"))
        self.sel2_empate = Seleccion.objects.create(mercado=self.m2, nombre="Empate", cuota=Decimal("4.0000"))

    def test_crear_apuesta_combinada_exitosa(self):
        monto = Decimal("30.0000")
        apuesta = crear_apuesta_combinada(
            self.user,
            [self.sel1_local.id, self.sel2_empate.id],
            monto
        )
        self.assertEqual(apuesta.tipo, "COMBINADA")
        self.assertEqual(apuesta.monto, monto)
        # Cuota esperada = 2.00 * 4.00 = 8.00
        self.assertEqual(apuesta.cuota_fijada, Decimal("8.0000"))
        self.assertEqual(apuesta.detalles.count(), 2)

        saldo_usuario = LedgerEntry.get_balance(self.user, TipoCuenta.WALLET_USUARIO)
        self.assertEqual(saldo_usuario, Decimal("170.0000"))

    def test_rechazo_apuesta_combinada_mismo_evento(self):
        # Intentar combinar Local y Visitante del mismo partido (Exclusión mutua)
        with self.assertRaises(ValidationError):
            crear_apuesta_combinada(
                self.user,
                [self.sel1_local.id, self.sel1_visitante.id],
                Decimal("10.0000")
            )

    def test_liquidacion_combinada_ganadora(self):
        apuesta = crear_apuesta_combinada(
            self.user,
            [self.sel1_local.id, self.sel2_local.id],
            Decimal("50.0000")
        )
        # Cuota = 2.00 * 1.50 = 3.00. Payout esperado = 50.00 * 3.00 = 150.00

        # Simular finalización de evento 1 ganando Local (Real Madrid)
        self.ev1.goles_local = 2
        self.ev1.goles_visitante = 1
        self.ev1.save()
        liquidar_apuestas_evento(self.ev1.id, self.sel1_local.id)

        # La combinada debería seguir ACCEPTED (pendiente de evento 2)
        apuesta.refresh_from_db()
        self.assertEqual(apuesta.estado, EstadoApuesta.ACCEPTED)

        # Simular finalización de evento 2 ganando Local (Arsenal)
        self.ev2.goles_local = 1
        self.ev2.goles_visitante = 0
        self.ev2.save()
        liquidar_apuestas_evento(self.ev2.id, self.sel2_local.id)

        apuesta.refresh_from_db()
        self.assertEqual(apuesta.estado, EstadoApuesta.WON)
        # Saldo = inicial (200) - stake (50) + payout (150) = 300.0000
        saldo_usuario = LedgerEntry.get_balance(self.user, TipoCuenta.WALLET_USUARIO)
        self.assertEqual(saldo_usuario, Decimal("300.0000"))

    def test_liquidacion_combinada_perdedora(self):
        apuesta = crear_apuesta_combinada(
            self.user,
            [self.sel1_local.id, self.sel2_local.id],
            Decimal("50.0000")
        )

        # Simular finalización de evento 1 ganando Visitante (Barcelona) -> Combinada perdida de inmediato
        self.ev1.goles_local = 0
        self.ev1.goles_visitante = 1
        self.ev1.save()
        liquidar_apuestas_evento(self.ev1.id, self.sel1_visitante.id)

        apuesta.refresh_from_db()
        self.assertEqual(apuesta.estado, EstadoApuesta.LOST)

        # El saldo restante debe ser 150 (200 - 50 stake perdido)
        saldo_usuario = LedgerEntry.get_balance(self.user, TipoCuenta.WALLET_USUARIO)
        self.assertEqual(saldo_usuario, Decimal("150.0000"))

    def test_recotizacion_apuesta_simple(self):
        # La cuota de sel1_local es 2.0000. Si enviamos 1.8000, debe fallar
        with self.assertRaises(ValidationError):
            crear_apuesta(self.user, self.sel1_local.id, Decimal("10.00"), cuota_esperada=Decimal("1.80"))

        # Si mandamos la correcta, pasa
        ap = crear_apuesta(self.user, self.sel1_local.id, Decimal("10.00"), cuota_esperada=Decimal("2.00"))
        self.assertIsNotNone(ap)

    def test_apuestas_en_vivo_y_mercado_suspendido(self):
        # Cambiar evento a EN_VIVO
        self.ev1.estado = EstadoEvento.EN_VIVO
        self.ev1.save()

        # Apuesta en vivo debería permitirse
        ap = crear_apuesta(self.user, self.sel1_local.id, Decimal("10.00"))
        self.assertIsNotNone(ap)

        # Registrar evento crítico para suspender el mercado
        from betting.services import registrar_evento_critico
        registrar_evento_critico(self.ev1.id, "GOL_LOCAL")

        # Intentar apostar en el mercado suspendido debe arrojar error
        with self.assertRaises(ValidationError):
            crear_apuesta(self.user, self.sel1_local.id, Decimal("10.00"))

