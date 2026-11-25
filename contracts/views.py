import mimetypes

from django.conf import settings
from django.contrib import messages
from django.core.files.base import ContentFile
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_POST
from django.views.decorators.clickjacking import xframe_options_sameorigin

from core.ai import AIError, generate_text

from .exporters import html_to_docx, html_to_pdf
from .forms import (
    ArchiveGeneratedForm,
    ContractTemplateForm,
    ContractUploadForm,
    CreatorForm,
    FieldValuesForm,
    TemplateHtmlForm,
)
from .models import Contract, ContractTemplate, GeneratedContract
from .prompts import build_contract_prompt
from .rendering import ContractRenderError, extract_canvases, merge_fields, render_contract, strip_scripts

# Served documents may contain arbitrary HTML (AI output, uploads): render them
# in a sandbox with no scripts, no forms and no network access except images.
SANDBOX_CSP = "sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data: https:; font-src data: https:"


def _sandboxed_html(document: str) -> HttpResponse:
    response = HttpResponse(document, content_type="text/html; charset=utf-8")
    response["Content-Security-Policy"] = SANDBOX_CSP
    return response


# --- Templates (Gerenciador de modelos) ------------------------------------

def template_list(request):
    form = ContractTemplateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        obj = form.save()
        messages.success(request, f"Modelo '{obj.title}' criado.")
        return redirect("contracts:templates")
    q = request.GET.get("q", "").strip()
    templates = ContractTemplate.objects.annotate(uses=Count("generated_contracts"))
    if q:
        templates = templates.filter(Q(title__icontains=q) | Q(category__icontains=q) | Q(content__icontains=q))
    return render(
        request,
        "contracts/template_list.html",
        {"form": form, "templates": templates, "q": q, "open_form": request.method == "POST"},
    )


def template_edit(request, pk):
    obj = get_object_or_404(ContractTemplate, pk=pk)
    form = ContractTemplateForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Modelo '{obj.title}' atualizado.")
        return redirect("contracts:templates")
    return render(request, "contracts/template_form.html", {"form": form, "template_obj": obj})


def template_delete(request, pk):
    obj = get_object_or_404(ContractTemplate, pk=pk)
    if request.method == "POST":
        obj.delete()
        messages.success(request, "Modelo removido.")
        return redirect("contracts:templates")
    return render(
        request,
        "core/confirm_delete.html",
        {"object": obj, "kind": "modelo de contrato", "cancel_url": reverse("contracts:templates")},
    )


# --- AI creator ----------------------------------------------------------------

def creator(request):
    templates = ContractTemplate.objects.all()
    if request.method == "POST":
        form = CreatorForm(request.POST)
        if form.is_valid():
            context = form.cleaned_data["context"]
            try:
                parsed = extract_canvases(generate_text(build_contract_prompt(context)))
            except AIError as exc:
                messages.error(request, str(exc))
            else:
                if not parsed.html:
                    messages.error(request, "A IA não retornou um contrato em HTML válido. Tente novamente.")
                else:
                    obj = GeneratedContract.objects.create(
                        title=parsed.title or "Contrato gerado",
                        prompt_context=context,
                        source_template=form.cleaned_data.get("template"),
                        template_html=parsed.html,
                        fields=parsed.fields,
                    )
                    messages.success(request, "Contrato gerado! Preencha os campos variáveis para finalizar.")
                    return redirect(obj)
    else:
        initial = {}
        template_id = request.GET.get("template")
        if template_id and template_id.isdigit():
            if tpl := templates.filter(pk=template_id).first():
                initial = {"context": tpl.content, "template": tpl.pk}
                messages.info(request, f"Modelo '{tpl.title}' carregado. Personalize valores, datas e prazos.")
        form = CreatorForm(initial=initial)
    return render(
        request,
        "contracts/creator.html",
        {"form": form, "templates": templates, "ai_configured": bool(settings.GEMINI_API_KEY)},
    )


def generated_list(request):
    q = request.GET.get("q", "").strip()
    items = GeneratedContract.objects.select_related("source_template")
    if q:
        items = items.filter(Q(title__icontains=q) | Q(prompt_context__icontains=q))
    return render(
        request,
        "contracts/generated_list.html",
        {"contracts": Paginator(items, 25).get_page(request.GET.get("page")), "q": q},
    )


def generated_detail(request, pk):
    obj = get_object_or_404(GeneratedContract, pk=pk)
    form = FieldValuesForm(request.POST or None, contract=obj)
    if request.method == "POST" and form.is_valid():
        obj.values = {name: form.cleaned_data.get(name, "") for name in obj.fields}
        if request.POST.get("action") == "finalize":
            try:
                obj.final_html = render_contract(obj.template_html, obj.values)
            except ContractRenderError as exc:
                messages.error(request, str(exc))
                obj.save(update_fields=["values", "updated_at"])
                return redirect(obj)
            obj.finalized_at = timezone.now()
            if obj.missing_fields:
                messages.warning(request, f"Contrato finalizado com {len(obj.missing_fields)} campo(s) em branco.")
            else:
                messages.success(request, "Contrato finalizado! Os downloads estão disponíveis.")
        else:
            # Editing values after finalizing invalidates the final version.
            obj.final_html, obj.finalized_at = "", None
            messages.info(request, "Rascunho salvo.")
        obj.save()
        return redirect(obj)

    archive_form = ArchiveGeneratedForm(initial={"name": obj.title, "contract_date": timezone.localdate()})
    return render(
        request,
        "contracts/generated_detail.html",
        {"contract": obj, "form": form, "archive_form": archive_form},
    )


@xframe_options_sameorigin
def generated_preview(request, pk):
    obj = get_object_or_404(GeneratedContract, pk=pk)
    try:
        document = (
            obj.final_html
            if obj.is_final and request.GET.get("draft") != "1"
            else render_contract(obj.template_html, obj.values, highlight_missing=True)
        )
    except ContractRenderError as exc:
        document = f"<p style='color:#b00;font-family:sans-serif'>{exc}</p>"
    return _sandboxed_html(document)


def generated_edit_html(request, pk):
    obj = get_object_or_404(GeneratedContract, pk=pk)
    form = TemplateHtmlForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.template_html = strip_scripts(obj.template_html)
        try:
            render_contract(obj.template_html, obj.values)
        except ContractRenderError as exc:
            form.add_error("template_html", str(exc))
        else:
            obj.fields = merge_fields(obj.fields, obj.template_html)
            obj.final_html, obj.finalized_at = "", None
            obj.save()
            messages.success(request, "Modelo HTML atualizado. Revise os campos e finalize novamente.")
            return redirect(obj)
    return render(request, "contracts/generated_edit_html.html", {"form": form, "contract": obj})


def generated_download(request, pk, fmt):
    obj = get_object_or_404(GeneratedContract, pk=pk)
    if not obj.is_final:
        messages.error(request, "Finalize o contrato antes de baixar.")
        return redirect(obj)
    base = slugify(obj.title) or "contrato"
    if fmt == "pdf":
        data, mime = html_to_pdf(obj.final_html), "application/pdf"
    elif fmt == "docx":
        data, mime = html_to_docx(obj.final_html), (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
    elif fmt == "html":
        data, mime = obj.final_html.encode("utf-8"), "text/html"
    else:
        raise Http404
    response = HttpResponse(data, content_type=mime)
    response["Content-Disposition"] = f'attachment; filename="{base}.{fmt}"'
    return response


@require_POST
def generated_archive(request, pk):
    obj = get_object_or_404(GeneratedContract, pk=pk)
    if not obj.is_final:
        messages.error(request, "Finalize o contrato antes de arquivá-lo.")
        return redirect(obj)
    form = ArchiveGeneratedForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Verifique os dados do arquivamento: " + "; ".join(
            f"{form.fields[k].label}: {' '.join(v)}" if k in form.fields else " ".join(v)
            for k, v in form.errors.items()
        ))
        return redirect(obj)
    contract = form.save(commit=False)
    contract.generated_from = obj
    contract.file.save(f"{slugify(contract.name) or 'contrato'}.pdf", ContentFile(html_to_pdf(obj.final_html)), save=False)
    contract.save()
    messages.success(request, f"Contrato '{contract.name}' salvo no arquivo de contratos.")
    return redirect("contracts:archive")


def generated_delete(request, pk):
    obj = get_object_or_404(GeneratedContract, pk=pk)
    if request.method == "POST":
        obj.delete()
        messages.success(request, "Contrato gerado apagado.")
        return redirect("contracts:generated_list")
    return render(
        request,
        "core/confirm_delete.html",
        {"object": obj, "kind": "contrato gerado", "cancel_url": obj.get_absolute_url()},
    )


# --- Archive (upload / análise de contratos) ------------------------------------

def archive(request):
    form = ContractUploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        obj = form.save()
        messages.success(request, f"Contrato '{obj.name}' enviado com sucesso!")
        return redirect("contracts:archive")

    contracts = Contract.objects.all()
    q = request.GET.get("q", "").strip()
    kind = request.GET.get("type", "")
    contractor = request.GET.get("contractor", "")
    if q:
        contracts = contracts.filter(Q(name__icontains=q) | Q(contractor__icontains=q))
    if kind:
        contracts = contracts.filter(contract_type=kind)
    if contractor:
        contracts = contracts.filter(contractor=contractor)
    return render(
        request,
        "contracts/archive.html",
        {
            "form": form,
            "open_form": request.method == "POST",
            "contracts": Paginator(contracts, 25).get_page(request.GET.get("page")),
            "stats": contracts.aggregate(count=Count("id"), total=Sum("value")),
            "kinds": Contract.Kind.choices,
            "contractors": Contract.objects.order_by("contractor").values_list("contractor", flat=True).distinct(),
            "filters": {"q": q, "type": kind, "contractor": contractor},
        },
    )


def archive_edit(request, pk):
    obj = get_object_or_404(Contract, pk=pk)
    old_file = obj.file.name
    form = ContractUploadForm(request.POST or None, request.FILES or None, instance=obj)
    form.fields["file"].required = False
    if request.method == "POST" and form.is_valid():
        obj = form.save()
        if old_file and obj.file.name != old_file:
            obj.file.storage.delete(old_file)
        messages.success(request, "Contrato atualizado.")
        return redirect("contracts:archive")
    return render(request, "contracts/archive_form.html", {"form": form, "contract": obj})


def archive_delete(request, pk):
    obj = get_object_or_404(Contract, pk=pk)
    if request.method == "POST":
        obj.file.delete(save=False)
        obj.delete()
        messages.success(request, f"Contrato '{obj.name}' apagado.")
        return redirect("contracts:archive")
    return render(
        request, "core/confirm_delete.html", {"object": obj, "kind": "contrato", "cancel_url": reverse("contracts:archive")}
    )


def archive_preview(request, pk):
    obj = get_object_or_404(Contract, pk=pk)
    return render(request, "contracts/archive_preview.html", {"contract": obj})


@xframe_options_sameorigin
def archive_file(request, pk):
    obj = get_object_or_404(Contract, pk=pk)
    download = request.GET.get("download") == "1" or not obj.previewable
    try:
        handle = obj.file.open("rb")
    except FileNotFoundError as exc:
        raise Http404("Arquivo não encontrado.") from exc
    mime = mimetypes.guess_type(obj.file.name)[0] or "application/octet-stream"
    if obj.extension in {"html", "htm", "txt"}:
        mime += "; charset=utf-8"
    response = FileResponse(handle, content_type=mime, as_attachment=download, filename=obj.download_name)
    if obj.extension in {"html", "htm"}:
        response["Content-Security-Policy"] = SANDBOX_CSP
    return response


# --- E-signature ---------------------------------------------------------------

def signatures(request):
    providers = [
        {
            "name": "Autentique",
            "slug": "autentique",
            "url": settings.AUTENTIQUE_URL,
            "icon": "shield-check",
            "description": "Assinatura eletrônica com validade jurídica. Plano gratuito com assinaturas mensais limitadas.",
        },
        {
            "name": "ZapSign",
            "slug": "zapsign",
            "url": settings.ZAPSIGN_URL,
            "icon": "pen",
            "description": "Envio para assinatura por link ou WhatsApp. Plano gratuito com assinaturas mensais limitadas.",
        },
    ]
    recent = Contract.objects.filter(file__iendswith=".pdf")[:10]
    return render(request, "contracts/signatures.html", {"providers": providers, "recent": recent})
