from django.contrib import admin

from .models import MarketAnalysis


@admin.register(MarketAnalysis)
class MarketAnalysisAdmin(admin.ModelAdmin):
    list_display = ["ticker", "company_name", "price", "change_percent", "created_at"]
    search_fields = ["ticker", "company_name"]
