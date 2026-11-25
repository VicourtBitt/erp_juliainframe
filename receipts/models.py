from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


class Receipt(models.Model):
    payer_name = models.CharField("contratante (quem paga)", max_length=200)
    payer_document = models.CharField("CPF/CNPJ do contratante", max_length=20)
    payee_name = models.CharField("contratado (quem recebe)", max_length=200)
    payee_document = models.CharField("CPF/CNPJ do contratado", max_length=20)
    issue_date = models.DateField("data do pagamento/emissão", default=timezone.localdate)
    location = models.CharField("cidade e estado", max_length=120)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"), editable=False)
    pdf = models.FileField(upload_to="receipts/%Y/%m/", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "recibo"
        ordering = ["-issue_date", "-id"]

    def __str__(self):
        return self.filename

    @property
    def filename(self):
        return f"recibo_{slugify(self.payer_name) or 'cliente'}_{self.issue_date:%Y%m%d}_{self.pk}.pdf"

    @property
    def number(self):
        return f"{self.issue_date:%Y}-{self.pk:05d}"

    def recompute_total(self):
        self.total = sum((item.price for item in self.items.all()), Decimal("0"))


class ReceiptItem(models.Model):
    receipt = models.ForeignKey(Receipt, on_delete=models.CASCADE, related_name="items")
    description = models.TextField("descrição")
    price = models.DecimalField(
        "valor", max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )

    class Meta:
        verbose_name = "item do recibo"
        ordering = ["id"]

    def __str__(self):
        return self.description[:50]
