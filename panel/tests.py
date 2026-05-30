from decimal import Decimal

from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.exceptions import ValidationError

from config.choices import (
    TipoCuenta, EstadoApuesta, EstadoEvento, TipoBono, EstadoBono, TipoAlertaAbuso
)
from betting.models import Evento, Mercado, Seleccion, Apuesta, ApuestaSeleccion, Equipo
from wallet.models import LedgerEntry
from panel.models import Bono, BonoApuesta, AlertaAbuso
from panel.services import (
    calculate_ggr, calculate_exposure_by_event, calculate_volume, count_active_users
)
from panel.reports import generate_monthly_report, generate_csv_content
from panel.abuse_detection import detect_risk_free_betting


class OperatorMetricsTestCase(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("admin", "admin@test.com", "admin123")
        self.user1 = User.objects.create_user("user1", "user1@test.com", "pass123")
        self.user2 = User.objects.create_user("user2", "user2@test.com", "pass123")

        self.equipo_local = Equipo.objects.create(nombre="Alianza Lima")
        self.equipo_visita = Equipo.objects.create(nombre="Universitario")

        self.evento = Evento.objects.create(
            local=self.equipo_local,
            visitante=self.equipo_visita,
            fecha_inicio=timezone.now(),
            estado=EstadoEvento.PROGRAMADO,
        )

        self.mercado = Mercado.objects.create(evento=self.evento, nombre="1X2")
        self.sel_local = Seleccion.objects.create(mercado=self.mercado, nombre="Local", cuota=Decimal("2.0000"))
        self.sel_empate = Seleccion.objects.create(mercado=self.mercado, nombre="Empate", cuota=Decimal("3.5000"))
        self.sel_visita = Seleccion.objects.create(mercado=self.mercado, nombre="Visitante", cuota=Decimal("2.5000"))

        LedgerEntry.objects.create(
            usuario=None, cuenta=TipoCuenta.CASA, monto=Decimal("10000.0000"), direccion="CREDIT"
        )
        LedgerEntry.objects.create(
            usuario=self.user1, cuenta=TipoCuenta.WALLET_USUARIO, monto=Decimal("500.0000"), direccion="CREDIT"
        )
        LedgerEntry.objects.create(
            usuario=self.user2, cuenta=TipoCuenta.WALLET_USUARIO, monto=Decimal("300.0000"), direccion="CREDIT"
        )

    def test_ggr_inicial_cero(self):
        ggr = calculate_ggr(period_hours=24)
        self.assertEqual(ggr, Decimal("0.0000"))

    def test_volume_sin_apuestas(self):
        volume = calculate_volume(hours=24)
        self.assertEqual(volume["total_apuestas"], 0)
        self.assertEqual(volume["total_staked"], "0.0000")

    def test_active_users_sin_apuestas(self):
        self.assertEqual(count_active_users(hours=1), 0)

    def test_exposure_evento_activo(self):
        Apuesta.objects.create(
            usuario=self.user1,
            seleccion=self.sel_local,
            monto=Decimal("50.0000"),
            cuota_fijada=Decimal("2.0000"),
            estado=EstadoApuesta.ACCEPTED,
            tipo="SIMPLE",
        )
        exposure = calculate_exposure_by_event()
        self.assertEqual(len(exposure), 1)
        self.assertEqual(Decimal(exposure[0]["total_exposure"]), Decimal("100.0000"))

    def test_ggr_con_apuesta_perdida(self):
        Apuesta.objects.create(
            usuario=self.user1,
            seleccion=self.sel_local,
            monto=Decimal("100.0000"),
            cuota_fijada=Decimal("2.0000"),
            estado=EstadoApuesta.LOST,
            tipo="SIMPLE",
        )
        ggr = calculate_ggr(period_hours=24)
        self.assertGreater(ggr, Decimal("0"))


class BonoModelTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("bonouser", "bono@test.com", "pass123")

    def test_creacion_bono_con_rollover(self):
        bono = Bono.objects.create(
            usuario=self.user,
            tipo=TipoBono.BIENVENIDA,
            monto=Decimal("100.0000"),
            rollover_multiplier=Decimal("5.00"),
        )
        self.assertEqual(bono.rollover_requerido, Decimal("500.0000"))
        self.assertEqual(bono.estado, EstadoBono.ACTIVO)
        self.assertFalse(bono.rollover_completado)

    def test_rollover_progreso(self):
        bono = Bono.objects.create(
            usuario=self.user,
            tipo=TipoBono.BIENVENIDA,
            monto=Decimal("100.0000"),
            rollover_multiplier=Decimal("5.00"),
        )
        bono.rollover_apostado = Decimal("250.0000")
        bono.save()
        self.assertEqual(bono.rollover_progreso, Decimal("50.00"))

    def test_rollover_completado(self):
        bono = Bono.objects.create(
            usuario=self.user,
            tipo=TipoBono.BIENVENIDA,
            monto=Decimal("100.0000"),
            rollover_multiplier=Decimal("5.00"),
        )
        bono.rollover_apostado = Decimal("500.0000")
        bono.save()
        self.assertTrue(bono.rollover_completado)

    def test_expirar_si_corresponde(self):
        bono = Bono.objects.create(
            usuario=self.user,
            tipo=TipoBono.BIENVENIDA,
            monto=Decimal("100.0000"),
            rollover_multiplier=Decimal("5.00"),
            expira=timezone.now() - timezone.timedelta(days=1),
        )
        self.assertTrue(bono.expirar_si_corresponde())
        bono.refresh_from_db()
        self.assertEqual(bono.estado, EstadoBono.EXPIRADO)


class AbusoDetectionTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("abusouser", "abuso@test.com", "pass123")

        self.equipo_local = Equipo.objects.create(nombre="Team A")
        self.equipo_visita = Equipo.objects.create(nombre="Team B")

        self.evento = Evento.objects.create(
            local=self.equipo_local,
            visitante=self.equipo_visita,
            fecha_inicio=timezone.now(),
            estado=EstadoEvento.PROGRAMADO,
        )

        self.mercado = Mercado.objects.create(evento=self.evento, nombre="1X2")
        self.sel_local = Seleccion.objects.create(mercado=self.mercado, nombre="Local", cuota=Decimal("2.0000"))
        self.sel_empate = Seleccion.objects.create(mercado=self.mercado, nombre="Empate", cuota=Decimal("3.5000"))
        self.sel_visita = Seleccion.objects.create(mercado=self.mercado, nombre="Visitante", cuota=Decimal("2.5000"))

        self.bono = Bono.objects.create(
            usuario=self.user,
            tipo=TipoBono.BIENVENIDA,
            monto=Decimal("100.0000"),
            rollover_multiplier=Decimal("5.00"),
        )

    def test_sin_alerta_con_apuesta_normal(self):
        apuesta = Apuesta.objects.create(
            usuario=self.user,
            seleccion=self.sel_local,
            monto=Decimal("50.0000"),
            cuota_fijada=Decimal("2.0000"),
            estado=EstadoApuesta.ACCEPTED,
            tipo="SIMPLE",
        )
        alertas = detect_risk_free_betting(self.user, self.bono)
        self.assertEqual(len(alertas), 0)

    def test_alerta_cobertura_total(self):
        Apuesta.objects.create(
            usuario=self.user,
            seleccion=self.sel_local,
            monto=Decimal("100.0000"),
            cuota_fijada=Decimal("2.0000"),
            estado=EstadoApuesta.ACCEPTED,
            tipo="SIMPLE",
        )
        Apuesta.objects.create(
            usuario=self.user,
            seleccion=self.sel_empate,
            monto=Decimal("100.0000"),
            cuota_fijada=Decimal("3.5000"),
            estado=EstadoApuesta.ACCEPTED,
            tipo="SIMPLE",
        )
        Apuesta.objects.create(
            usuario=self.user,
            seleccion=self.sel_visita,
            monto=Decimal("100.0000"),
            cuota_fijada=Decimal("2.5000"),
            estado=EstadoApuesta.ACCEPTED,
            tipo="SIMPLE",
        )

        alertas = detect_risk_free_betting(self.user, self.bono)
        self.assertGreater(len(alertas), 0)
        self.assertEqual(alertas[0].tipo, TipoAlertaAbuso.RISK_FREE)


class MonthlyReportTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("reportuser", "report@test.com", "pass123")

        self.equipo_local = Equipo.objects.create(nombre="Team X")
        self.equipo_visita = Equipo.objects.create(nombre="Team Y")

        self.evento = Evento.objects.create(
            local=self.equipo_local,
            visitante=self.equipo_visita,
            fecha_inicio=timezone.now(),
            estado=EstadoEvento.FINALIZADO,
        )

        self.mercado = Mercado.objects.create(evento=self.evento, nombre="1X2")
        self.sel_local = Seleccion.objects.create(mercado=self.mercado, nombre="Local", cuota=Decimal("2.0000"))

        ahora = timezone.now()
        Apuesta.objects.create(
            usuario=self.user,
            seleccion=self.sel_local,
            monto=Decimal("50.0000"),
            cuota_fijada=Decimal("2.0000"),
            estado=EstadoApuesta.WON,
            tipo="SIMPLE",
            creado=ahora,
        )

    def test_generar_reporte_mensual(self):
        ahora = timezone.now()
        filas = generate_monthly_report(ahora.year, ahora.month)
        self.assertGreater(len(filas), 0)
        self.assertIn("monto_apostado", filas[0])
        self.assertIn("ggr", filas[0])

    def test_csv_content_no_vacio(self):
        ahora = timezone.now()
        filas = generate_monthly_report(ahora.year, ahora.month)
        csv_content = generate_csv_content(filas)
        self.assertIn("fecha", csv_content)
        self.assertIn("monto_apostado", csv_content)
