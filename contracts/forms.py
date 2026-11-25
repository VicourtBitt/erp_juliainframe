from django import forms
from django.conf import settings

from .models import Contract, ContractTemplate, GeneratedContract
from .prompts import CREATOR_PLACEHOLDER
from .rendering import humanize


class ContractTemplateForm(forms.ModelForm):
    class Meta:
        model = ContractTemplate
        fields = ["title", "category", "content"]
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "Ex: Contrato PJ para PJ - Padrão"}),
            "category": forms.TextInput(attrs={"placeholder": "Ex: Consultoria, Ensaio, Evento"}),
            "content": forms.Textarea(attrs={"rows": 14, "placeholder": "Texto base / instruções do contrato..."}),
        }


class CreatorForm(forms.Form):
    context = forms.CharField(
        label="Contexto do contrato",
        min_length=50,
        widget=forms.Textarea(attrs={"rows": 14, "placeholder": CREATOR_PLACEHOLDER}),
        error_messages={"min_length": "Insira um contexto mais detalhado (mínimo de %(limit_value)d caracteres)."},
    )
    template = forms.ModelChoiceField(queryset=ContractTemplate.objects.all(), required=False, widget=forms.HiddenInput)


class FieldValuesForm(forms.Form):
    """Dynamic form with one input per Jinja variable of a generated contract."""

    def __init__(self, *args, contract: GeneratedContract, **kwargs):
        super().__init__(*args, **kwargs)
        for name in contract.fields:
            self.fields[name] = forms.CharField(
                label=humanize(name),
                required=False,
                initial=contract.values.get(name, ""),
                widget=forms.TextInput(attrs={"placeholder": "{{ " + name + " }}"}),
            )


class TemplateHtmlForm(forms.ModelForm):
    class Meta:
        model = GeneratedContract
        fields = ["title", "template_html"]
        widgets = {"template_html": forms.Textarea(attrs={"rows": 20, "class": "font-monospace small"})}


class ContractUploadForm(forms.ModelForm):
    class Meta:
        model = Contract
        fields = ["name", "contract_type", "contract_date", "value", "contractor", "file"]
        widgets = {"contract_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["file"].widget.attrs["accept"] = ".pdf,.docx,.html,.htm,.txt,.png,.jpg,.jpeg"

    def clean_file(self):
        f = self.cleaned_data["file"]
        limit = settings.MAX_CONTRACT_UPLOAD_MB
        if f and getattr(f, "size", 0) > limit * 1024 * 1024:
            raise forms.ValidationError(f"O arquivo excede o limite de {limit} MB.")
        return f


class ArchiveGeneratedForm(forms.ModelForm):
    class Meta:
        model = Contract
        fields = ["name", "contract_type", "contract_date", "value", "contractor"]
        widgets = {"contract_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}
