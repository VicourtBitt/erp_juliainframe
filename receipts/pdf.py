"""Receipt PDF rendering with ReportLab (ported from the Streamlit version)."""

from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas

from core.templatetags.brl import format_brl

MONTHS = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]


def date_long(d) -> str:
    # Avoids depending on the pt_BR locale being installed on the server.
    return f"{d.day:02d} de {MONTHS[d.month - 1]} de {d.year}"


def render_receipt_pdf(receipt) -> bytes:
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setTitle(f"Recibo {receipt.number}")
    width, height = A4
    margin = 1 * inch
    right = width - margin
    y = height - margin
    items = list(receipt.items.all())
    total = receipt.total

    c.setFont("Helvetica-Bold", 22)
    c.drawString(margin, y, "RECIBO DE PAGAMENTO")
    c.setFont("Helvetica", 11)
    c.drawRightString(right, y + 15, "VALOR TOTAL")
    c.setFont("Helvetica-Bold", 22)
    c.drawRightString(right, y - 5, format_brl(total))

    y -= 20
    c.setFont("Helvetica", 9)
    c.setFillColorRGB(0.5, 0.5, 0.5)
    c.drawString(margin, y, f"Recibo nº {receipt.number}")
    y -= 0.75 * inch - 20

    c.setStrokeColorRGB(0.8, 0.8, 0.8)
    c.line(margin, y, right, y)
    y -= 0.5 * inch

    c.setFillColorRGB(0, 0, 0)
    body = (
        f"Recebemos de {receipt.payer_name.upper()}, portador(a) do documento (CPF/CNPJ) nº "
        f"{receipt.payer_document}, a importância de {format_brl(total)}, referente ao pagamento de:"
    )
    c.setFont("Helvetica", 12)
    for line in simpleSplit(body, "Helvetica", 12, right - margin):
        c.drawString(margin, y, line)
        y -= 16
    y -= 0.25 * inch

    def table_header(label="DESCRIÇÃO"):
        nonlocal y
        c.setFont("Helvetica-Bold", 10)
        c.setFillColorRGB(0.3, 0.3, 0.3)
        c.drawString(margin, y, label)
        c.drawRightString(right, y, "VALOR (R$)")
        y -= 12
        c.setStrokeColorRGB(0.8, 0.8, 0.8)
        c.line(margin, y, right, y)
        y -= 15

    c.setFont("Helvetica-Bold", 11)
    c.drawString(margin, y, "ITENS DO SERVIÇO:")
    y -= 0.25 * inch
    table_header()

    desc_width = right - margin - 2 * inch
    for item in items:
        lines = simpleSplit(item.description, "Helvetica", 10, desc_width)
        if y - 13 * len(lines) < margin + 2 * inch:
            c.showPage()
            y = height - margin
            table_header("DESCRIÇÃO (continuação)")
        c.setFont("Helvetica", 10)
        c.setFillColorRGB(0.1, 0.1, 0.1)
        start = y
        c.drawRightString(right, y, format_brl(item.price, symbol=False))
        for line in lines:
            c.drawString(margin, y, line)
            y -= 13
        y = min(y, start - 15) - 5

    y -= 10
    c.setStrokeColorRGB(0.6, 0.6, 0.6)
    c.line(margin, y, right, y)
    y -= 20
    c.setFont("Helvetica-Bold", 12)
    c.setFillColorRGB(0, 0, 0)
    c.drawString(margin, y, "VALOR TOTAL")
    c.drawRightString(right, y, format_brl(total))

    # Signature block needs ~3.5in; start a new page if it doesn't fit.
    if y - 3.5 * inch < margin:
        c.showPage()
        y = height - margin
    y -= 0.75 * inch
    c.setFont("Helvetica", 12)
    c.drawRightString(right, y, f"{receipt.location}, {date_long(receipt.issue_date)}.")
    y -= 1.5 * inch
    c.line(margin + 1.5 * inch, y, right - 1.5 * inch, y)
    y -= 15
    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(width / 2, y, receipt.payee_name.upper())
    y -= 15
    c.setFont("Helvetica", 10)
    c.drawCentredString(width / 2, y, f"CPF/CNPJ: {receipt.payee_document}")
    y -= 12
    c.drawCentredString(width / 2, y, "(Contratado / Prestador do Serviço)")

    c.showPage()
    c.save()
    return buffer.getvalue()
