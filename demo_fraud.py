import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from api.models import AuditLog, SuspiciousActivity
from config.choices import ReglaActividadSospechosa, SeveridadActividadSospechosa, EstadoActividadSospechosa, TipoAccionAuditoria
from django.contrib.auth.models import User

# 1. Crear una Alerta de Fraude falsa para que la vean en el panel web
admin_user = User.objects.filter(is_superuser=True).first() or User.objects.first()

SuspiciousActivity.objects.create(
    user=admin_user,
    rule_triggered=ReglaActividadSospechosa.MULTIPLE_ACCOUNTS_SAME_IP,
    severity=SeveridadActividadSospechosa.HIGH,
    details={"ip": "192.168.1.50", "cuentas_asociadas": ["user1", "user2", "user3"], "motivo": "Demostración de alerta"},
    status=EstadoActividadSospechosa.PENDING
)
print("✅ Alerta de Actividad Sospechosa creada. Revisa el panel web en /admin/api/suspiciousactivity/")

# 2. Romper la inmutabilidad de la cadena de Auditoría
# Vamos a crear un registro legítimo
log_legitimo = AuditLog(
    action_type=TipoAccionAuditoria.WALLET_MOVEMENT,
    payload={"msg": "Movimiento financiero", "ip": "127.0.0.1"}
)
log_legitimo.save()

# Ahora vamos a simular a un hacker modificando directamente la base de datos para borrar sus huellas
# Usamos .update() para bypasear la protección del método save() del modelo que nos impediría alterarlo
print(f"Modificando maliciosamente el log ID {log_legitimo.id}...")
AuditLog.objects.filter(id=log_legitimo.id).update(payload={"msg": "Registro borrado por hacker", "ip": "0.0.0.0"})

print("✅ Cadena de auditoría corrompida con éxito.")
print("👉 Entra ahora mismo a: http://localhost:8000/api/admin/audit/verify/ y verás cómo el sistema detecta la anomalía.")
