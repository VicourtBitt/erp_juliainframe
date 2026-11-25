"""Import data from the Streamlit app's Supabase tables and MongoDB collections.

Usage:
    pip install supabase pymongo
    SUPABASE_URL=... SUPABASE_KEY=... MONGO_URI=... MONGO_DB=... \\
        python manage.py import_legacy [--skip-supabase] [--skip-mongo] [--dry-run]

Supabase tables: categories, transactions, installments, contract_template, search_history
Mongo collections: contracts_dashboard, receipts_dashboard
"""

import os
from datetime import date, datetime
from datetime import timezone as dt_timezone
from decimal import Decimal

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.utils.text import slugify

from contracts.models import Contract, ContractTemplate
from finance.models import Category, EntryType, Installment, Transaction
from market.models import MarketAnalysis
from receipts.models import Receipt, ReceiptItem


class DryRun(Exception):
    pass


def _date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not value:
        return None
    return parse_date(str(value)[:10])


def _dec(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


class Command(BaseCommand):
    help = "Importa dados do app Streamlit antigo (Supabase + MongoDB)."

    def add_arguments(self, parser):
        parser.add_argument("--skip-supabase", action="store_true")
        parser.add_argument("--skip-mongo", action="store_true")
        parser.add_argument("--dry-run", action="store_true", help="Executa tudo e desfaz no final.")
        parser.add_argument("--allow-existing", action="store_true", help="Importa mesmo com dados já cadastrados.")

    def handle(self, *args, **opts):
        if not opts["allow_existing"] and (Transaction.objects.exists() or Receipt.objects.exists() or Contract.objects.exists()):
            raise CommandError("O banco já possui dados. Use --allow-existing para importar mesmo assim (pode duplicar).")
        try:
            with transaction.atomic():
                if not opts["skip_supabase"]:
                    self.import_supabase()
                if not opts["skip_mongo"]:
                    self.import_mongo()
                if opts["dry_run"]:
                    raise DryRun
        except DryRun:
            self.stdout.write(self.style.WARNING("Dry-run: nenhuma alteração foi gravada."))
        else:
            self.stdout.write(self.style.SUCCESS("Importação concluída."))

    # --- Supabase --------------------------------------------------------
    def _rows(self, client, table, columns="*"):
        rows, start, page = [], 0, 1000
        while True:
            batch = client.table(table).select(columns).range(start, start + page - 1).execute().data or []
            rows.extend(batch)
            if len(batch) < page:
                return rows
            start += page

    def import_supabase(self):
        try:
            from supabase import create_client
        except ImportError as exc:
            raise CommandError("Instale o cliente: pip install supabase") from exc
        url, key = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY")
        if not url or not key:
            raise CommandError("Defina SUPABASE_URL e SUPABASE_KEY.")
        client = create_client(url, key)

        categories = {}
        for row in self._rows(client, "categories"):
            entry_type = row.get("type") if row.get("type") in EntryType.values else EntryType.EXPENSE
            categories[row["id"]], _ = Category.objects.get_or_create(name=row["name"], type=entry_type)
        self.stdout.write(f"Categorias: {len(categories)}")

        transactions = {}
        for row in self._rows(client, "transactions"):
            entry_type = row.get("type") if row.get("type") in EntryType.values else EntryType.EXPENSE
            category = categories.get(row.get("category_id"))
            if category is None:
                category, _ = Category.objects.get_or_create(name="Sem Categoria", type=entry_type)
            tx = Transaction.objects.create(
                description=row.get("description") or "(sem descrição)",
                category=category,
                type=entry_type,
                total_amount=_dec(row.get("total_amount")),
                transaction_date=_date(row.get("transaction_date")) or timezone.localdate(),
                installments_count=max(int(row.get("installments_count") or 1), 1),
            )
            if row.get("created_at") and (created := parse_datetime(row["created_at"])):
                Transaction.objects.filter(pk=tx.pk).update(created_at=created)
            transactions[row["id"]] = tx
        self.stdout.write(f"Transações: {len(transactions)}")

        count = 0
        seen = set()
        for row in self._rows(client, "installments"):
            tx = transactions.get(row.get("transaction_id"))
            if tx is None:
                continue
            number = int(row.get("installment_number") or 1)
            while (tx.pk, number) in seen:  # guard against duplicated numbers in legacy data
                number += 1
            seen.add((tx.pk, number))
            paid = row.get("status") == "paid"
            Installment.objects.create(
                transaction=tx,
                number=number,
                amount=_dec(row.get("installment_amount")),
                due_date=_date(row.get("due_date")) or tx.transaction_date,
                status=Installment.Status.PAID if paid else Installment.Status.PENDING,
                payment_date=_date(row.get("payment_date")) if paid else None,
            )
            count += 1
        self.stdout.write(f"Parcelas: {count}")

        templates = 0
        for row in self._rows(client, "contract_template"):
            ContractTemplate.objects.get_or_create(
                title=row.get("title") or "Modelo",
                defaults={"category": row.get("category") or "", "content": row.get("content") or ""},
            )
            templates += 1
        self.stdout.write(f"Modelos de contrato: {templates}")

        analyses = 0
        for row in self._rows(client, "search_history"):
            ticker = row.get("ticker_clean") or ""
            obj = MarketAnalysis.objects.create(
                ticker=ticker,
                symbol=row.get("ticker_full") or ticker,
                company_name=row.get("company_name") or "",
                currency="BRL" if str(row.get("ticker_full", "")).endswith(".SA") else "USD",
                price=Decimal(str(row.get("current_price") or 0)),
                change_percent=Decimal(str(row.get("change_percent") or 0)),
                analysis_text=row.get("analysis_text") or "",
            )
            if row.get("created_at") and (created := parse_datetime(row["created_at"])):
                if timezone.is_naive(created):
                    created = timezone.make_aware(created, dt_timezone.utc)
                MarketAnalysis.objects.filter(pk=obj.pk).update(created_at=created)
            analyses += 1
        self.stdout.write(f"Análises de mercado: {analyses}")

    # --- Mongo -----------------------------------------------------------
    def import_mongo(self):
        try:
            from pymongo import MongoClient
        except ImportError as exc:
            raise CommandError("Instale o cliente: pip install pymongo") from exc
        uri, name = os.getenv("MONGO_URI"), os.getenv("MONGO_DB")
        if not uri or not name:
            raise CommandError("Defina MONGO_URI e MONGO_DB.")
        db = MongoClient(uri)[name]

        contracts = 0
        for doc in db.contracts_dashboard.find():
            content = doc.get("file_content")
            ext = (doc.get("file_extension") or "pdf").lower().lstrip(".")
            if not content:
                continue
            obj = Contract(
                name=doc.get("file_name") or "Contrato",
                contract_type=doc.get("contract_type") or Contract.Kind.OTHER,
                contract_date=_date(doc.get("contract_date")) or timezone.localdate(),
                value=_dec(doc.get("contract_value")),
                contractor=doc.get("contractor") or "",
            )
            obj.file.save(f"{slugify(obj.name) or 'contrato'}.{ext}", ContentFile(bytes(content)), save=False)
            obj.save()
            contracts += 1
        self.stdout.write(f"Contratos (arquivo): {contracts}")

        receipts = 0
        for doc in db.receipts_dashboard.find():
            receipt = Receipt.objects.create(
                payer_name=doc.get("contratante_nome") or "",
                payer_document=doc.get("contratante_doc") or "",
                payee_name=doc.get("contratado_nome") or "",
                payee_document=doc.get("contratado_doc") or "",
                issue_date=_date(doc.get("emission_date")) or timezone.localdate(),
                location=doc.get("servico_local") or "",
            )
            for item in doc.get("servicos") or []:
                if item.get("nome"):
                    ReceiptItem.objects.create(receipt=receipt, description=item["nome"], price=_dec(item.get("preco")))
            receipt.recompute_total()
            if doc.get("receipt_binary"):
                # Keep the PDF that was actually issued instead of re-rendering it.
                receipt.pdf.save(receipt.filename, ContentFile(bytes(doc["receipt_binary"])), save=False)
            receipt.save()
            receipts += 1
        self.stdout.write(f"Recibos: {receipts}")
