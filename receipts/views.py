from django.contrib import messages
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from core.pagination import paginate

from .forms import ReceiptForm, ReceiptItemFormSet
from .models import Receipt
from .pdf import render_receipt_pdf


def _save_pdf(receipt):
    receipt.recompute_total()
    if receipt.pdf:
        receipt.pdf.delete(save=False)
    receipt.pdf.save(receipt.filename, ContentFile(render_receipt_pdf(receipt)), save=False)
    receipt.save()


def receipt_list(request):
    receipts = Receipt.objects.all()
    q = request.GET.get("q", "").strip()
    payer = request.GET.get("payer", "")
    payee = request.GET.get("payee", "")
    if q:
        receipts = receipts.filter(
            Q(payer_name__icontains=q) | Q(payee_name__icontains=q) | Q(items__description__icontains=q)
        ).distinct()
    if payer:
        receipts = receipts.filter(payer_name=payer)
    if payee:
        receipts = receipts.filter(payee_name=payee)
    stats = receipts.aggregate(count=Count("id", distinct=True), total=Sum("total"))
    return render(
        request,
        "receipts/list.html",
        {
            "receipts": paginate(request, receipts),
            "stats": stats,
            "payers": Receipt.objects.order_by("payer_name").values_list("payer_name", flat=True).distinct(),
            "payees": Receipt.objects.order_by("payee_name").values_list("payee_name", flat=True).distinct(),
            "filters": {"q": q, "payer": payer, "payee": payee},
        },
    )


def receipt_form(request, pk=None):
    receipt = get_object_or_404(Receipt, pk=pk) if pk else None
    initial = {}
    if receipt is None and (last := Receipt.objects.first()):
        # The payee (the business itself) rarely changes: prefill from last receipt.
        initial = {"payee_name": last.payee_name, "payee_document": last.payee_document, "location": last.location}
    form = ReceiptForm(request.POST or None, instance=receipt, initial=initial)
    formset = ReceiptItemFormSet(request.POST or None, instance=receipt or Receipt())
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        with transaction.atomic():
            receipt = form.save()
            formset.instance = receipt
            formset.save()
            _save_pdf(receipt)
        messages.success(request, f"Recibo {receipt.number} salvo.")
        return redirect("receipts:detail", pk=receipt.pk)
    return render(request, "receipts/form.html", {"form": form, "formset": formset, "receipt": receipt})


def receipt_detail(request, pk):
    receipt = get_object_or_404(Receipt.objects.prefetch_related("items"), pk=pk)
    return render(request, "receipts/detail.html", {"receipt": receipt})


def receipt_pdf(request, pk):
    receipt = get_object_or_404(Receipt, pk=pk)
    if not receipt.pdf:
        _save_pdf(receipt)
    try:
        handle = receipt.pdf.open("rb")
    except FileNotFoundError as exc:
        raise Http404("Arquivo do recibo não encontrado.") from exc
    return FileResponse(
        handle,
        content_type="application/pdf",
        as_attachment=request.GET.get("download") == "1",
        filename=receipt.filename,
    )


def receipt_delete(request, pk):
    receipt = get_object_or_404(Receipt, pk=pk)
    if request.method == "POST":
        if receipt.pdf:
            receipt.pdf.delete(save=False)
        receipt.delete()
        messages.success(request, "Recibo apagado.")
        return redirect("receipts:list")
    return render(
        request,
        "core/confirm_delete.html",
        {"object": receipt, "kind": "recibo", "cancel_url": reverse("receipts:detail", args=[pk])},
    )
