"""Aggregations for the financial dashboard (replaces the pandas pipeline)."""

from collections import defaultdict
from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.db.models import Avg, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from .models import EntryType, Installment, Transaction

ZERO = Decimal("0")


def default_period(today: date | None = None) -> tuple[date, date]:
    """First day two months ago through the last day three months ahead."""
    today = today or timezone.localdate()
    start = (today - relativedelta(months=2)).replace(day=1)
    end = (today + relativedelta(months=3)).replace(day=1) + relativedelta(months=1, days=-1)
    return start, end


def month_range(start: date, end: date) -> list[date]:
    months, cursor = [], start.replace(day=1)
    while cursor <= end:
        months.append(cursor)
        cursor += relativedelta(months=1)
    return months


def dashboard_data(start: date, end: date) -> dict:
    installments = Installment.objects.filter(due_date__range=(start, end))
    months = month_range(start, end)
    labels = [m.strftime("%Y-%m") for m in months]

    by_month_type = defaultdict(lambda: ZERO)
    for row in (
        installments.annotate(month=TruncMonth("due_date"))
        .values("month", "transaction__type")
        .annotate(total=Sum("amount"))
    ):
        by_month_type[(row["month"].strftime("%Y-%m"), row["transaction__type"])] = row["total"]

    by_month_status = defaultdict(lambda: ZERO)
    for row in (
        installments.annotate(month=TruncMonth("due_date")).values("month", "status").annotate(total=Sum("amount"))
    ):
        by_month_status[(row["month"].strftime("%Y-%m"), row["status"])] = row["total"]

    income = [by_month_type[(m, EntryType.SALE)] for m in labels]
    expense = [by_month_type[(m, EntryType.EXPENSE)] for m in labels]
    balance, running = [], ZERO
    for inc, exp in zip(income, expense):
        running += inc - exp
        balance.append(running)

    # Expenses per category per month
    categories = defaultdict(lambda: defaultdict(lambda: ZERO))
    for row in (
        installments.filter(transaction__type=EntryType.EXPENSE)
        .annotate(month=TruncMonth("due_date"))
        .values("month", "transaction__category__name")
        .annotate(total=Sum("amount"))
    ):
        categories[row["transaction__category__name"]][row["month"].strftime("%Y-%m")] = row["total"]

    total_income, total_expense = sum(income, ZERO), sum(expense, ZERO)
    avg_ticket = (
        Transaction.objects.filter(type=EntryType.SALE, transaction_date__range=(start, end)).aggregate(
            v=Avg("total_amount")
        )["v"]
        or ZERO
    )
    overdue_total = (
        Installment.objects.overdue().filter(transaction__type=EntryType.SALE).aggregate(v=Sum("amount"))["v"] or ZERO
    )

    return {
        "kpis": {
            "income": total_income,
            "expense": total_expense,
            "profit": total_income - total_expense,
            "avg_ticket": avg_ticket,
            "overdue": overdue_total,
        },
        "has_data": installments.exists(),
        "chart": {
            "labels": labels,
            "income": [float(v) for v in income],
            "expense": [float(v) for v in expense],
            "balance": [float(v) for v in balance],
            "paid": [float(by_month_status[(m, Installment.Status.PAID)]) for m in labels],
            "pending": [float(by_month_status[(m, Installment.Status.PENDING)]) for m in labels],
            "categories": [
                {"name": name, "data": [float(values[m]) for m in labels]} for name, values in sorted(categories.items())
            ],
        },
    }


def pending_installments(start: date, end: date):
    base = (
        Installment.objects.filter(due_date__range=(start, end), status=Installment.Status.PENDING)
        .select_related("transaction", "transaction__category")
        .order_by("due_date")
    )
    sales = list(base.filter(transaction__type=EntryType.SALE))
    expenses_by_month = defaultdict(list)
    for inst in base.filter(transaction__type=EntryType.EXPENSE):
        expenses_by_month[inst.due_date.replace(day=1)].append(inst)
    expense_groups = [
        {"month": month, "items": items, "total": sum((i.amount for i in items), ZERO)}
        for month, items in sorted(expenses_by_month.items())
    ]
    return sales, expense_groups
