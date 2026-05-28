from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.utils import timezone
from decimal import Decimal

from config.choices import EstadoEvento, EstadoApuesta


class Evento(models.Model):
    local = models.CharField(max_length=100)
    visitante = models.CharField(max_length=100)
    fecha_inicio = models.DateTimeField()
    estado = models.CharField(
        max_length=20,
        choices=EstadoEvento.choices,
        default=EstadoEvento.PROGRAMADO,
    )
    goles_local = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    goles_visitante = models.IntegerField(default=0, validators=[MinValueValidator(0)])

    def __str__(self):
        return f"{self.local} vs {self.visitante} ({self.get_estado_display()})"

    class Meta:
        db_table = "eventos"
        verbose_name = "Evento"
        verbose_name_plural = "Eventos"
        ordering = ["fecha_inicio"]


class Mercado(models.Model):
    evento = models.ForeignKey(Evento, on_delete=models.CASCADE, related_name="mercados")
    nombre = models.CharField(max_length=100, default="1X2")
    activo = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.nombre} - {self.evento}"

    class Meta:
        db_table = "mercados"
        verbose_name = "Mercado"
        verbose_name_plural = "Mercados"


class Seleccion(models.Model):
    mercado = models.ForeignKey(Mercado, on_delete=models.CASCADE, related_name="selecciones")
    nombre = models.CharField(max_length=100) # Local, Empate, Visitante
    cuota = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("1.0001"))]
    )

    def __str__(self):
        return f"{self.nombre} ({self.cuota}) - {self.mercado.evento}"

    class Meta:
        db_table = "selecciones"
        verbose_name = "Selección"
        verbose_name_plural = "Selecciones"


class Apuesta(models.Model):
    TIPO_CHOICES = [
        ("SIMPLE", "Simple"),
        ("COMBINADA", "Combinada"),
    ]

    usuario = models.ForeignKey(User, on_delete=models.PROTECT, related_name="apuestas")
    seleccion = models.ForeignKey(
        Seleccion,
        on_delete=models.PROTECT,
        related_name="apuestas_simples",
        null=True,
        blank=True,
    )
    selecciones = models.ManyToManyField(
        Seleccion,
        through="ApuestaSeleccion",
        related_name="apuestas",
    )
    monto = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0.1000"))]
    )
    cuota_fijada = models.DecimalField(max_digits=18, decimal_places=4)
    estado = models.CharField(
        max_length=20,
        choices=EstadoApuesta.choices,
        default=EstadoApuesta.ACCEPTED,
    )
    tipo = models.CharField(
        max_length=15,
        choices=TIPO_CHOICES,
        default="SIMPLE",
    )
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    @property
    def payout(self):
        return self.monto * self.cuota_fijada

    def clean(self):
        super().clean()
        # Nota: Permitimos apuestas en eventos en_vivo para las apuestas en vivo.
        if self.seleccion_id and self.seleccion.mercado.evento.estado not in [EstadoEvento.PROGRAMADO, EstadoEvento.EN_VIVO]:
            raise ValidationError("Solo se permiten apuestas en eventos programados o en vivo.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Apuesta #{self.id} ({self.tipo}) - {self.usuario.username} ({self.estado})"

    class Meta:
        db_table = "apuestas"
        verbose_name = "Apuesta"
        verbose_name_plural = "Apuestas"
        ordering = ["-creado"]


class ApuestaSeleccion(models.Model):
    apuesta = models.ForeignKey(Apuesta, on_delete=models.CASCADE, related_name="detalles")
    seleccion = models.ForeignKey(Seleccion, on_delete=models.PROTECT, related_name="detalles")
    cuota_fijada = models.DecimalField(max_digits=18, decimal_places=4)

    def __str__(self):
        return f"Detalle #{self.id} de Apuesta #{self.apuesta.id} - Seleccion: {self.seleccion.nombre}"

    class Meta:
        db_table = "apuestas_selecciones"
        unique_together = ("apuesta", "seleccion")
        verbose_name = "Detalle de Apuesta"
        verbose_name_plural = "Detalles de Apuesta"

