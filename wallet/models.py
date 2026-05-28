import uuid
from decimal import Decimal
from django.db import models, transaction as db_transaction
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from config.choices import DireccionLedger, TipoCuenta, TipoTransaccion


class LedgerEntry(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="ledger_entries",
        null=True,
        blank=True,
    )
    account = models.CharField(max_length=50, choices=TipoCuenta.choices)
    amount = models.DecimalField(max_digits=18, decimal_places=4)
    direction = models.CharField(max_length=10, choices=DireccionLedger.choices)
    transaction_id = models.UUIDField(db_index=True)
    tipo_transaccion = models.CharField(
        max_length=30, choices=TipoTransaccion.choices
    )
    descripcion = models.TextField(blank=True, default="")
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["creado_en", "id"]
        indexes = [
            models.Index(fields=["user", "account", "creado_en"]),
            models.Index(fields=["transaction_id"]),
        ]

    def __str__(self):
        user_str = self.user.username if self.user else "Sistema"
        return f"[{self.direction}] {user_str} / {self.account}: {self.amount} (tx: {self.transaction_id})"

    @property
    def signed_amount(self):
        if self.direction == DireccionLedger.CREDIT:
            return self.amount
        return -self.amount

    @classmethod
    def get_saldo_usuario(cls, user):
        return cls.objects.filter(user=user).aggregate(
            total=models.Sum(
                models.Case(
                    models.When(
                        direction=DireccionLedger.CREDIT,
                        then=models.F("amount"),
                    ),
                    models.When(
                        direction=DireccionLedger.DEBIT,
                        then=models.F("amount") * -1,
                    ),
                    output_field=models.DecimalField(max_digits=18, decimal_places=4),
                )
            )
        )["total"] or Decimal("0.0000")

    @classmethod
    def get_saldo_cuenta_usuario(cls, user, account):
        return cls.objects.filter(user=user, account=account).aggregate(
            total=models.Sum(
                models.Case(
                    models.When(
                        direction=DireccionLedger.CREDIT,
                        then=models.F("amount"),
                    ),
                    models.When(
                        direction=DireccionLedger.DEBIT,
                        then=models.F("amount") * -1,
                    ),
                    output_field=models.DecimalField(max_digits=18, decimal_places=4),
                )
            )
        )["total"] or Decimal("0.0000")

    @classmethod
    def crear_transaccion(cls, entradas, tipo_transaccion, user=None, descripcion=""):
        if len(entradas) < 2:
            raise ValidationError(
                "Una transaccion de partida doble requiere al menos 2 entradas."
            )

        total = Decimal("0.0000")
        for e in entradas:
            if e["direction"] == DireccionLedger.CREDIT:
                total += e["amount"]
            else:
                total -= e["amount"]

        if abs(total) > Decimal("0.00001"):
            raise ValidationError(
                f"La suma de las entradas debe ser cero. Suma actual: {total}"
            )

        transaction_id = uuid.uuid4()

        with db_transaction.atomic():
            entradas_creadas = []
            for entrada in entradas:
                entry = cls.objects.create(
                    user=entrada.get("user", user),
                    account=entrada["account"],
                    amount=entrada["amount"],
                    direction=entrada["direction"],
                    transaction_id=transaction_id,
                    tipo_transaccion=tipo_transaccion,
                    descripcion=descripcion,
                )
                entradas_creadas.append(entry)

        return transaction_id, entradas_creadas
