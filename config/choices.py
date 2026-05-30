from django.db import models


class EstadoPerfil(models.TextChoices):
    PENDIENTE_VERIFICACION = "pendiente_verificacion", "Pendiente Verificación"
    VERIFICADO = "verificado", "Verificado"
    BLOQUEADO = "bloqueado", "Bloqueado"
    AUTOEXCLUIDO = "autoexcluido", "Autoexcluido"


class TipoAutoexclusion(models.TextChoices):
    NINGUNA = "ninguna", "Ninguna"
    DIAS_7 = "7_dias", "7 días"
    DIAS_30 = "30_dias", "30 días"
    DIAS_90 = "90_dias", "90 días"
    INDEFINIDA = "indefinida", "Indefinida"


class TipoLimite(models.TextChoices):
    DIARIO = "diario", "Diario"
    SEMANAL = "semanal", "Semanal"
    MENSUAL = "mensual", "Mensual"


class TipoCuenta(models.TextChoices):
    WALLET_USUARIO = "wallet_usuario", "Billetera del Usuario"
    CASA = "casa", "Casa de Apuestas"
    APUESTAS_PENDIENTES = "apuestas_pendientes", "Apuestas Pendientes"
    BONOS = "bonos", "Bonos"
    BONOS_USUARIO = "bonos_usuario", "Bonos del Usuario"


class TipoBono(models.TextChoices):
    BIENVENIDA = "bienvenida", "Bono de Bienvenida"
    RECARGA = "recarga", "Bono de Recarga"
    MANUAL = "manual", "Bono Manual (Operador)"


class EstadoBono(models.TextChoices):
    ACTIVO = "activo", "Activo"
    COMPLETADO = "completado", "Completado"
    EXPIRADO = "expirado", "Expirado"
    REVOCADO = "revocado", "Revocado por Abuso"


class TipoAlertaAbuso(models.TextChoices):
    RISK_FREE = "risk_free", "Apuesta Sin Riesgo"
    MATCHED_BETTING = "matched_betting", "Matched Betting"
    ARBITRAGE = "arbitrage", "Arbitraje"


class Direccion(models.TextChoices):
    DEBIT = "DEBIT", "Débito"
    CREDIT = "CREDIT", "Crédito"


class EstadoEvento(models.TextChoices):
    PROGRAMADO = "programado", "Programado"
    EN_VIVO = "en_vivo", "En Vivo"
    FINALIZADO = "finalizado", "Finalizado"
    SUSPENDIDO = "suspendido", "Suspendido"
    ANULADO = "anulado", "Anulado"


class EstadoApuesta(models.TextChoices):
    ACCEPTED = "accepted", "Aceptada"
    CASHED_OUT = "cashed_out", "Retirada"
    WON = "won", "Ganada"
    LOST = "lost", "Perdida"
    CANCELLED = "cancelled", "Cancelada"


class TipoApuesta(models.TextChoices):
    SIMPLE = "SIMPLE", "Simple"
    COMBINADA = "COMBINADA", "Combinada"


class TipoAccionAuditoria(models.TextChoices):
    BET_CREATED = 'BET_CREATED', 'Apuesta Creada'
    BET_SETTLED = 'BET_SETTLED', 'Apuesta Liquidada'
    WALLET_MOVEMENT = 'WALLET_MOVEMENT', 'Movimiento de Wallet'
    ODDS_CHANGED = 'ODDS_CHANGED', 'Cambio de Cuotas'


class ReglaActividadSospechosa(models.TextChoices):
    MULTIPLE_ACCOUNTS_SAME_IP = 'MULTIPLE_ACCOUNTS_SAME_IP', 'Misma IP con múltiples cuentas'
    IDENTICAL_GROUP_BETTING = 'IDENTICAL_GROUP_BETTING', 'Patrón de apuestas idénticas en grupo'
    IMMEDIATE_DEPOSIT_CASHOUT = 'IMMEDIATE_DEPOSIT_CASHOUT', 'Depósito inmediato seguido de Cash-Out'


class EstadoActividadSospechosa(models.TextChoices):
    PENDING = 'PENDING', 'Pendiente de Revisión'
    REVIEWED = 'REVIEWED', 'Revisado / Confirmado'
    DISMISSED = 'DISMISSED', 'Descartado / Falso Positivo'


class SeveridadActividadSospechosa(models.TextChoices):
    LOW = 'LOW', 'Baja'
    MEDIUM = 'MEDIUM', 'Media'
    HIGH = 'HIGH', 'Alta'



