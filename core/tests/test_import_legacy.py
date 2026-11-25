import shutil
import sys
import tempfile
import types
from datetime import date, datetime
from decimal import Decimal
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase, override_settings

from contracts.models import Contract, ContractTemplate
from finance.models import Installment, Transaction
from market.models import MarketAnalysis
from receipts.models import Receipt

SUPABASE_DATA = {
    "categories": [{"id": "c1", "name": "Ensaio", "type": "sale"}, {"id": "c2", "name": "Aluguel", "type": "expense"}],
    "transactions": [
        {"id": 10, "description": "Ensaio X", "total_amount": 300.0, "type": "sale", "transaction_date": "2025-10-01",
         "installments_count": 2, "category_id": "c1", "created_at": "2025-10-01T12:00:00+00:00"},
        {"id": 11, "description": "Sem cat", "total_amount": 50.0, "type": "expense", "transaction_date": "2025-10-02",
         "installments_count": 1, "category_id": None, "created_at": "2025-10-02T12:00:00+00:00"},
    ],
    "installments": [
        {"id": 1, "transaction_id": 10, "installment_number": 1, "installment_amount": 150.0, "due_date": "2025-10-01",
         "status": "paid", "payment_date": "2025-10-03"},
        {"id": 2, "transaction_id": 10, "installment_number": 2, "installment_amount": 150.0, "due_date": "2025-11-01",
         "status": "pending", "payment_date": None},
        {"id": 3, "transaction_id": 11, "installment_number": 1, "installment_amount": 50.0, "due_date": "2025-10-02",
         "status": "pending", "payment_date": None},
    ],
    "contract_template": [{"id": 1, "title": "Modelo antigo", "category": "Geral", "content": "abc"}],
    "search_history": [{"ticker_clean": "PETR4", "ticker_full": "PETR4.SA", "company_name": "Petrobras",
                        "current_price": 38.1, "change_percent": 1.2, "analysis_text": "ok",
                        "created_at": "2025-10-05T10:00:00"}],
}


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def select(self, *_):
        return self

    def range(self, start, end):
        self.slice = (start, end + 1)
        return self

    def execute(self):
        return types.SimpleNamespace(data=self.rows[self.slice[0]:self.slice[1]])


class FakeSupabase:
    def table(self, name):
        return FakeQuery(SUPABASE_DATA[name])


class FakeCollection(list):
    def find(self):
        return iter(self)


MONGO = {
    "contracts_dashboard": FakeCollection([
        {"file_name": "Contrato Evento", "contract_type": "Contrato de Evento", "contract_date": "2025-09-01",
         "contract_value": 900.0, "contractor": "Pedro", "file_content": b"%PDF-1.4 fake", "file_extension": "pdf"},
    ]),
    "receipts_dashboard": FakeCollection([
        {"receipt_name": "r.pdf", "emission_date": datetime(2025, 9, 10), "contratante_nome": "Ana",
         "contratante_doc": "1", "contratado_nome": "Ju", "contratado_doc": "2",
         "servicos": [{"nome": "Ensaio", "preco": 200.0}, {"nome": "Extra", "preco": 50.5}],
         "servico_local": "POA", "total": 250.5, "receipt_binary": b"%PDF-1.4 old"},
    ]),
}

MEDIA = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA)
class ImportLegacyTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def run_import(self, *args):
        fake_supabase = types.ModuleType("supabase")
        fake_supabase.create_client = lambda url, key: FakeSupabase()
        fake_pymongo = types.ModuleType("pymongo")
        fake_pymongo.MongoClient = lambda uri: {"db": types.SimpleNamespace(**MONGO)}
        env = {"SUPABASE_URL": "x", "SUPABASE_KEY": "y", "MONGO_URI": "m", "MONGO_DB": "db"}
        with mock.patch.dict(sys.modules, {"supabase": fake_supabase, "pymongo": fake_pymongo}), \
                mock.patch.dict("os.environ", env):
            call_command("import_legacy", *args, stdout=StringIO())

    def test_import(self):
        self.run_import()
        self.assertEqual(Transaction.objects.count(), 2)
        self.assertEqual(Transaction.objects.get(description="Sem cat").category.name, "Sem Categoria")
        paid = Installment.objects.get(status="paid")
        self.assertEqual(paid.payment_date, date(2025, 10, 3))
        self.assertEqual(Installment.objects.count(), 3)
        self.assertTrue(ContractTemplate.objects.filter(title="Modelo antigo").exists())
        self.assertEqual(MarketAnalysis.objects.get().symbol, "PETR4.SA")
        contract = Contract.objects.get()
        self.assertEqual((contract.extension, contract.value), ("pdf", Decimal("900.00")))
        receipt = Receipt.objects.get()
        self.assertEqual(receipt.total, Decimal("250.50"))
        self.assertEqual(receipt.pdf.read(), b"%PDF-1.4 old")

    def test_dry_run(self):
        self.run_import("--dry-run")
        self.assertFalse(Transaction.objects.exists())
        self.assertFalse(Contract.objects.exists())
