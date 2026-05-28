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
    WON = "won", "Ganada"
    LOST = "lost", "Perdida"
    CANCELLED = "cancelled", "Cancelada"

