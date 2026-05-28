from rest_framework import serializers
from django.contrib.auth.models import User
from django.db import transaction
from .models import PerfilUsuario
from config.choices import EstadoPerfil
from .validators import validar_dni, validar_mayor_edad


class RegistroUsuarioSerializer(serializers.ModelSerializer):
    fecha_nacimiento = serializers.DateField(write_only=True)
    dni = serializers.CharField(max_length=8, write_only=True)
    password = serializers.CharField(
        write_only=True, min_length=6, style={"input_type": "password"}
    )

    class Meta:
        model = User
        fields = [
            "username",
            "email",
            "password",
            "first_name",
            "last_name",
            "fecha_nacimiento",
            "dni",
        ]
        extra_kwargs = {
            "email": {"required": True},
            "first_name": {"required": True},
            "last_name": {"required": True},
        }

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError(
                "Este correo electrónico ya está registrado."
            )
        return value

    def validate_dni(self, value):
        if PerfilUsuario.objects.filter(dni=value).exists():
            raise serializers.ValidationError("Este DNI ya está registrado.")
        # Validar formato
        from django.core.exceptions import ValidationError as DjangoValidationError

        try:
            validar_dni(value)
        except DjangoValidationError as e:
            raise serializers.ValidationError(e.messages)
        return value

    def validate_fecha_nacimiento(self, value):
        validar_mayor_edad(value)
        return value

    def create(self, validated_data):
        fecha_nacimiento = validated_data.pop("fecha_nacimiento")
        dni = validated_data.pop("dni")
        password = validated_data.pop("password")

        with transaction.atomic():
            # Crear el usuario base de Django
            user = User.objects.create_user(
                username=validated_data["username"],
                email=validated_data["email"],
                password=password,
                first_name=validated_data.get("first_name", ""),
                last_name=validated_data.get("last_name", ""),
            )
            # Crear el perfil del usuario (estado verificado por defecto tras pasar el KYC)
            PerfilUsuario.objects.create(
                user=user,
                fecha_nacimiento=fecha_nacimiento,
                dni=dni,
                estado=EstadoPerfil.VERIFICADO,
            )

        return user


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(required=True)
    password = serializers.CharField(
        required=True, write_only=True, style={"input_type": "password"}
    )
