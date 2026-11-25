import shutil
import tempfile
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from contracts.models import Contract, ContractTemplate, GeneratedContract
from contracts.prompts import build_contract_prompt
from contracts.rendering import ContractRenderError, extract_canvases, render_contract

AI_RESPONSE = """Sure!
```html
<!DOCTYPE html><html><head><meta charset="UTF-8"><title>X</title><style>body{color:#333}</style></head>
<body><h1>CONTRATO DE PRESTA\\u00c7\\u00c3O</h1>
<p>Contratante: {{ client_name }}, CPF {{ client_cpf }}.</p>
<p>Valor: {{ total_value }}</p><script>alert(1)</script></body></html>
```

```plaintext
Contrato de Presta&ccedil;&atilde;o de Servi&ccedil;os
```

```json
{"context_fields": ["client_name", "client_cpf", "unused_field"]}
```
"""

MEDIA = tempfile.mkdtemp()


class RenderingTests(TestCase):
    def test_extract(self):
        parsed = extract_canvases(AI_RESPONSE)
        self.assertIn("PRESTAÇÃO", parsed.html)
        self.assertNotIn("<script", parsed.html)
        self.assertEqual(parsed.title, "Contrato de Prestação de Serviços")
        # Template variables win over the declared list (total_value was missing, unused_field is bogus).
        self.assertEqual(parsed.fields, ["client_name", "client_cpf", "total_value"])

    def test_extract_without_blocks(self):
        parsed = extract_canvases("no code blocks here")
        self.assertIsNone(parsed.html)
        self.assertEqual(parsed.fields, [])

    def test_render_escapes_values(self):
        out = render_contract("<p>{{ name }}</p>", {"name": "<b>Ana</b>"})
        self.assertEqual(out, "<p>&lt;b&gt;Ana&lt;/b&gt;</p>")

    def test_render_highlights_missing(self):
        out = render_contract("<p>{{ client_name }}</p>", {}, highlight_missing=True)
        self.assertIn("[Client name]", out)
        self.assertIn("<mark", out)

    def test_sandbox_blocks_unsafe_attribute_access(self):
        with self.assertRaises(ContractRenderError):
            render_contract("{{ ''.__class__.__mro__ }}", {})

    def test_syntax_error(self):
        with self.assertRaises(ContractRenderError):
            render_contract("{{ broken", {})

    def test_prompt_contains_css_once(self):
        prompt = build_contract_prompt("Contrato de teste")
        self.assertEqual(prompt.count("--accent:#0056b3"), 1)
        self.assertIn("Contrato de teste", prompt)


@override_settings(MEDIA_ROOT=MEDIA, GEMINI_API_KEY="test")
class CreatorFlowTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user("ju", password="pw"))

    def test_seeded_templates(self):
        self.assertEqual(ContractTemplate.objects.filter(category="Fotografia").count(), 2)

    def test_template_prefill(self):
        tpl = ContractTemplate.objects.first()
        response = self.client.get(reverse("contracts:creator"), {"template": tpl.pk})
        self.assertContains(response, tpl.content[:40])

    def test_context_too_short(self):
        response = self.client.post(reverse("contracts:creator"), {"context": "curto"})
        self.assertContains(response, "mínimo de 50")

    @mock.patch("contracts.views.generate_text", return_value=AI_RESPONSE)
    def test_full_flow(self, gen):
        response = self.client.post(reverse("contracts:creator"), {"context": "Contrato de serviços fotográficos " * 3})
        contract = GeneratedContract.objects.get()
        self.assertRedirects(response, contract.get_absolute_url())
        gen.assert_called_once()

        preview = self.client.get(reverse("contracts:generated_preview", args=[contract.pk]))
        self.assertIn("sandbox", preview["Content-Security-Policy"])
        self.assertContains(preview, "[Client name]")

        # Draft save
        self.client.post(contract.get_absolute_url(), {"action": "save", "client_name": "Ana"})
        contract.refresh_from_db()
        self.assertEqual(contract.values["client_name"], "Ana")
        self.assertFalse(contract.is_final)
        self.assertEqual(
            self.client.get(reverse("contracts:generated_download", args=[contract.pk, "pdf"])).status_code, 302
        )

        # Finalize
        self.client.post(contract.get_absolute_url(), {
            "action": "finalize", "client_name": "Ana & Cia", "client_cpf": "000", "total_value": "R$ 1.000,00",
        })
        contract.refresh_from_db()
        self.assertTrue(contract.is_final)
        self.assertIn("Ana &amp; Cia", contract.final_html)

        for fmt, magic in [("pdf", b"%PDF"), ("docx", b"PK"), ("html", b"<!DOCTYPE")]:
            response = self.client.get(reverse("contracts:generated_download", args=[contract.pk, fmt]))
            self.assertEqual(response.status_code, 200, fmt)
            self.assertTrue(response.content.startswith(magic), fmt)
        docx = self.client.get(reverse("contracts:generated_download", args=[contract.pk, "docx"])).content
        self.assertGreater(len(docx), 1000)

        # Archive
        response = self.client.post(reverse("contracts:generated_archive", args=[contract.pk]), {
            "name": "Contrato Ana", "contract_type": Contract.Kind.SERVICE, "contract_date": "2026-11-25",
            "value": "1000", "contractor": "Ana",
        })
        self.assertRedirects(response, reverse("contracts:archive"))
        archived = Contract.objects.get()
        self.assertEqual(archived.extension, "pdf")
        self.assertEqual(archived.generated_from, contract)

    @mock.patch("contracts.views.generate_text", return_value=AI_RESPONSE)
    def test_edit_html_updates_fields(self, _):
        self.client.post(reverse("contracts:creator"), {"context": "x" * 60})
        contract = GeneratedContract.objects.get()
        self.client.post(reverse("contracts:generated_edit_html", args=[contract.pk]), {
            "title": "Novo", "template_html": "<p>{{ a }} {{ b }}</p><script>x</script>",
        })
        contract.refresh_from_db()
        self.assertEqual(contract.fields, ["a", "b"])
        self.assertNotIn("script", contract.template_html)
        response = self.client.post(reverse("contracts:generated_edit_html", args=[contract.pk]), {
            "title": "Novo", "template_html": "{% if %}",
        })
        self.assertContains(response, "sintaxe")

    def test_ai_not_configured(self):
        with override_settings(GEMINI_API_KEY=""):
            response = self.client.post(reverse("contracts:creator"), {"context": "x" * 60}, follow=True)
        self.assertContains(response, "GEMINI_API_KEY")
        self.assertFalse(GeneratedContract.objects.exists())


@override_settings(MEDIA_ROOT=MEDIA)
class ArchiveTests(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user("ju", password="pw"))

    def upload(self, name="c.html", content=b"<html><body>Oi<script>x</script></body></html>", **extra):
        data = {
            "name": "Contrato Evento", "contract_type": Contract.Kind.EVENT, "contract_date": "2026-11-01",
            "value": "800.00", "contractor": "Pedro", "file": SimpleUploadedFile(name, content),
        }
        data.update(extra)
        return self.client.post(reverse("contracts:archive"), data)

    def test_upload_preview_sandboxed(self):
        self.assertEqual(self.upload().status_code, 302)
        contract = Contract.objects.get()
        response = self.client.get(reverse("contracts:archive_file", args=[contract.pk]))
        self.assertIn("sandbox", response["Content-Security-Policy"])
        self.assertNotIn("attachment", response.get("Content-Disposition", ""))
        download = self.client.get(reverse("contracts:archive_file", args=[contract.pk]), {"download": "1"})
        self.assertIn("attachment", download["Content-Disposition"])
        self.assertEqual(self.client.get(reverse("contracts:archive_preview", args=[contract.pk])).status_code, 200)

    def test_rejects_bad_extension(self):
        response = self.upload(name="virus.exe")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Contract.objects.exists())

    def test_docx_is_download_only(self):
        self.upload(name="c.docx", content=b"PK fake")
        contract = Contract.objects.get()
        self.assertFalse(contract.previewable)
        response = self.client.get(reverse("contracts:archive_file", args=[contract.pk]))
        self.assertIn("attachment", response["Content-Disposition"])

    def test_filters_and_delete(self):
        self.upload()
        self.assertContains(self.client.get(reverse("contracts:archive"), {"contractor": "Pedro"}), "Contrato Evento")
        self.assertNotContains(self.client.get(reverse("contracts:archive"), {"q": "zzz"}), "Contrato Evento</td>")
        contract = Contract.objects.get()
        self.client.post(reverse("contracts:archive_delete", args=[contract.pk]))
        self.assertFalse(Contract.objects.exists())

    def test_template_crud(self):
        self.client.post(reverse("contracts:templates"), {"title": "T", "category": "C", "content": "abc"})
        tpl = ContractTemplate.objects.get(title="T")
        self.client.post(reverse("contracts:template_edit", args=[tpl.pk]), {"title": "T2", "category": "C", "content": "x"})
        tpl.refresh_from_db()
        self.assertEqual(tpl.title, "T2")
        self.client.post(reverse("contracts:template_delete", args=[tpl.pk]))
        self.assertFalse(ContractTemplate.objects.filter(pk=tpl.pk).exists())
