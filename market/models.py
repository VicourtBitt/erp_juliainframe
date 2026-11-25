from django.db import models


class MarketAnalysis(models.Model):
    ticker = models.CharField("ticker", max_length=20)
    symbol = models.CharField("símbolo Yahoo", max_length=30)
    company_name = models.CharField("empresa", max_length=200, blank=True)
    currency = models.CharField("moeda", max_length=10, default="BRL")
    price = models.DecimalField("preço", max_digits=16, decimal_places=4)
    change_percent = models.DecimalField("variação %", max_digits=9, decimal_places=4)
    analysis_text = models.TextField("análise")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "análise de ativo"
        verbose_name_plural = "análises de ativos"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.ticker} @ {self.created_at:%d/%m/%Y %H:%M}"
