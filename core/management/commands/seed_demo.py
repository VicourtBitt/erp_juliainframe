"""Populate the database with sample data to try the app locally."""

from datetime import timedelta
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from finance.models import Category, EntryType, Transaction
from receipts.models import Receipt, ReceiptItem
from receipts.views import _save_pdf


class Command(BaseCommand):
    help = "Cria dados de demonstração (e o usuário demo/demo12345 se não existir)."

    def handle(self, *args, **opts):
        User = get_user_model()
        if not User.objects.filter(username="demo").exists():
            User.objects.create_superuser("demo", password="demo12345")
            self.stdout.write("Usuário demo / demo12345 criado.")

        cats = {
            name: Category.objects.get_or_create(name=name, type=kind)[0]
            for name, kind in [
                ("Ensaio fotográfico", EntryType.SALE), ("Cobertura de evento", EntryType.SALE),
                ("Equipamento", EntryType.EXPENSE), ("Aluguel de estúdio", EntryType.EXPENSE),
                ("Software", EntryType.EXPENSE), ("Transporte", EntryType.EXPENSE),
            ]
        }
        today = timezone.localdate()
        start = (today - relativedelta(months=4)).replace(day=5)
        samples = [
            ("Ensaio gestante – Carla", "Ensaio fotográfico", "650.00", 0, 2),
            ("Casamento Ana & Pedro", "Cobertura de evento", "4800.00", 1, 4),
            ("Ensaio corporativo – Acme", "Ensaio fotográfico", "1200.00", 2, 1),
            ("Aniversário 15 anos – Bia", "Cobertura de evento", "2500.00", 3, 3),
            ("Ensaio família Souza", "Ensaio fotográfico", "480.00", 4, 1),
            ("Lente 50mm", "Equipamento", "1890.00", 0, 6),
            ("Adobe Creative Cloud", "Software", "120.00", 0, 1),
            ("Adobe Creative Cloud", "Software", "120.00", 1, 1),
            ("Adobe Creative Cloud", "Software", "120.00", 2, 1),
            ("Adobe Creative Cloud", "Software", "120.00", 3, 1),
            ("Estúdio – diárias", "Aluguel de estúdio", "900.00", 1, 3),
            ("Uber eventos", "Transporte", "210.00", 3, 1),
        ]
        for desc, cat, total, month_offset, count in samples:
            when = start + relativedelta(months=month_offset)
            tx = Transaction.create_with_installments(
                description=desc, category=cats[cat], total_amount=Decimal(total),
                transaction_date=when, installments_count=count,
            )
            for inst in tx.installments.filter(due_date__lt=today - timedelta(days=10)):
                if inst.pk % 4:  # leave a few overdue on purpose
                    inst.mark_paid(inst.due_date)

        receipt = Receipt.objects.create(
            payer_name="Carla Mendes", payer_document="123.456.789-00",
            payee_name="Ju Fotografia ME", payee_document="12.345.678/0001-90",
            issue_date=today, location="Porto Alegre - RS",
        )
        ReceiptItem.objects.create(receipt=receipt, description="Ensaio gestante (2h, 40 fotos editadas)", price=Decimal("550"))
        ReceiptItem.objects.create(receipt=receipt, description="Deslocamento", price=Decimal("100"))
        _save_pdf(receipt)
        self.stdout.write(self.style.SUCCESS("Dados de demonstração criados."))
