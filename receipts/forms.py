from django import forms

from .models import Receipt, ReceiptItem


class ReceiptForm(forms.ModelForm):
    class Meta:
        model = Receipt
        fields = ["payer_name", "payer_document", "payee_name", "payee_document", "issue_date", "location"]
        widgets = {
            "issue_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "location": forms.TextInput(attrs={"placeholder": "Ex: Porto Alegre - RS"}),
        }


ReceiptItemFormSet = forms.inlineformset_factory(
    Receipt,
    ReceiptItem,
    fields=["description", "price"],
    widgets={"description": forms.Textarea(attrs={"rows": 2})},
    extra=0,
    min_num=1,
    validate_min=True,
    can_delete=True,
)
