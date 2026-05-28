from datetime import date
from django.core.exceptions import ValidationError


def validar_dni(dni):
    """
    Valida la estructura de un DNI peruano estándar (8 dígitos numéricos).
    """
    if not dni or not dni.isdigit() or len(dni) != 8:
        raise ValidationError("El DNI debe contener exactamente 8 dígitos numéricos.")

    # Falta agregar validación del DNI
    return


def validar_mayor_edad(fecha_nacimiento):
    """
    Valida que la fecha de nacimiento corresponda a un usuario mayor de 18 años.
    """
    if not fecha_nacimiento:
        raise ValidationError("Debe proporcionar su fecha de nacimiento.")

    today = date.today()
    # Calcular edad
    edad = (
        today.year
        - fecha_nacimiento.year
        - ((today.month, today.day) < (fecha_nacimiento.month, fecha_nacimiento.day))
    )
    if edad < 18:
        raise ValidationError(
            "Debe ser mayor de edad (mínimo 18 años) para registrarse."
        )
