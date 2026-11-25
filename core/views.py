from django.db.models import Sum
from django.shortcuts import render
from django.utils import timezone

from contracts.models import Contract, GeneratedContract
from finance.models import EntryType, Installment
from receipts.models import Receipt


def _total(qs):
    return qs.aggregate(v=Sum("amount"))["v"] or 0


def home(request):
    today = timezone.localdate()
    month = Installment.objects.filter(due_date__year=today.year, due_date__month=today.month)
    overdue = Installment.objects.overdue().select_related("transaction").order_by("due_date")
    upcoming = (
        Installment.objects.filter(status=Installment.Status.PENDING, due_date__gte=today)
        .select_related("transaction")
        .order_by("due_date")[:8]
    )
    return render(
        request,
        "core/home.html",
        {
            "today": today,
            "month_income": _total(month.filter(transaction__type=EntryType.SALE)),
            "month_expense": _total(month.filter(transaction__type=EntryType.EXPENSE)),
            "overdue_sales": _total(overdue.filter(transaction__type=EntryType.SALE)),
            "overdue_count": overdue.count(),
            "overdue": overdue[:8],
            "upcoming": upcoming,
            "contracts_count": Contract.objects.count(),
            "drafts_count": GeneratedContract.objects.filter(final_html="").count(),
            "recent_receipts": Receipt.objects.all()[:5],
        },
    )
