from datetime import timedelta
from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone
from config.choices import EstadoPerfil, TipoAutoexclusion, TipoLimite


class PerfilUsuario(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="perfil")
    fecha_nacimiento = models.DateField()
    dni = models.CharField(max_length=8, unique=True)
    estado = models.CharField(
        max_length=30,
        choices=EstadoPerfil.choices,
        default=EstadoPerfil.PENDIENTE_VERIFICACION,
    )

    # Juego Responsable - Límites Activos
    limite_deposito_diario = models.DecimalField(
        max_digits=18, decimal_places=4, default=1000.0000
    )
    limite_deposito_semanal = models.DecimalField(
        max_digits=18, decimal_places=4, default=5000.0000
    )
    limite_deposito_mensual = models.DecimalField(
        max_digits=18, decimal_places=4, default=20000.0000
    )

    # Autoexclusión
    tipo_autoexclusion = models.CharField(
        max_length=20,
        choices=TipoAutoexclusion.choices,
        default=TipoAutoexclusion.NINGUNA,
    )
    fecha_autoexclusion_hasta = models.DateTimeField(null=True, blank=True)

    # Solicitudes de Incremento de Límite Pendientes
    limite_pendiente = models.DecimalField(
        max_digits=18, decimal_places=4, null=True, blank=True
    )
    tipo_limite_pendiente = models.CharField(
        max_length=20,
        choices=TipoLimite.choices,
        null=True,
        blank=True,
    )
    fecha_solicitud_incremento = models.DateTimeField(null=True, blank=True)

    def clean(self):
        super().clean()
        if self.pk:
            original = PerfilUsuario.objects.only("tipo_autoexclusion").get(pk=self.pk)
            if (
                original.tipo_autoexclusion == TipoAutoexclusion.INDEFINIDA
                and self.tipo_autoexclusion != TipoAutoexclusion.INDEFINIDA
            ):
                raise ValidationError(
                    "No se permite revertir una autoexclusión indefinida."
                )

    def save(self, *args, **kwargs):
        self.full_clean()

        if self.pk:
            original = PerfilUsuario.objects.only("tipo_autoexclusion").get(pk=self.pk)
            cambio_autoexclusion = (
                original.tipo_autoexclusion != self.tipo_autoexclusion
            )
        else:
            cambio_autoexclusion = True

        if cambio_autoexclusion:
            dias = {
                TipoAutoexclusion.DIAS_7: 7,
                TipoAutoexclusion.DIAS_30: 30,
                TipoAutoexclusion.DIAS_90: 90,
            }.get(self.tipo_autoexclusion)

            self.fecha_autoexclusion_hasta = (
                timezone.now() + timedelta(days=dias) if dias else None
            )

            if self.tipo_autoexclusion != TipoAutoexclusion.NINGUNA:
                self.estado = EstadoPerfil.AUTOEXCLUIDO
            elif self.estado == EstadoPerfil.AUTOEXCLUIDO:
                self.estado = EstadoPerfil.VERIFICADO

        super().save(*args, **kwargs)

    @property
    def esta_autoexcluido(self):
        return self.tipo_autoexclusion == TipoAutoexclusion.INDEFINIDA or (
            self.fecha_autoexclusion_hasta is not None
            and timezone.now() < self.fecha_autoexclusion_hasta
        )

    def solicitar_cambio_limite(self, tipo_limite, nuevo_valor):
        if tipo_limite not in TipoLimite.values:
            raise ValidationError("Tipo de límite no válido.")

        current_field = f"limite_deposito_{tipo_limite}"
        current_value = getattr(self, current_field)

        if nuevo_valor == current_value:
            if self.tipo_limite_pendiente == tipo_limite:
                self.limite_pendiente = self.tipo_limite_pendiente = (
                    self.fecha_solicitud_incremento
                ) = None
                self.save()
            return

        # Reducción inmediata; incremento espera 24h de cooldown
        if nuevo_valor < current_value:
            setattr(self, current_field, nuevo_valor)
            if self.tipo_limite_pendiente == tipo_limite:
                self.limite_pendiente = self.tipo_limite_pendiente = (
                    self.fecha_solicitud_incremento
                ) = None
            self.save()
        else:
            if self.fecha_solicitud_incremento is not None:
                raise ValidationError(
                    "Ya existe una solicitud de incremento de límite pendiente."
                )

            self.limite_pendiente = nuevo_valor
            self.tipo_limite_pendiente = tipo_limite
            self.fecha_solicitud_incremento = timezone.now()
            self.save()

    def aplicar_limite_pendiente(self):
        """Aplica el límite pendiente tras el cooldown de 24h."""
        if self.fecha_solicitud_incremento:
            cooldown_limite = self.fecha_solicitud_incremento + timedelta(hours=24)
            if timezone.now() >= cooldown_limite:
                setattr(
                    self,
                    f"limite_deposito_{self.tipo_limite_pendiente}",
                    self.limite_pendiente,
                )

                self.limite_pendiente = self.tipo_limite_pendiente = (
                    self.fecha_solicitud_incremento
                ) = None
                self.save()
                return True
        return False

    def __str__(self):
        return f"{self.user.username} - DNI: {self.dni} ({self.estado})"
