from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse

from core.pagination import paginate
from finance.models import Category, EntryType, Transaction


class PaginateHelperTests(TestCase):
    def test_size_and_param(self):
        rf = RequestFactory()
        page = paginate(rf.get("/", {"x": "2", "x_size": "10"}), list(range(35)), param="x")
        self.assertEqual((page.number, page.size, list(page)), (2, 10, list(range(10, 20))))

    def test_invalid_values_fall_back(self):
        rf = RequestFactory()
        page = paginate(rf.get("/", {"page": "abc", "page_size": "7"}), list(range(35)), per_page=25)
        self.assertEqual((page.number, page.size), (1, 25))
        page = paginate(rf.get("/", {"page": "99"}), list(range(35)))
        self.assertEqual(page.number, 2)  # out of range -> last page


class PaginatedViewsTests(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user("ju", password="pw"))
        sale = Category.objects.create(name="Venda", type=EntryType.SALE)
        for i in range(30):
            Category.objects.create(name=f"Cat {i:02d}", type=EntryType.EXPENSE)
        self.tx = Transaction.create_with_installments(
            description="Longo", category=sale, total_amount=Decimal("1200"),
            transaction_date=date(2026, 1, 1), installments_count=40,
        )

    def test_transaction_detail_installments(self):
        response = self.client.get(reverse("finance:transaction_detail", args=[self.tx.pk]))
        self.assertEqual(len(response.context["installments"]), 25)
        self.assertContains(response, "Mostrando 1–25 de 40")
        response = self.client.get(reverse("finance:transaction_detail", args=[self.tx.pk]), {"page": 2})
        self.assertEqual([i.number for i in response.context["installments"]][0], 26)

    def test_categories_page_size(self):
        response = self.client.get(reverse("finance:categories"), {"page_size": 10})
        self.assertEqual(len(response.context["categories"]), 10)
        self.assertContains(response, 'name="page_size"')

    def test_pagination_keeps_filters(self):
        response = self.client.get(reverse("finance:audit"), {"tab": "installments", "status": "pending", "page_size": 10})
        self.assertContains(response, "status=pending")
        self.assertContains(response, "page=2")
        self.assertEqual(len(response.context["installments"]), 10)

    def test_dashboard_pending_sales_independent_param(self):
        response = self.client.get(reverse("finance:dashboard"), {"start": "2026-01-01", "end": "2029-12-31", "sales_page": 2})
        page = response.context["pending_sales"]
        self.assertEqual((page.number, page.paginator.count), (2, 40))
        self.assertContains(response, "sales_page=3")
