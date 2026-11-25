from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from market.models import MarketAnalysis
from market.services import MarketDataError, Quote, normalize_ticker
from market.templatetags.markdown_safe import markdown_safe

QUOTE = Quote(
    ticker="PETR4", symbol="PETR4.SA", company_name="Petrobras", currency="BRL", price=38.5, change_percent=-1.25,
    history=[{"date": "2026-11-24", "close": 39.0, "high": 39.5, "low": 38.0, "volume": 1000},
             {"date": "2026-11-25", "close": 38.5, "high": 39.1, "low": 38.2, "volume": 2000}],
)


class TickerTests(TestCase):
    def test_normalize(self):
        self.assertEqual(normalize_ticker("petr4"), ("PETR4", "PETR4.SA"))
        self.assertEqual(normalize_ticker("TAEE11"), ("TAEE11", "TAEE11.SA"))
        self.assertEqual(normalize_ticker("VALE3.SA"), ("VALE3", "VALE3.SA"))
        self.assertEqual(normalize_ticker("AAPL"), ("AAPL", "AAPL"))  # was AAPL.SA in the Streamlit app
        self.assertEqual(normalize_ticker("MSFT"), ("MSFT", "MSFT"))

    def test_markdown_is_sanitised(self):
        html = markdown_safe("**Alta** <script>alert(1)</script> [x](javascript:alert(1))")
        self.assertIn("<strong>Alta</strong>", html)
        self.assertNotIn("<script", html)
        self.assertNotIn("javascript:", html.split("x")[0] if "href" in html else html)
        self.assertNotIn("href", html)


@override_settings(GEMINI_API_KEY="test")
class AnalyzerViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client.force_login(get_user_model().objects.create_user("ju", password="pw"))

    @mock.patch("market.views.generate_text", return_value="## Visão Geral\nNeutro.")
    @mock.patch("market.views.fetch_quote", return_value=QUOTE)
    def test_analyze_and_detail(self, fq, gen):
        response = self.client.post(reverse("market:analyzer"), {"ticker": "petr4"})
        analysis = MarketAnalysis.objects.get()
        self.assertRedirects(response, reverse("market:detail", args=[analysis.pk]), fetch_redirect_response=False)
        self.assertEqual(analysis.symbol, "PETR4.SA")
        with mock.patch("market.views.fetch_quote", return_value=QUOTE):
            detail = self.client.get(reverse("market:detail", args=[analysis.pk]))
        self.assertContains(detail, "<h2>Visão Geral</h2>", html=True)
        self.assertContains(detail, "chart-data")

    @mock.patch("market.views.fetch_quote", side_effect=MarketDataError("Ticker não encontrado"))
    def test_market_error(self, _):
        response = self.client.post(reverse("market:analyzer"), {"ticker": "XXXX"})
        self.assertContains(response, "Ticker não encontrado")
        self.assertFalse(MarketAnalysis.objects.exists())

    def test_detail_survives_quote_failure(self):
        a = MarketAnalysis.objects.create(ticker="X", symbol="X", price=1, change_percent=0, analysis_text="ok")
        with mock.patch("market.views.fetch_quote", side_effect=MarketDataError("offline")):
            response = self.client.get(reverse("market:detail", args=[a.pk]))
        self.assertContains(response, "offline")
