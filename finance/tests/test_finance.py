from datetime import date
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from finance import services
from finance.models import Category, EntryType, Installment, Transaction


def make_tx(category, total="100.00", when=date(2026, 1, 31), count=1, desc="Item"):
    return Transaction.create_with_installments(
        description=desc, category=category, total_amount=Decimal(total), transaction_date=when,
        installments_count=count,
    )


class InstallmentScheduleTests(TestCase):
    def setUp(self):
        self.sale = Category.objects.create(name="Ensaio", type=EntryType.SALE)

    def test_split_rounds_and_last_absorbs_difference(self):
        tx = make_tx(self.sale, "100.00", count=3)
        amounts = list(tx.installments.order_by("number").values_list("amount", flat=True))
        self.assertEqual(amounts, [Decimal("33.33"), Decimal("33.33"), Decimal("33.34")])
        self.assertEqual(sum(amounts), Decimal("100.00"))

    def test_due_dates_are_monthly_and_clamp_month_end(self):
        tx = make_tx(self.sale, count=3, when=date(2026, 1, 31))
        dates = list(tx.installments.order_by("number").values_list("due_date", flat=True))
        self.assertEqual(dates, [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31)])

    def test_type_comes_from_category(self):
        expense = Category.objects.create(name="Aluguel", type=EntryType.EXPENSE)
        self.assertEqual(make_tx(expense).type, EntryType.EXPENSE)

    @mock.patch("django.utils.timezone.localdate", return_value=date(2026, 3, 1))
    def test_overdue_is_derived(self, _):
        tx = make_tx(self.sale, count=3, when=date(2026, 1, 15))
        statuses = [i.display_status for i in tx.installments.order_by("number")]
        self.assertEqual(statuses, ["overdue", "overdue", "pending"])
        first = tx.installments.get(number=1)
        first.mark_paid()
        self.assertEqual(first.display_status, "paid")
        self.assertEqual(first.payment_date, date(2026, 3, 1))
        first.mark_pending()
        self.assertIsNone(first.payment_date)


class DashboardServiceTests(TestCase):
    def setUp(self):
        self.sale = Category.objects.create(name="Evento", type=EntryType.SALE)
        self.rent = Category.objects.create(name="Aluguel", type=EntryType.EXPENSE)
        self.tools = Category.objects.create(name="Equipamento", type=EntryType.EXPENSE)
        make_tx(self.sale, "300.00", date(2026, 1, 10), count=3)
        make_tx(self.rent, "50.00", date(2026, 1, 5))
        make_tx(self.tools, "120.00", date(2026, 2, 5), count=2)

    def test_default_period(self):
        self.assertEqual(services.default_period(date(2026, 5, 15)), (date(2026, 3, 1), date(2026, 8, 31)))

    @mock.patch("django.utils.timezone.localdate", return_value=date(2026, 2, 20))
    def test_aggregates(self, _):
        data = services.dashboard_data(date(2026, 1, 1), date(2026, 3, 31))
        chart = data["chart"]
        self.assertEqual(chart["labels"], ["2026-01", "2026-02", "2026-03"])
        self.assertEqual(chart["income"], [100.0, 100.0, 100.0])
        self.assertEqual(chart["expense"], [50.0, 60.0, 60.0])
        self.assertEqual(chart["balance"], [50.0, 90.0, 130.0])
        self.assertEqual(data["kpis"]["income"], Decimal("300.00"))
        self.assertEqual(data["kpis"]["profit"], Decimal("130.00"))
        self.assertEqual(data["kpis"]["avg_ticket"], Decimal("300.00"))
        # Jan and Feb sale installments are overdue on 2026-02-20 (Feb 10 < Feb 20).
        self.assertEqual(data["kpis"]["overdue"], Decimal("200.00"))
        names = [c["name"] for c in chart["categories"]]
        self.assertEqual(names, ["Aluguel", "Equipamento"])

    def test_pending_groups(self):
        sales, groups = services.pending_installments(date(2026, 1, 1), date(2026, 3, 31))
        self.assertEqual(len(sales), 3)
        self.assertEqual([g["month"] for g in groups], [date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1)])
        self.assertEqual(groups[1]["total"], Decimal("60.00"))


class FinanceViewTests(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user("ju", password="pw"))
        self.sale = Category.objects.create(name="Ensaio", type=EntryType.SALE)
        self.rent = Category.objects.create(name="Aluguel", type=EntryType.EXPENSE)

    def test_create_transaction_from_dashboard(self):
        response = self.client.post(reverse("finance:dashboard"), {
            "description": "Casamento", "category": self.sale.pk, "total_amount": "1500.00",
            "transaction_date": "2026-11-01", "installments_count": "3",
        })
        self.assertEqual(response.status_code, 302)
        tx = Transaction.objects.get()
        self.assertEqual(tx.installments.count(), 3)
        self.assertEqual(tx.type, EntryType.SALE)

    def test_dashboard_with_data_renders(self):
        make_tx(self.sale, when=date.today())
        make_tx(self.rent, when=date.today())
        response = self.client.get(reverse("finance:dashboard"))
        self.assertContains(response, "chart-data")

    def test_mark_paid_and_revert(self):
        inst = make_tx(self.sale).installments.get()
        self.client.post(reverse("finance:installment_status", args=[inst.pk]), {"status": "paid"})
        inst.refresh_from_db()
        self.assertEqual(inst.status, Installment.Status.PAID)
        self.client.post(reverse("finance:installment_status", args=[inst.pk]), {"status": "pending"})
        inst.refresh_from_db()
        self.assertEqual(inst.status, Installment.Status.PENDING)

    def test_status_requires_post(self):
        inst = make_tx(self.sale).installments.get()
        self.assertEqual(self.client.get(reverse("finance:installment_status", args=[inst.pk])).status_code, 405)

    def test_pay_month_only_selected_ids(self):
        a = make_tx(self.rent, when=date(2026, 4, 2), desc="A").installments.get()
        b = make_tx(self.rent, when=date(2026, 4, 20), desc="B").installments.get()
        self.client.post(reverse("finance:installments_pay_month"), {"month": "2026-04-01", "type": "expense", "ids": [a.pk]})
        a.refresh_from_db(); b.refresh_from_db()
        self.assertEqual((a.status, b.status), ("paid", "pending"))

    def test_edit_schedule_blocked_when_paid(self):
        tx = make_tx(self.sale, count=2)
        tx.installments.first().mark_paid()
        response = self.client.post(reverse("finance:transaction_edit", args=[tx.pk]), {
            "description": "Novo", "category": self.sale.pk, "total_amount": "999.00",
            "transaction_date": "2026-01-31", "installments_count": "2",
        })
        self.assertEqual(response.status_code, 200)
        tx.refresh_from_db()
        self.assertEqual(tx.total_amount, Decimal("100.00"))

    def test_edit_rebuilds_schedule(self):
        tx = make_tx(self.sale, count=2)
        self.client.post(reverse("finance:transaction_edit", args=[tx.pk]), {
            "description": "Novo", "category": self.sale.pk, "total_amount": "90.00",
            "transaction_date": "2026-01-31", "installments_count": "3",
        })
        self.assertEqual(list(tx.installments.values_list("amount", flat=True)), [Decimal("30.00")] * 3)

    def test_delete_category_in_use_is_refused(self):
        make_tx(self.sale)
        self.client.post(reverse("finance:category_delete", args=[self.sale.pk]))
        self.assertTrue(Category.objects.filter(pk=self.sale.pk).exists())

    def test_delete_transaction_requires_confirmation(self):
        tx = make_tx(self.sale)
        self.assertEqual(self.client.get(reverse("finance:transaction_delete", args=[tx.pk])).status_code, 200)
        self.assertTrue(Transaction.objects.exists())
        self.client.post(reverse("finance:transaction_delete", args=[tx.pk]))
        self.assertFalse(Transaction.objects.exists())
        self.assertFalse(Installment.objects.exists())
