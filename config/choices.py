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


class DireccionLedger(models.TextChoices):
    DEBIT = "DEBIT", "Débito"
    CREDIT = "CREDIT", "Crédito"


class TipoCuenta(models.TextChoices):
    WALLET_USUARIO = "wallet_usuario", "Billetera Usuario"
    CASA = "casa", "Cuenta Casa"
    APUESTAS_PENDIENTES = "apuestas_pendientes", "Apuestas Pendientes"
    BONOS = "bonos", "Bonos"
    CASHOUT = "cashout", "Cash-Out"


class TipoTransaccion(models.TextChoices):
    DEPOSITO = "deposito", "Depósito"
    RETIRO = "retiro", "Retiro"
    APUESTA = "apuesta", "Apuesta"
    LIQUIDACION_GANADA = "liquidacion_ganada", "Liquidación Ganada"
    LIQUIDACION_PERDIDA = "liquidacion_perdida", "Liquidación Perdida"
    CASHOUT = "cashout", "Cash-Out"
    CANCELACION = "cancelacion", "Cancelación"
    BONO = "bono", "Bono"
    AJUSTE = "ajuste", "Ajuste"
