from django.contrib import admin

from .models import Contract, ContractTemplate, GeneratedContract


@admin.register(ContractTemplate)
class ContractTemplateAdmin(admin.ModelAdmin):
    list_display = ["title", "category", "updated_at"]
    search_fields = ["title", "category", "content"]


@admin.register(GeneratedContract)
class GeneratedContractAdmin(admin.ModelAdmin):
    list_display = ["title", "created_at", "finalized_at"]
    search_fields = ["title", "prompt_context"]


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = ["name", "contract_type", "contractor", "value", "contract_date"]
    list_filter = ["contract_type"]
    search_fields = ["name", "contractor"]
