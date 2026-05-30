import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from config.choices import TipoBono, EstadoBono, TipoAlertaAbuso


class Bono(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="bonos",
    )
    tipo = models.CharField(max_length=20, choices=TipoBono.choices)
    monto = models.DecimalField(max_digits=10, decimal_places=4)
    rollover_multiplier = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal("5.00"),
        help_text="Veces que debe apostarse el monto antes de retirar",
    )
    rollover_requerido = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        help_text="monto * rollover_multiplier",
    )
    rollover_apostado = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        default=Decimal("0.0000"),
    )
    cuota_minima_rollover = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=Decimal("1.5000"),
        help_text="Cuota mínima para que una apuesta cuente al rollover",
    )
    estado = models.CharField(
        max_length=20,
        choices=EstadoBono.choices,
        default=EstadoBono.ACTIVO,
    )
    creado = models.DateTimeField(auto_now_add=True)
    expira = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Fecha de expiración del bono",
    )

    class Meta:
        ordering = ["-creado"]
        indexes = [
            models.Index(fields=["usuario", "estado"]),
        ]

    def save(self, *args, **kwargs):
        if not self.rollover_requerido:
            self.rollover_requerido = self.monto * self.rollover_multiplier
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Bono {self.tipo} - {self.usuario.username} - {self.monto}"

    @property
    def rollover_completado(self):
        return self.rollover_apostado >= self.rollover_requerido

    @property
    def rollover_progreso(self):
        if self.rollover_requerido == 0:
            return Decimal("100.00")
        return (self.rollover_apostado / self.rollover_requerido * Decimal("100")).quantize(
            Decimal("0.01")
        )

    def expirar_si_corresponde(self):
        if self.estado == EstadoBono.ACTIVO and self.expira and self.expira < timezone.now():
            self.estado = EstadoBono.EXPIRADO
            self.save()
            return True
        return False


class BonoApuesta(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bono = models.ForeignKey(
        Bono,
        on_delete=models.CASCADE,
        related_name="apuestas",
    )
    apuesta = models.ForeignKey(
        "betting.Apuesta",
        on_delete=models.CASCADE,
        related_name="bonos_asociados",
    )
    monto_aportado = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        help_text="Monto de la apuesta que cuenta para el rollover",
    )
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["bono", "apuesta"]
        ordering = ["-creado"]

    def __str__(self):
        return f"BonoApuesta {self.bono.id} -> Apuesta {self.apuesta.id}"


class AlertaAbuso(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="alertas_abuso",
    )
    bono = models.ForeignKey(
        Bono,
        on_delete=models.CASCADE,
        related_name="alertas",
    )
    tipo = models.CharField(max_length=20, choices=TipoAlertaAbuso.choices)
    detalle = models.JSONField(
        default=dict,
        help_text="Detalles técnicos de la detección (apuestas involucradas, coberturas, etc.)",
    )
    revisado = models.BooleanField(default=False)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creado"]
        indexes = [
            models.Index(fields=["revisado", "creado"]),
        ]

    def __str__(self):
        return f"Alerta {self.tipo} - {self.usuario.username} - {self.creado.strftime('%Y-%m-%d')}"
