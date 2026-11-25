from django import forms

from .models import Category, Transaction


class TransactionForm(forms.ModelForm):
    class Meta:
        model = Transaction
        fields = ["description", "category", "total_amount", "transaction_date", "installments_count"]
        widgets = {"transaction_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}
        help_texts = {"category": "A categoria define se o lançamento é entrada ou saída."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = Category.objects.order_by("type", "name")
        self.fields["installments_count"].widget.attrs.update(min=1, max=120)

    def clean_installments_count(self):
        value = self.cleaned_data["installments_count"]
        if not 1 <= value <= 120:
            raise forms.ValidationError("Informe entre 1 e 120 parcelas.")
        return value


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "type"]


class PeriodForm(forms.Form):
    start = forms.DateField(label="De", widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    end = forms.DateField(label="Até", widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))

    def clean(self):
        data = super().clean()
        if data.get("start") and data.get("end") and data["start"] > data["end"]:
            raise forms.ValidationError("A data inicial deve ser anterior à final.")
        return data
