import logging
import re
from dataclasses import dataclass

from django.core.cache import cache

logger = logging.getLogger(__name__)

# B3 tickers: 4 letters + 1-2 digits, optional fractional "F" (PETR4, TAEE11, NVDC34, PETR4F).
B3_TICKER_RE = re.compile(r"^[A-Z]{4}\d{1,2}F?$")
CURRENCY_SYMBOLS = {"BRL": "R$", "USD": "US$", "EUR": "€", "GBP": "£"}

PROMPT_TEMPLATE = """
Atue como um analista de mercado financeiro sênior especializado em B3 e Mercados Globais.
Realize uma análise técnica e fundamentalista do ativo: {ticker} ({company}).
O preço atual é {price} e a variação no último pregão é de {change}%.
Fechamentos dos últimos pregões (mais antigo -> mais recente): {closes}.

A análise DEVE conter obrigatoriamente os seguintes tópicos, em Markdown:
1. **Visão Geral**: Breve resumo do momento atual do ativo.
2. **Análise Geopolítica**: Como o cenário político (local e global) está impactando este ativo especificamente?
3. **Volatilidade e Risco**: Quão volátil está o ativo? Quais são os riscos de curto prazo?
4. **Conclusão**: Viés (Alta, Baixa ou Neutro).

Seja direto e objetivo. Termine com um aviso de que não se trata de recomendação de investimento.
"""


class MarketDataError(Exception):
    pass


@dataclass
class Quote:
    ticker: str
    symbol: str
    company_name: str
    currency: str
    price: float
    change_percent: float
    history: list[dict]  # [{"date": "2026-01-02", "close": .., "high": .., "low": .., "volume": ..}]

    @property
    def last(self):
        return self.history[-1] if self.history else {}


def normalize_ticker(raw: str) -> tuple[str, str]:
    """Return (display ticker, Yahoo Finance symbol).

    The Streamlit version appended '.SA' to anything up to 6 characters, which
    broke US tickers such as AAPL or MSFT.
    """
    ticker = raw.strip().upper()
    if ticker.endswith(".SA"):
        return ticker[:-3], ticker
    if B3_TICKER_RE.match(ticker):
        return ticker, f"{ticker}.SA"
    return ticker, ticker


def currency_symbol(code: str) -> str:
    return CURRENCY_SYMBOLS.get((code or "").upper(), code or "")


def fetch_quote(raw_ticker: str, period: str = "1mo") -> Quote:
    ticker, symbol = normalize_ticker(raw_ticker)
    cache_key = f"quote:{symbol}:{period}"
    if cached := cache.get(cache_key):
        return cached
    try:
        import yfinance as yf

        stock = yf.Ticker(symbol)
        hist = stock.history(period=period)
    except Exception as exc:
        logger.warning("yfinance failed for %s: %s", symbol, exc)
        raise MarketDataError(f"Erro ao buscar dados no Yahoo Finance: {exc}") from exc
    if hist is None or hist.empty:
        raise MarketDataError(f"Não foi possível encontrar dados para o ticker {ticker}. Verifique o código.")

    closes = hist["Close"].tolist()
    price = float(closes[-1])
    change = ((price - closes[-2]) / closes[-2] * 100) if len(closes) >= 2 and closes[-2] else 0.0
    try:
        info = stock.info or {}
    except Exception:  # .info is flaky and not essential
        info = {}
    quote = Quote(
        ticker=ticker,
        symbol=symbol,
        company_name=info.get("longName") or info.get("shortName") or ticker,
        currency=info.get("currency") or ("BRL" if symbol.endswith(".SA") else "USD"),
        price=price,
        change_percent=float(change),
        history=[
            {
                "date": idx.strftime("%Y-%m-%d"),
                "close": round(float(row["Close"]), 4),
                "high": round(float(row["High"]), 4),
                "low": round(float(row["Low"]), 4),
                "volume": int(row["Volume"]),
            }
            for idx, row in hist.iterrows()
        ],
    )
    cache.set(cache_key, quote, 600)
    return quote


def build_prompt(quote: Quote) -> str:
    return PROMPT_TEMPLATE.format(
        ticker=quote.ticker,
        company=quote.company_name,
        price=f"{currency_symbol(quote.currency)} {quote.price:.2f}",
        change=f"{quote.change_percent:.2f}",
        closes=", ".join(f"{h['close']:.2f}" for h in quote.history[-20:]),
    )
