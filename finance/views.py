from datetime import date

from django.contrib import messages
from django.db import transaction as db_transaction
from django.db.models import Count, ProtectedError, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from core.pagination import paginate

from . import services
from .forms import CategoryForm, PeriodForm, TransactionForm
from .models import Category, EntryType, Installment, Transaction


def _period_from_request(request):
    start, end = services.default_period()
    form = PeriodForm(request.GET or {"start": start, "end": end})
    if form.is_valid():
        start, end = form.cleaned_data["start"], form.cleaned_data["end"]
    return form, start, end


def _redirect_back(request, fallback: str):
    target = request.POST.get("next") or request.META.get("HTTP_REFERER")
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        return redirect(target)
    return redirect(fallback)


def dashboard(request):
    period_form, start, end = _period_from_request(request)

    if request.method == "POST":
        form = TransactionForm(request.POST)
        if form.is_valid():
            Transaction.create_with_installments(**form.cleaned_data)
            messages.success(request, "Lançamento salvo!")
            return redirect(request.get_full_path())
    else:
        form = TransactionForm()

    data = services.dashboard_data(start, end)
    pending_sales, pending_expense_groups = services.pending_installments(start, end)
    return render(
        request,
        "finance/dashboard.html",
        {
            "form": form,
            "form_has_errors": request.method == "POST",
            "period_form": period_form,
            "start": start,
            "end": end,
            "has_categories": Category.objects.exists(),
            "pending_sales": paginate(request, pending_sales, per_page=10, param="sales_page"),
            "pending_expense_groups": paginate(request, pending_expense_groups, per_page=10, param="exp_page"),
            **data,
        },
    )


@require_POST
def installment_set_status(request, pk):
    installment = get_object_or_404(Installment, pk=pk)
    if request.POST.get("status") == Installment.Status.PENDING:
        installment.mark_pending()
        messages.info(request, f"Parcela '{installment}' voltou para pendente.")
    else:
        installment.mark_paid()
        messages.success(request, f"Parcela '{installment}' marcada como paga.")
    return _redirect_back(request, reverse("finance:dashboard"))


@require_POST
def installments_pay_month(request):
    try:
        month = date.fromisoformat(request.POST["month"]).replace(day=1)
    except (KeyError, ValueError):
        messages.error(request, "Mês inválido.")
        return _redirect_back(request, reverse("finance:dashboard"))
    entry_type = request.POST.get("type", EntryType.EXPENSE)
    qs = Installment.objects.filter(
        status=Installment.Status.PENDING,
        transaction__type=entry_type,
        due_date__year=month.year,
        due_date__month=month.month,
    )
    ids = request.POST.getlist("ids")
    if ids:  # only the items that were displayed on the page
        qs = qs.filter(pk__in=ids)
    with db_transaction.atomic():
        items = list(qs)
        for inst in items:
            inst.mark_paid()
    messages.success(request, f"{len(items)} parcela(s) de {month:%m/%Y} marcada(s) como paga(s).")
    return _redirect_back(request, reverse("finance:dashboard"))


# --- Audit -----------------------------------------------------------------

def audit(request):
    q = request.GET.get("q", "").strip()
    entry_type = request.GET.get("type", "")
    category_id = request.GET.get("category", "")

    transactions = Transaction.objects.select_related("category").annotate(
        paid_count=Count("installments", filter=Q(installments__status=Installment.Status.PAID))
    ).order_by("-transaction_date", "-id")
    if q:
        transactions = transactions.filter(description__icontains=q)
    if entry_type in EntryType.values:
        transactions = transactions.filter(type=entry_type)
    if category_id.isdigit():
        transactions = transactions.filter(category_id=category_id)

    status = request.GET.get("status", "")
    installments = Installment.objects.select_related("transaction", "transaction__category").order_by("-due_date")
    if q:
        installments = installments.filter(transaction__description__icontains=q)
    if entry_type in EntryType.values:
        installments = installments.filter(transaction__type=entry_type)
    if category_id.isdigit():
        installments = installments.filter(transaction__category_id=category_id)
    if status == "overdue":
        installments = installments.overdue()
    elif status in Installment.Status.values:
        installments = installments.filter(status=status)

    by_category = list(
        Transaction.objects.values("category__name", "type")
        .annotate(total=Sum("total_amount"), count=Count("id"))
        .order_by("-total", "category__name")
    )

    tab = request.GET.get("tab", "transactions")
    return render(
        request,
        "finance/audit.html",
        {
            "tab": tab,
            "transactions": paginate(request, transactions, per_page=25),
            "installments": paginate(request, installments, per_page=50),
            "by_category": by_category,  # full list feeds the chart
            "by_category_page": paginate(request, by_category, per_page=25),
            "categories": Category.objects.all(),
            "entry_types": EntryType.choices,
            "filters": {"q": q, "type": entry_type, "category": category_id, "status": status},
        },
    )


def transaction_detail(request, pk):
    obj = get_object_or_404(Transaction.objects.select_related("category"), pk=pk)
    return render(
        request,
        "finance/transaction_detail.html",
        {"transaction": obj, "installments": paginate(request, obj.installments.order_by("number"), per_page=25)},
    )


def transaction_edit(request, pk):
    obj = get_object_or_404(Transaction, pk=pk)
    has_paid = obj.installments.filter(status=Installment.Status.PAID).exists()
    form = TransactionForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        schedule_fields = {"total_amount", "transaction_date", "installments_count"}
        schedule_changed = bool(schedule_fields & set(form.changed_data))
        if schedule_changed and has_paid:
            form.add_error(
                None,
                "Esta transação já possui parcelas pagas: valor, data e número de parcelas não podem ser alterados. "
                "Estorne os pagamentos primeiro.",
            )
        else:
            with db_transaction.atomic():
                obj = form.save(commit=False)
                obj.type = obj.category.type
                obj.save()
                if schedule_changed:
                    obj.rebuild_installments()
            messages.success(request, "Transação atualizada.")
            return redirect("finance:transaction_detail", pk=obj.pk)
    return render(request, "finance/transaction_form.html", {"form": form, "transaction": obj, "has_paid": has_paid})


def transaction_delete(request, pk):
    obj = get_object_or_404(Transaction, pk=pk)
    if request.method == "POST":
        obj.delete()
        messages.success(request, f"Transação '{obj}' apagada.")
        return redirect("finance:audit")
    return render(
        request,
        "core/confirm_delete.html",
        {"object": obj, "kind": "transação", "cancel_url": reverse("finance:transaction_detail", args=[pk]),
         "warning": "Todas as parcelas desta transação também serão apagadas."},
    )


# --- Categories --------------------------------------------------------------

def categories(request):
    form = CategoryForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Categoria criada.")
        return redirect("finance:categories")
    items = Category.objects.annotate(n=Count("transactions")).order_by("type", "name")
    return render(request, "finance/categories.html", {"form": form, "categories": paginate(request, items)})


def category_edit(request, pk):
    obj = get_object_or_404(Category, pk=pk)
    form = CategoryForm(request.POST or None, instance=obj)
    if obj.transactions.exists():
        form.fields["type"].disabled = True
        form.fields["type"].help_text = "O tipo não pode mudar porque a categoria já possui lançamentos."
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Categoria atualizada.")
        return redirect("finance:categories")
    return render(request, "finance/category_form.html", {"form": form, "category": obj})


@require_POST
def category_delete(request, pk):
    obj = get_object_or_404(Category, pk=pk)
    try:
        obj.delete()
        messages.success(request, f"Categoria '{obj.name}' apagada.")
    except ProtectedError:
        messages.error(request, "Não é possível apagar uma categoria que possui lançamentos.")
    return redirect("finance:categories")
