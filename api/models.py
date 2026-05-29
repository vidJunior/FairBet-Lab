import hashlib
import json
from django.db import models, transaction
from django.core.exceptions import ValidationError
from django.conf import settings

class AuditLog(models.Model):
    ACTION_CHOICES = [
        ('BET_CREATED', 'Apuesta Creada'),
        ('BET_SETTLED', 'Apuesta Liquidada'),
        ('WALLET_MOVEMENT', 'Movimiento de Wallet'),
        ('ODDS_CHANGED', 'Cambio de Cuotas'),
    ]

    timestamp = models.DateTimeField(auto_now_add=True)
    action_type = models.CharField(max_length=20, choices=ACTION_CHOICES)
    payload = models.JSONField(help_text="Datos del evento en formato JSON")
    previous_hash = models.CharField(max_length=64, editable=False)
    current_hash = models.CharField(max_length=64, editable=False)

    class Meta:
        ordering = ['id']  # Es crítico que el orden sea estrictamente por inserción
        db_table = 'api_audit_log'

    def save(self, *args, **kwargs):
        # Si el registro ya existe en la BD, no permitimos su modificación (Inmutabilidad)
        if self.pk:
            raise ValidationError("Los registros de auditoría son inmutables y no se pueden modificar.")

        # Aseguramos consistencia usando una transacción atómica y bloqueo pesimista
        with transaction.atomic():
            # 1. Obtener el último hash de la cadena
            last_log = AuditLog.objects.select_for_update().last()
            
            if last_log:
                self.previous_hash = last_log.current_hash
            else:
                # Bloque Génesis: Si es el primer registro del sistema, usamos 64 ceros
                self.previous_hash = '0' * 64

            # 2. Serializar el payload a string garantizando que las llaves estén ordenadas
            payload_string = json.dumps(self.payload, sort_keys=True)

            # 3. Calcular el hash actual (hash_n = SHA256(hash_n-1 + payload_n))
            hasher = hashlib.sha256()
            hasher.update(f"{self.previous_hash}{payload_string}".encode('utf-8'))
            self.current_hash = hasher.hexdigest()

            super().save(*args, **kwargs)

    @classmethod
    def verify_chain(cls):
        """
        Recorre secuencialmente toda la tabla de auditoría recreando los hashes en memoria.
        Retorna (True, None) si todo es íntegro.
        Retorna (False, id_corrupto) si encuentra un eslabón roto.
        """
        logs = cls.objects.all().order_by('id')
        expected_previous_hash = '0' * 64

        for log in logs:
            # Validación A: ¿El hash anterior grabado coincide con el eslabón real de la cadena?
            if log.previous_hash != expected_previous_hash:
                return False, log.id

            # Validación B: Volver a calcular el SHA256 con el payload real de la BD
            payload_string = json.dumps(log.payload, sort_keys=True)
            hasher = hashlib.sha256()
            hasher.update(f"{log.previous_hash}{payload_string}".encode('utf-8'))
            calculated_current_hash = hasher.hexdigest()

            # Si el hash guardado no coincide con el calculado, significa que el payload fue alterado
            if log.current_hash != calculated_current_hash:
                return False, log.id

            # El hash actual de este registro se convierte en el previo esperado para el siguiente
            expected_previous_hash = log.current_hash

        return True, None

class SuspiciousActivity(models.Model):
    RULE_CHOICES = [
        ('MULTIPLE_ACCOUNTS_SAME_IP', 'Misma IP con múltiples cuentas'),
        ('IDENTICAL_GROUP_BETTING', 'Patrón de apuestas idénticas en grupo'),
        ('IMMEDIATE_DEPOSIT_CASHOUT', 'Depósito inmediato seguido de Cash-Out'),
    ]
    
    STATUS_CHOICES = [
        ('PENDING', 'Pendiente de Revisión'),
        ('REVIEWED', 'Revisado / Confirmado'),
        ('DISMISSED', 'Descartado / Falso Positivo'),
    ]

    # Usamos el modelo de usuario configurado en el proyecto (usualmente auth.User o custom)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='suspicious_activities',
        null=True, blank=True,
        help_text="Usuario principal involucrado (si aplica)"
    )
    rule_triggered = models.CharField(max_length=30, choices=RULE_CHOICES)
    severity = models.CharField(max_length=10, default='MEDIUM', choices=[('LOW', 'Baja'), ('MEDIUM', 'Media'), ('HIGH', 'Alta')])
    details = models.JSONField(help_text="Pruebas recolectadas (IPs, IDs de apuestas, marcas de tiempo)")
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        db_table = 'api_suspicious_activity'

    def __str__(self):
        return f"Alerta {self.rule_triggered} - Estado: {self.status}"