from rest_framework import generics, status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.contrib.auth import authenticate, login
from config.choices import EstadoPerfil
from .serializers import RegistroUsuarioSerializer, LoginSerializer
from .models import TipoAutoexclusion


class RegistroUsuarioAPIView(generics.CreateAPIView):
    serializer_class = RegistroUsuarioSerializer
    permission_classes = [permissions.AllowAny]


class LoginAPIView(APIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = LoginSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        username = serializer.validated_data.get("username")
        password = serializer.validated_data.get("password")
        user = authenticate(request, username=username, password=password)

        if user is not None:
            # Validar estados de cuenta (KYC y Juego Responsable)
            perfil = getattr(user, "perfil", None)
            if perfil:
                if perfil.estado == EstadoPerfil.BLOQUEADO:
                    return Response(
                        {"detail": "Esta cuenta está bloqueada por el operador."},
                        status=status.HTTP_403_FORBIDDEN,
                    )
                elif perfil.estado == EstadoPerfil.PENDIENTE_VERIFICACION:
                    return Response(
                        {"detail": "La cuenta está pendiente de verificación."},
                        status=status.HTTP_403_FORBIDDEN,
                    )
                elif perfil.esta_autoexcluido:
                    detail = (
                        "Cuenta autoexcluida voluntariamente de forma indefinida."
                        if perfil.tipo_autoexclusion == TipoAutoexclusion.INDEFINIDA
                        else f"Cuenta autoexcluida voluntariamente hasta el {perfil.fecha_autoexclusion_hasta.strftime('%d/%m/%Y %H:%M')}."
                    )
                    return Response(
                        {"detail": detail}, status=status.HTTP_403_FORBIDDEN
                    )
                elif perfil.estado == EstadoPerfil.AUTOEXCLUIDO:
                    # Si venció el plazo de autoexclusión, rehabilitar
                    perfil.estado = EstadoPerfil.VERIFICADO
                    perfil.tipo_autoexclusion = TipoAutoexclusion.NINGUNA
                    perfil.save()

            login(request, user)
            return Response(
                {
                    "message": "Sesión iniciada con éxito.",
                    "user": {
                        "username": user.username,
                        "email": user.email,
                        "first_name": user.first_name,
                        "last_name": user.last_name,
                        "estado": perfil.estado if perfil else "verificado",
                    },
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            {"detail": "Nombre de usuario o contraseña incorrectos."},
            status=status.HTTP_400_BAD_REQUEST,
        )
