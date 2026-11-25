from django.contrib import admin

from .models import Category, Installment, Transaction


class InstallmentInline(admin.TabularInline):
    model = Installment
    extra = 0


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "type"]
    list_filter = ["type"]


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ["description", "category", "type", "total_amount", "transaction_date", "installments_count"]
    list_filter = ["type", "category"]
    search_fields = ["description"]
    inlines = [InstallmentInline]


@admin.register(Installment)
class InstallmentAdmin(admin.ModelAdmin):
    list_display = ["transaction", "number", "amount", "due_date", "status", "payment_date"]
    list_filter = ["status", "transaction__type"]
