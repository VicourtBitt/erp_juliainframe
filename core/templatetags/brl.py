from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


def format_brl(value, symbol: bool = True) -> str:
    """Format a number as Brazilian Real: 1234.5 -> 'R$ 1.234,50'."""
    try:
        number = Decimal(value or 0)
    except (InvalidOperation, TypeError, ValueError):
        return str(value)
    text = f"{abs(number):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    sign = "-" if number < 0 else ""
    return f"{sign}R$ {text}" if symbol else f"{sign}{text}"


@register.filter
def brl(value):
    return format_brl(value)


@register.filter
def percent(value):
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return str(value)
    return f"{number:+.2f}%".replace(".", ",")


@register.filter
def bs(bound_field, extra_classes=""):
    """Render a form field widget with the right Bootstrap class."""
    widget = bound_field.field.widget
    input_type = getattr(widget, "input_type", "")
    if input_type in {"checkbox", "radio"}:
        css = "form-check-input"
    elif input_type == "select" or widget.__class__.__name__ in {"Select", "SelectMultiple"}:
        css = "form-select"
    else:
        css = "form-control"
    if bound_field.errors:
        css += " is-invalid"
    attrs = {"class": f"{css} {extra_classes}".strip()}
    existing = widget.attrs.get("class")
    if existing:
        attrs["class"] += f" {existing}"
    return bound_field.as_widget(attrs=attrs)


@register.simple_tag(takes_context=True)
def query_replace(context, **kwargs):
    """Current querystring with some keys replaced (for pagination/tabs)."""
    query = context["request"].GET.copy()
    for key, value in kwargs.items():
        if value in (None, ""):
            query.pop(key, None)
        else:
            query[key] = value
    return query.urlencode()


@register.simple_tag(takes_context=True)
def page_url(context, page, number):
    """Querystring for ``page`` (from core.pagination.paginate) pointing at ``number``."""
    query = context["request"].GET.copy()
    query[page.param] = number
    return query.urlencode()


@register.simple_tag(takes_context=True)
def hidden_query_inputs(context, *exclude):
    """Hidden inputs that preserve the current querystring in a GET form."""
    from django.utils.html import format_html, format_html_join

    items = [
        (key, value)
        for key, values in context["request"].GET.lists()
        if key not in exclude
        for value in values
    ]
    return format_html_join("", '<input type="hidden" name="{}" value="{}">', items) if items else format_html("")
