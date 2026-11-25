from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from dateutil.relativedelta import relativedelta
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.utils import timezone


class EntryType(models.TextChoices):
    SALE = "sale", "Venda (entrada)"
    EXPENSE = "expense", "Despesa (saída)"


class Category(models.Model):
    name = models.CharField("nome", max_length=120)
    type = models.CharField("tipo", max_length=10, choices=EntryType.choices)

    class Meta:
        verbose_name = "categoria"
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["name", "type"], name="unique_category_per_type")]

    def __str__(self):
        return f"{self.name} ({self.get_type_display()})"


class Transaction(models.Model):
    """A sale or an expense, split into one or more monthly installments."""

    description = models.CharField("descrição", max_length=255)
    category = models.ForeignKey(
        Category, verbose_name="categoria", on_delete=models.PROTECT, related_name="transactions"
    )
    # Denormalised from the category at creation time so history stays
    # consistent if a category is later edited.
    type = models.CharField("tipo", max_length=10, choices=EntryType.choices, editable=False)
    total_amount = models.DecimalField(
        "valor total", max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    transaction_date = models.DateField("data da operação", default=date.today)
    installments_count = models.PositiveSmallIntegerField(
        "parcelas", default=1, validators=[MinValueValidator(1)]
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "transação"
        verbose_name_plural = "transações"
        ordering = ["-transaction_date", "-id"]

    def __str__(self):
        return self.description

    @property
    def paid_amount(self):
        return sum((i.amount for i in self.installments.all() if i.status == Installment.Status.PAID), Decimal("0"))

    @classmethod
    @transaction.atomic
    def create_with_installments(cls, *, description, category, total_amount, transaction_date, installments_count):
        obj = cls.objects.create(
            description=description,
            category=category,
            type=category.type,
            total_amount=total_amount,
            transaction_date=transaction_date,
            installments_count=installments_count,
        )
        obj.rebuild_installments()
        return obj

    def rebuild_installments(self):
        """(Re)create the installment schedule: one per month from the operation date.

        Values are rounded to cents and the last installment absorbs the
        rounding difference, so the installments always add up to the total.
        """
        self.installments.all().delete()
        total = Decimal(self.total_amount)
        count = int(self.installments_count)
        base = (total / count).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        values = [base] * count
        values[-1] = total - base * (count - 1)
        Installment.objects.bulk_create(
            Installment(
                transaction=self,
                number=i + 1,
                amount=values[i],
                due_date=self.transaction_date + relativedelta(months=i),
            )
            for i in range(count)
        )


class InstallmentQuerySet(models.QuerySet):
    def overdue(self):
        return self.filter(status=Installment.Status.PENDING, due_date__lt=timezone.localdate())


class Installment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendente"
        PAID = "paid", "Pago"

    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name="installments")
    number = models.PositiveSmallIntegerField("nº parcela")
    amount = models.DecimalField("valor", max_digits=12, decimal_places=2)
    due_date = models.DateField("vencimento")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    payment_date = models.DateField("data de pagamento", null=True, blank=True)

    objects = InstallmentQuerySet.as_manager()

    class Meta:
        verbose_name = "parcela"
        ordering = ["due_date", "transaction_id", "number"]
        constraints = [
            models.UniqueConstraint(fields=["transaction", "number"], name="unique_installment_number")
        ]

    def __str__(self):
        return f"{self.transaction} – {self.number}/{self.transaction.installments_count}"

    @property
    def is_overdue(self):
        return self.status == self.Status.PENDING and self.due_date < timezone.localdate()

    @property
    def display_status(self):
        """'paid', 'pending' or 'overdue' (overdue is derived, never stored)."""
        if self.status == self.Status.PAID:
            return "paid"
        return "overdue" if self.is_overdue else "pending"

    def mark_paid(self, when=None):
        self.status = self.Status.PAID
        self.payment_date = when or timezone.localdate()
        self.save(update_fields=["status", "payment_date"])

    def mark_pending(self):
        self.status = self.Status.PENDING
        self.payment_date = None
        self.save(update_fields=["status", "payment_date"])
