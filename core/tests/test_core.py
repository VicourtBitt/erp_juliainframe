from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.templatetags.brl import format_brl


class BRLFormatTests(TestCase):
    def test_format(self):
        self.assertEqual(format_brl(Decimal("1234.5")), "R$ 1.234,50")
        self.assertEqual(format_brl(-10), "-R$ 10,00")
        self.assertEqual(format_brl(None), "R$ 0,00")
        self.assertEqual(format_brl(1000000, symbol=False), "1.000.000,00")


class AuthTests(TestCase):
    def test_pages_require_login(self):
        for url in ["/", reverse("finance:dashboard"), reverse("receipts:list"), reverse("contracts:archive"),
                    reverse("market:analyzer")]:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302, url)
            self.assertTrue(response.url.startswith(reverse("login")), url)

    def test_login_page_public(self):
        self.assertEqual(self.client.get(reverse("login")).status_code, 200)


class SmokeTests(TestCase):
    """Every listed page renders for a logged-in user on an empty database."""

    def setUp(self):
        self.user = get_user_model().objects.create_user("ju", password="pw")
        self.client.force_login(self.user)

    def test_pages_render(self):
        names = [
            "core:home", "finance:dashboard", "finance:audit", "finance:categories", "receipts:list",
            "receipts:create", "contracts:creator", "contracts:generated_list", "contracts:templates",
            "contracts:archive", "contracts:signatures", "market:analyzer",
        ]
        for name in names:
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)
        for tab in ["installments", "categories"]:
            self.assertEqual(self.client.get(reverse("finance:audit"), {"tab": tab}).status_code, 200)


class NavigationTests(TestCase):
    def test_only_most_specific_item_active(self):
        self.client.force_login(get_user_model().objects.create_user("nav", password="pw"))
        response = self.client.get(reverse("finance:audit"))
        active = [i["label"] for s in response.context["nav_sections"] for i in s["items"] if i["active"]]
        self.assertEqual(active, ["Auditoria"])
