from decimal import Decimal

from django import forms
from django.conf import settings
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.ai import AIError, generate_text
from core.pagination import paginate

from .models import MarketAnalysis
from .services import MarketDataError, build_prompt, fetch_quote


class TickerForm(forms.Form):
    ticker = forms.CharField(
        label="Ticker do ativo",
        max_length=20,
        widget=forms.TextInput(attrs={"placeholder": "Ex: PETR4, VALE3, ITUB4, AAPL, MSFT", "autofocus": True}),
    )


def analyzer(request):
    form = TickerForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            quote = fetch_quote(form.cleaned_data["ticker"])
            analysis = generate_text(build_prompt(quote))
        except (MarketDataError, AIError) as exc:
            messages.error(request, str(exc))
        else:
            obj = MarketAnalysis.objects.create(
                ticker=quote.ticker,
                symbol=quote.symbol,
                company_name=quote.company_name,
                currency=quote.currency,
                price=Decimal(str(round(quote.price, 4))),
                change_percent=Decimal(str(round(quote.change_percent, 4))),
                analysis_text=analysis,
            )
            messages.success(request, "Análise completa realizada!")
            return redirect("market:detail", pk=obj.pk)
    return render(
        request,
        "market/analyzer.html",
        {
            "form": form,
            "history": paginate(request, MarketAnalysis.objects.all()),
            "ai_configured": bool(settings.GEMINI_API_KEY),
        },
    )


def detail(request, pk):
    obj = get_object_or_404(MarketAnalysis, pk=pk)
    quote, quote_error, chart = None, None, None
    try:
        quote = fetch_quote(obj.symbol)  # fresh chart data; the analysis text is the saved one
        chart = {"labels": [h["date"] for h in quote.history], "close": [h["close"] for h in quote.history]}
    except MarketDataError as exc:
        quote_error = str(exc)
    return render(
        request,
        "market/detail.html",
        {
            "analysis": obj,
            "quote": quote,
            "quote_error": quote_error,
            "chart": chart,
            "history": MarketAnalysis.objects.exclude(pk=pk)[:10],
        },
    )


@require_POST
def delete(request, pk):
    get_object_or_404(MarketAnalysis, pk=pk).delete()
    messages.success(request, "Análise removida do histórico.")
    return redirect("market:analyzer")
