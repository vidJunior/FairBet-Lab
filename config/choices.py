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
