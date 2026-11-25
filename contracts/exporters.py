"""HTML -> PDF / DOCX conversion for finished contracts."""

import re
from io import BytesIO

_STYLE_RE = re.compile(r"<style\b[^>]*>.*?</style\s*>", re.IGNORECASE | re.DOTALL)
_HEAD_RE = re.compile(r"<head\b[^>]*>.*?</head\s*>", re.IGNORECASE | re.DOTALL)


def html_to_pdf(document: str) -> bytes:
    from weasyprint import HTML  # imported lazily: needs system Pango libraries

    return HTML(string=document).write_pdf()


def html_to_docx(document: str) -> bytes:
    from docx import Document
    from htmldocx import HtmlToDocx

    # htmldocx would otherwise dump the CSS and <title> as body text.
    body = _HEAD_RE.sub("", _STYLE_RE.sub("", document))
    doc = Document()
    HtmlToDocx().add_html_to_document(body, doc)
    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()
