from django.test import TestCase
from django.db import connection
from django.core.exceptions import ValidationError
from api.models import AuditLog

class AuditLogTestCase(TestCase):

    def test_hash_chaining_sequential(self):
        """Prueba que los bloques se encadenen correctamente (hash_n usa hash_n-1)"""
        log1 = AuditLog.objects.create(action_type='BET_CREATED', payload={'id': 1, 'amount': 100})
        log2 = AuditLog.objects.create(action_type='WALLET_MOVEMENT', payload={'id': 5, 'balance': 500})
        
        # El previous_hash del segundo debe ser exactamente el current_hash del primero
        self.assertEqual(log2.previous_hash, log1.current_hash)
        # El primero debe tener el hash génesis (64 ceros)
        self.assertEqual(log1.previous_hash, '0' * 64)

    def test_immutable_records(self):
        """Prueba que Django impida modificar un registro existente usando .save()"""
        log = AuditLog.objects.create(action_type='BET_CREATED', payload={'id': 1})
        
        log.payload = {'id': 1, 'amount': 9999} # Intento de alteración
        with self.assertRaises(ValidationError):
            log.save()

    def test_verify_chain_success_when_intact(self):
        """Prueba que la verificación sea exitosa si nadie ha manipulado la base de datos"""
        AuditLog.objects.create(action_type='BET_CREATED', payload={'id': 1, 'amount': 50})
        AuditLog.objects.create(action_type='ODDS_CHANGED', payload={'market': 'Goles', 'value': 1.85})
        AuditLog.objects.create(action_type='WALLET_MOVEMENT', payload={'id': 2, 'amount': -50})

        # Asumimos que AuditLog tendrá un método para verificar la cadena completa
        is_valid, corrupted_id = AuditLog.verify_chain()
        
        self.assertTrue(is_valid)
        self.assertIsNone(corrupted_id)

    def test_verify_chain_fails_when_manipulated(self):
        """LA PRUEBA DEL HACKER: Modificar la BD vía SQL directo debe romper la cadena"""
        log1 = AuditLog.objects.create(action_type='BET_CREATED', payload={'id': 1, 'amount': 100})
        log2 = AuditLog.objects.create(action_type='WALLET_MOVEMENT', payload={'user_id': 1, 'amount': -100})
        log3 = AuditLog.objects.create(action_type='BET_SETTLED', payload={'id': 1, 'status': 'WON'})

        # Simulamos un ataque: Un admin corrupto entra a la base de datos usando SQL
        # y cambia el monto del payload original de 100 a 100000 para cobrar de más.
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE api_audit_log SET payload = '{\"amount\": 100000, \"id\": 1}' WHERE id = %s",
                [log1.id]
            )

        # Ejecutamos la verificación del sistema
        is_valid, corrupted_id = AuditLog.verify_chain()

        # El sistema DEBE darse cuenta de que la cadena se rompió
        self.assertFalse(is_valid)
        # Debe apuntar exactamente al bloque que fue modificado o donde se rompió la secuencia
        self.assertEqual(corrupted_id, log1.id)

from django.contrib.auth import get_user_model
from api.models import SuspiciousActivity
from api.services import AntiFraudService  # Crearemos este archivo en el siguiente paso

User = get_user_model()

class AntiFraudTestCase(TestCase):

    def setUp(self):
        # Creamos usuarios de prueba para los escenarios de fraude
        self.user1 = User.objects.create_user(username='player1', password='password123', email='p1@test.com')
        self.user2 = User.objects.create_user(username='player2', password='password123', email='p2@test.com')
        self.user3 = User.objects.create_user(username='player3', password='password123', email='p3@test.com')

    def test_rule_multiple_accounts_same_ip(self):
        """Regla 1: Debe alertar si una IP está vinculada a demasiadas cuentas distintas"""
        ip_sospechosa = "192.168.1.50"
        
        # Simulamos una lista de registros de login/registro con la misma IP
        # Estructura: (user_id, ip_address)
        login_logs = [
            (self.user1.id, ip_sospechosa),
            (self.user2.id, ip_sospechosa),
            (self.user3.id, ip_sospechosa), # 3 cuentas con la misma IP (Umbral alcanzado)
        ]

        # Ejecutamos el evaluador de la regla pasándole un límite estricto de N=2 para activar la alerta
        alerts_created = AntiFraudService.check_multicuenta_ip(login_logs, max_accounts=2, ip_address=ip_sospechosa)
        
        self.assertTrue(alerts_created)
        self.assertEqual(SuspiciousActivity.objects.filter(rule_triggered='MULTIPLE_ACCOUNTS_SAME_IP').count(), 1)

    def test_rule_identical_group_betting(self):
        """Regla 2: Debe alertar si múltiples usuarios realizan exactamente la misma apuesta en grupo"""
        # Simulamos apuestas idénticas colocadas casi al mismo tiempo por distintos usuarios
        # Mercado id: 99 (Goleador exacto), Selección: "Messi", Cuota: 2.10, Monto: 500
        bets_to_analyze = [
            {'user_id': self.user1.id, 'market_id': 99, 'selection': 'Messi', 'odds': 2.10, 'stake': 500},
            {'user_id': self.user2.id, 'market_id': 99, 'selection': 'Messi', 'odds': 2.10, 'stake': 500},
        ]

        AntiFraudService.check_identical_bets(bets_to_analyze)

        # Debe generar la alerta por patrón de apuestas idénticas en grupo
        self.assertEqual(SuspiciousActivity.objects.filter(rule_triggered='IDENTICAL_GROUP_BETTING').count(), 1)

    def test_rule_immediate_deposit_cashout(self):
        """Regla 3: Debe alertar si hay un depósito fuerte e inmediato cash-out sin jugar significativamente"""
        # Simulamos un historial sospechoso: deposita 1000 y retira (cash-out) 950 a los 2 minutos sin arriesgar nada
        transaction_history = {
            'user_id': self.user1.id,
            'deposit_amount': 1000.00,
            'cashout_amount': 950.00,
            'minutes_elapsed': 2, # Menor a nuestro umbral de 10 minutos
            'total_wagered': 0.00  # No apostó nada del depósito, es lavado o traspaso
        }

        AntiFraudService.check_immediate_cashout(transaction_history)

        self.assertEqual(SuspiciousActivity.objects.filter(rule_triggered='IMMEDIATE_DEPOSIT_CASHOUT').count(), 1)