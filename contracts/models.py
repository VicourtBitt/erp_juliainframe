from pathlib import Path

from django.core.validators import FileExtensionValidator, MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone

PREVIEWABLE_EXTENSIONS = {"pdf", "html", "htm", "txt", "png", "jpg", "jpeg"}
ALLOWED_EXTENSIONS = ["pdf", "docx", "html", "htm", "txt", "png", "jpg", "jpeg"]


class ContractTemplate(models.Model):
    """Reusable base text/instructions loaded into the AI contract creator."""

    title = models.CharField("título", max_length=200)
    category = models.CharField("categoria", max_length=100, blank=True)
    content = models.TextField("conteúdo base")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "modelo de contrato"
        verbose_name_plural = "modelos de contrato"
        ordering = ["category", "title"]

    def __str__(self):
        return f"[{self.category}] {self.title}" if self.category else self.title


class GeneratedContract(models.Model):
    """A contract drafted by the AI. Persisted, unlike the Streamlit version."""

    title = models.CharField("título", max_length=255)
    prompt_context = models.TextField("contexto informado")
    source_template = models.ForeignKey(
        ContractTemplate, null=True, blank=True, on_delete=models.SET_NULL, related_name="generated_contracts"
    )
    template_html = models.TextField("HTML (Jinja2)")
    fields = models.JSONField("campos variáveis", default=list, blank=True)
    values = models.JSONField("valores preenchidos", default=dict, blank=True)
    final_html = models.TextField("HTML final", blank=True)
    finalized_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "contrato gerado"
        verbose_name_plural = "contratos gerados"
        ordering = ["-updated_at"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("contracts:generated_detail", args=[self.pk])

    @property
    def is_final(self):
        return bool(self.final_html)

    @property
    def missing_fields(self):
        return [f for f in self.fields if not str(self.values.get(f, "")).strip()]


class Contract(models.Model):
    """An executed / signed contract file kept in the archive."""

    class Kind(models.TextChoices):
        SESSION = "Contrato de Ensaio", "Contrato de Ensaio"
        EVENT = "Contrato de Evento", "Contrato de Evento"
        SERVICE = "Contrato de Prestação de Serviços", "Contrato de Prestação de Serviços"
        OTHER = "Outro", "Outro"

    name = models.CharField("nome do contrato", max_length=200)
    contract_type = models.CharField("tipo de contrato", max_length=60, choices=Kind.choices, default=Kind.SERVICE)
    contract_date = models.DateField("data do contrato", default=timezone.localdate)
    value = models.DecimalField(
        "valor do contrato", max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)]
    )
    contractor = models.CharField("contratante", max_length=200)
    file = models.FileField(
        "arquivo",
        upload_to="contracts/%Y/%m/",
        validators=[FileExtensionValidator(ALLOWED_EXTENSIONS)],
    )
    generated_from = models.ForeignKey(
        GeneratedContract, null=True, blank=True, on_delete=models.SET_NULL, related_name="archived_files"
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "contrato"
        ordering = ["-contract_date", "-id"]

    def __str__(self):
        return self.name

    @property
    def extension(self):
        return Path(self.file.name).suffix.lstrip(".").lower()

    @property
    def previewable(self):
        return self.extension in PREVIEWABLE_EXTENSIONS

    @property
    def download_name(self):
        return f"{self.name}.{self.extension}"
