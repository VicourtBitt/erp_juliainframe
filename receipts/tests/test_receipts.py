import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from receipts.models import Receipt

MEDIA = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA)
class ReceiptTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user("ju", password="pw"))

    def payload(self, **items):
        data = {
            "payer_name": "Maria Silva", "payer_document": "123.456.789-00",
            "payee_name": "Ju Fotografia", "payee_document": "12.345.678/0001-90",
            "issue_date": "2026-11-25", "location": "Porto Alegre - RS",
            "items-TOTAL_FORMS": "2", "items-INITIAL_FORMS": "0", "items-MIN_NUM_FORMS": "1", "items-MAX_NUM_FORMS": "1000",
            "items-0-description": "Ensaio fotográfico " * 20, "items-0-price": "350.00",
            "items-1-description": "Álbum impresso", "items-1-price": "149.90",
        }
        data.update(items)
        return data

    def test_create_generates_pdf_and_total(self):
        response = self.client.post(reverse("receipts:create"), self.payload())
        receipt = Receipt.objects.get()
        self.assertRedirects(response, reverse("receipts:detail", args=[receipt.pk]))
        self.assertEqual(str(receipt.total), "499.90")
        self.assertEqual(receipt.items.count(), 2)
        pdf = self.client.get(reverse("receipts:pdf", args=[receipt.pk]))
        content = b"".join(pdf.streaming_content)
        self.assertTrue(content.startswith(b"%PDF"))
        self.assertEqual(pdf["Content-Type"], "application/pdf")

    def test_requires_at_least_one_item(self):
        data = self.payload(**{"items-TOTAL_FORMS": "1", "items-0-description": "", "items-0-price": ""})
        response = self.client.post(reverse("receipts:create"), data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Receipt.objects.exists())

    def test_many_items_paginate(self):
        data = self.payload(**{"items-TOTAL_FORMS": "40"})
        for i in range(2, 40):
            data[f"items-{i}-description"] = f"Serviço {i}"
            data[f"items-{i}-price"] = "10.00"
        self.client.post(reverse("receipts:create"), data)
        receipt = Receipt.objects.get()
        self.assertEqual(receipt.items.count(), 40)
        self.assertGreater(receipt.pdf.size, 1000)

    def test_edit_regenerates_and_delete(self):
        self.client.post(reverse("receipts:create"), self.payload())
        receipt = Receipt.objects.get()
        item_ids = list(receipt.items.values_list("pk", flat=True))
        data = self.payload(**{
            "items-INITIAL_FORMS": "2",
            "items-0-id": str(item_ids[0]), "items-1-id": str(item_ids[1]), "items-1-DELETE": "on",
        })
        self.client.post(reverse("receipts:edit", args=[receipt.pk]), data)
        receipt.refresh_from_db()
        self.assertEqual(str(receipt.total), "350.00")
        self.client.post(reverse("receipts:delete", args=[receipt.pk]))
        self.assertFalse(Receipt.objects.exists())

    def test_list_filters(self):
        self.client.post(reverse("receipts:create"), self.payload())
        response = self.client.get(reverse("receipts:list"), {"q": "Álbum"})
        self.assertContains(response, "Maria Silva")
        response = self.client.get(reverse("receipts:list"), {"payer": "Outra"})
        self.assertNotContains(response, "Maria Silva</td>")
