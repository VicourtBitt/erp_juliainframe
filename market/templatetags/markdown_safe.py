import bleach
import markdown as md
from django import template
from django.utils.safestring import mark_safe

register = template.Library()

ALLOWED_TAGS = [
    "p", "br", "strong", "em", "b", "i", "ul", "ol", "li", "h1", "h2", "h3", "h4", "h5", "h6",
    "blockquote", "code", "pre", "hr", "table", "thead", "tbody", "tr", "th", "td",
]


@register.filter
def markdown_safe(text):
    """Render AI-produced Markdown and strip anything that isn't plain formatting."""
    html = md.markdown(text or "", extensions=["tables", "sane_lists"])
    return mark_safe(bleach.clean(html, tags=ALLOWED_TAGS, attributes={}, strip=True))


@register.filter
def currency_symbol(code):
    from market.services import currency_symbol as _symbol

    return _symbol(code)
