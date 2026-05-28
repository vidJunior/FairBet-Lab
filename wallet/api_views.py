from rest_framework import generics, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .serializers import DepositoSerializer, RetiroSerializer
from . import services


class DepositoAPIView(generics.CreateAPIView):
    serializer_class = DepositoSerializer
    permission_classes = [permissions.IsAuthenticated]


class RetiroAPIView(generics.CreateAPIView):
    serializer_class = RetiroSerializer
    permission_classes = [permissions.IsAuthenticated]


class SaldoAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user
        desglose = services.obtener_desglose_saldos(user)
        return Response(
            {
                "saldo_disponible": desglose["wallet"],
                "apuestas_pendientes": desglose["apuestas_pendientes"],
                "bonos": desglose["bonos"],
            },
            status=status.HTTP_200_OK,
        )


class HistorialAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user
        entries = services.LedgerEntry.objects.filter(user=user).order_by(
            "-creado_en"
        )[:50]

        data = []
        for entry in entries:
            data.append(
                {
                    "id": entry.id,
                    "account": entry.account,
                    "amount": entry.amount,
                    "direction": entry.direction,
                    "tipo_transaccion": entry.tipo_transaccion,
                    "descripcion": entry.descripcion,
                    "creado_en": entry.creado_en,
                }
            )

        return Response(data, status=status.HTTP_200_OK)
