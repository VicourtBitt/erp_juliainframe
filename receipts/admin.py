from django.contrib import admin

from .models import Receipt, ReceiptItem


class ReceiptItemInline(admin.TabularInline):
    model = ReceiptItem
    extra = 0


@admin.register(Receipt)
class ReceiptAdmin(admin.ModelAdmin):
    list_display = ["id", "payer_name", "payee_name", "total", "issue_date"]
    search_fields = ["payer_name", "payee_name"]
    inlines = [ReceiptItemInline]
