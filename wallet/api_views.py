from django.core.exceptions import ValidationError
from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from config.choices import TipoCuenta
from wallet.models import LedgerEntry
from wallet.serializers import RecargaSerializer, RetiroSerializer, SaldoSerializer
from wallet import services


class SaldoAPIView(GenericAPIView):
    """
    GET /api/wallet/saldo/
    """

    permission_classes = [IsAuthenticated]
    serializer_class = SaldoSerializer

    def get(self, request, *args, **kwargs):
        user = request.user
        data = {
            "wallet_usuario": LedgerEntry.get_balance(user, TipoCuenta.WALLET_USUARIO),
            "apuestas_pendientes": LedgerEntry.get_balance(
                user, TipoCuenta.APUESTAS_PENDIENTES
            ),
            "bonos": LedgerEntry.get_balance(user, TipoCuenta.BONOS),
        }
        serializer = self.get_serializer(data)
        return Response(serializer.data)


class RecargaAPIView(GenericAPIView):
    """
    POST /api/wallet/recargar/
    """

    permission_classes = [IsAuthenticated]
    serializer_class = RecargaSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            tid = services.recargar(
                user=request.user,
                amount=serializer.validated_data["amount"],
            )
        except ValidationError as e:
            return Response({"detail": e.message}, status=status.HTTP_400_BAD_REQUEST)

        saldo = LedgerEntry.get_balance(request.user, TipoCuenta.WALLET_USUARIO)
        return Response(
            {"transaction_id": tid, "saldo_disponible": saldo},
            status=status.HTTP_201_CREATED,
        )


class RetiroAPIView(GenericAPIView):
    """
    POST /api/wallet/retirar/
    """

    permission_classes = [IsAuthenticated]
    serializer_class = RetiroSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            tid = services.retirar(
                user=request.user,
                amount=serializer.validated_data["amount"],
            )
        except ValidationError as e:
            return Response({"detail": e.message}, status=status.HTTP_400_BAD_REQUEST)

        saldo = LedgerEntry.get_balance(request.user, TipoCuenta.WALLET_USUARIO)
        return Response(
            {"transaction_id": tid, "saldo_disponible": saldo},
            status=status.HTTP_200_OK,
        )
