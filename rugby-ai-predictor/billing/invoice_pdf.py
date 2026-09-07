"""Professional SARS tax invoice PDFs (clean layout; discreet sandbox note only)."""

from __future__ import annotations

import base64
import io
from datetime import datetime
from typing import Any, Dict, Optional


# Palette — restrained charcoal / ink, one accent
INK = "#111827"
MUTED = "#6B7280"
LINE = "#E5E7EB"
LINE_SOFT = "#F3F4F6"
ACCENT = "#0F766E"  # deep teal — premium, not neon green
ACCENT_SOFT = "#F0FDFA"
PAPER = "#FFFFFF"


def _money(cents: int, currency: str = "ZAR") -> str:
    value = cents / 100.0
    if currency == "ZAR":
        # South African style: R 1,234.56
        return f"R {value:,.2f}"
    return f"{currency} {value:,.2f}"


def _fmt_date(iso_or_date: Optional[str]) -> str:
    raw = (iso_or_date or "").strip()
    if not raw:
        return datetime.utcnow().strftime("%d %B %Y")
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).strftime("%d %B %Y")
    except Exception:
        try:
            return datetime.strptime(raw[:10], "%Y-%m-%d").strftime("%d %B %Y")
        except Exception:
            return raw


def build_invoice_pdf_bytes(invoice: Dict[str, Any]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        HRFlowable,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    ink = colors.HexColor(INK)
    muted = colors.HexColor(MUTED)
    line = colors.HexColor(LINE)
    line_soft = colors.HexColor(LINE_SOFT)
    accent = colors.HexColor(ACCENT)
    accent_soft = colors.HexColor(ACCENT_SOFT)

    buffer = io.BytesIO()
    page_w, page_h = A4
    margin_x = 18 * mm
    margin_y = 16 * mm

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=margin_x,
        rightMargin=margin_x,
        topMargin=20 * mm,
        bottomMargin=18 * mm,
        title=f"Tax Invoice {invoice.get('invoice_number')}",
        author=(invoice.get("supplier") or {}).get("legal_name") or "Rugby AI Predictor",
    )

    styles = getSampleStyleSheet()
    brand = ParagraphStyle(
        "Brand",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=13,
        textColor=ink,
        leading=16,
        spaceAfter=0,
    )
    brand_sub = ParagraphStyle(
        "BrandSub",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        textColor=muted,
        leading=11,
    )
    doc_title = ParagraphStyle(
        "DocTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=22,
        textColor=ink,
        alignment=TA_RIGHT,
        leading=26,
    )
    meta_label = ParagraphStyle(
        "MetaLabel",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.5,
        textColor=muted,
        alignment=TA_RIGHT,
        leading=9,
        spaceBefore=0,
        spaceAfter=0,
    )
    meta_value = ParagraphStyle(
        "MetaValue",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        textColor=ink,
        alignment=TA_RIGHT,
        leading=11,
    )
    section = ParagraphStyle(
        "Section",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.5,
        textColor=muted,
        leading=9,
        spaceBefore=0,
        spaceAfter=4,
    )
    body = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        textColor=ink,
        leading=12.5,
    )
    body_bold = ParagraphStyle(
        "BodyBold",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9.5,
        textColor=ink,
        leading=13,
    )
    th = ParagraphStyle(
        "TH",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.5,
        textColor=muted,
        leading=9,
    )
    th_right = ParagraphStyle("THRight", parent=th, alignment=TA_RIGHT)
    td = ParagraphStyle(
        "TD",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        textColor=ink,
        leading=12,
    )
    td_right = ParagraphStyle("TDRight", parent=td, alignment=TA_RIGHT)
    td_center = ParagraphStyle("TDCenter", parent=td, alignment=TA_CENTER)
    total_label = ParagraphStyle(
        "TotalLabel",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        textColor=muted,
        alignment=TA_RIGHT,
        leading=12,
    )
    total_value = ParagraphStyle(
        "TotalValue",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        textColor=ink,
        alignment=TA_RIGHT,
        leading=12,
    )
    grand_label = ParagraphStyle(
        "GrandLabel",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        textColor=ink,
        alignment=TA_RIGHT,
        leading=13,
    )
    grand_value = ParagraphStyle(
        "GrandValue",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=12,
        textColor=accent,
        alignment=TA_RIGHT,
        leading=15,
    )
    license_label = ParagraphStyle(
        "LicLabel",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.5,
        textColor=muted,
        alignment=TA_CENTER,
        leading=9,
    )
    license_key = ParagraphStyle(
        "LicKey",
        parent=styles["Normal"],
        fontName="Courier-Bold",
        fontSize=13,
        textColor=ink,
        alignment=TA_CENTER,
        leading=16,
        spaceBefore=2,
    )
    foot = ParagraphStyle(
        "Foot",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.5,
        textColor=muted,
        leading=10,
        alignment=TA_LEFT,
    )

    supplier = invoice.get("supplier") or {}
    customer = invoice.get("customer") or {}
    totals = invoice.get("totals") or {}
    payment = invoice.get("payment") or {}
    currency = invoice.get("currency") or "ZAR"
    sandbox = bool(invoice.get("sandbox"))
    content_w = page_w - (2 * margin_x)

    issued_fmt = _fmt_date(invoice.get("issued_at_iso"))
    supply_fmt = _fmt_date(invoice.get("supply_date") or invoice.get("issued_at_iso"))

    address_lines = [str(x) for x in (supplier.get("address_lines") or []) if x]
    trading = supplier.get("trading_name") or supplier.get("legal_name") or "Rugby AI Predictor"
    legal = supplier.get("legal_name") or trading
    supplier_detail_lines = []
    if legal and legal != trading:
        supplier_detail_lines.append(legal)
    supplier_detail_lines.extend(address_lines)
    contact = []
    if supplier.get("email"):
        contact.append(supplier["email"])
    if supplier.get("phone"):
        contact.append(supplier["phone"])
    if contact:
        supplier_detail_lines.append(" · ".join(contact))
    reg_bits = []
    if supplier.get("company_reg"):
        reg_bits.append(f"Reg {supplier['company_reg']}")
    if supplier.get("vat_registered") and supplier.get("vat_number"):
        reg_bits.append(f"VAT {supplier['vat_number']}")
    elif not supplier.get("vat_registered"):
        reg_bits.append("VAT not registered")
    if reg_bits:
        supplier_detail_lines.append(" · ".join(reg_bits))

    story = []

    # —— Header: brand | TAX INVOICE + meta ——
    header = Table(
        [
            [
                [
                    Paragraph(str(trading).upper(), brand),
                    Spacer(1, 2),
                    Paragraph("<br/>".join(supplier_detail_lines), brand_sub)
                    if supplier_detail_lines
                    else Spacer(1, 1),
                ],
                [
                    Paragraph("TAX INVOICE", doc_title),
                    Spacer(1, 6),
                    Paragraph("INVOICE NUMBER", meta_label),
                    Paragraph(str(invoice.get("invoice_number") or "—"), meta_value),
                    Spacer(1, 4),
                    Paragraph("ISSUE DATE", meta_label),
                    Paragraph(issued_fmt, meta_value),
                    Spacer(1, 4),
                    Paragraph("SUPPLY DATE", meta_label),
                    Paragraph(supply_fmt, meta_value),
                ],
            ]
        ],
        colWidths=[content_w * 0.58, content_w * 0.42],
    )
    header.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(header)
    story.append(Spacer(1, 10))
    story.append(
        HRFlowable(width="100%", thickness=1.25, color=accent, spaceBefore=0, spaceAfter=14)
    )

    # —— Bill to | Payment status ——
    bill_parts = [f"<b>{customer.get('name') or 'Customer'}</b>"]
    if customer.get("email"):
        bill_parts.append(customer["email"])
    if customer.get("address"):
        bill_parts.append(customer["address"])
    if customer.get("vat_number"):
        bill_parts.append(f"VAT {customer['vat_number']}")

    method = (payment.get("method") or "card").replace("_", " ").title()
    brand_pay = (payment.get("brand") or "").replace("_", " ").title()
    last4 = payment.get("last4")
    pay_line = method
    if brand_pay:
        pay_line = f"{brand_pay} {method}" if method.lower() != "apple pay" else "Apple Pay"
    if last4 and last4 != "0000":
        pay_line += f" · •••• {last4}"

    status = (invoice.get("status") or "paid").upper()
    bill_table = Table(
        [
            [
                [
                    Paragraph("BILLED TO", section),
                    Paragraph("<br/>".join(bill_parts), body),
                ],
                [
                    Paragraph("PAYMENT", section),
                    Paragraph(f"<b>{status}</b>", body_bold),
                    Paragraph(pay_line, body),
                    Paragraph(
                        f"Ref {payment.get('payment_id') or '—'}",
                        brand_sub,
                    ),
                ],
            ]
        ],
        colWidths=[content_w * 0.58, content_w * 0.42],
    )
    bill_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("BACKGROUND", (1, 0), (1, 0), accent_soft),
                ("BOX", (1, 0), (1, 0), 0.5, colors.HexColor("#CCFBF1")),
                ("LEFTPADDING", (1, 0), (1, 0), 10),
                ("RIGHTPADDING", (1, 0), (1, 0), 10),
                ("TOPPADDING", (1, 0), (1, 0), 8),
                ("BOTTOMPADDING", (1, 0), (1, 0), 8),
            ]
        )
    )
    story.append(bill_table)
    story.append(Spacer(1, 18))

    # —— Line items ——
    rows = [
        [
            Paragraph("DESCRIPTION", th),
            Paragraph("QTY", th_right),
            Paragraph("EXCL. VAT", th_right),
            Paragraph("VAT", th_right),
            Paragraph("TOTAL", th_right),
        ]
    ]
    for item in invoice.get("line_items") or []:
        rows.append(
            [
                Paragraph(item.get("description") or "Subscription", td),
                Paragraph(str(item.get("quantity") or 1), td_center),
                Paragraph(_money(int(item.get("line_excl_cents") or 0), currency), td_right),
                Paragraph(_money(int(item.get("vat_cents") or 0), currency), td_right),
                Paragraph(_money(int(item.get("line_incl_cents") or 0), currency), td_right),
            ]
        )

    col_w = [
        content_w * 0.44,
        content_w * 0.08,
        content_w * 0.16,
        content_w * 0.16,
        content_w * 0.16,
    ]
    items = Table(rows, colWidths=col_w, repeatRows=1)
    items.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), line_soft),
                ("LINEBELOW", (0, 0), (-1, 0), 0.75, line),
                ("LINEBELOW", (0, 1), (-1, -1), 0.4, line),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, 0), 8),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                ("TOPPADDING", (0, 1), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 10),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(items)
    story.append(Spacer(1, 12))

    # —— Totals ——
    vat_rate = float(supplier.get("vat_rate") or 0)
    vat_label = f"VAT ({vat_rate * 100:.0f}%)" if vat_rate else "VAT"
    totals_data = [
        [
            Paragraph("Subtotal (excl. VAT)", total_label),
            Paragraph(_money(int(totals.get("excl_cents") or 0), currency), total_value),
        ],
        [
            Paragraph(vat_label, total_label),
            Paragraph(_money(int(totals.get("vat_cents") or 0), currency), total_value),
        ],
        [
            Paragraph("Total due (incl. VAT)", grand_label),
            Paragraph(_money(int(totals.get("incl_cents") or 0), currency), grand_value),
        ],
    ]
    totals_table = Table(totals_data, colWidths=[content_w * 0.68, content_w * 0.32])
    totals_table.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
                ("TOPPADDING", (0, 0), (-1, -2), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -2), 3),
                ("TOPPADDING", (0, -1), (-1, -1), 8),
                ("BOTTOMPADDING", (0, -1), (-1, -1), 4),
                ("LINEABOVE", (0, -1), (-1, -1), 1, accent),
                ("BACKGROUND", (0, -1), (-1, -1), accent_soft),
                ("LEFTPADDING", (0, -1), (-1, -1), 8),
                ("RIGHTPADDING", (0, -1), (-1, -1), 8),
            ]
        )
    )
    story.append(totals_table)
    story.append(Spacer(1, 20))

    # —— License key panel ——
    lic_inner = Table(
        [
            [Paragraph("LICENCE KEY", license_label)],
            [Paragraph(invoice.get("license_key") or "—", license_key)],
            [
                Paragraph(
                    "Keep this key secure. It activates your Rugby AI Predictor subscription.",
                    ParagraphStyle(
                        "LicHint",
                        parent=foot,
                        alignment=TA_CENTER,
                        fontSize=7.5,
                    ),
                )
            ],
        ],
        colWidths=[content_w - 24],
    )
    lic_inner.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    lic_wrap = Table([[lic_inner]], colWidths=[content_w])
    lic_wrap.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.75, line),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FAFAFA")),
                ("TOPPADDING", (0, 0), (-1, -1), 14),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ]
        )
    )
    story.append(lic_wrap)
    story.append(Spacer(1, 22))

    # —— Footer notes ——
    story.append(HRFlowable(width="100%", thickness=0.5, color=line, spaceBefore=0, spaceAfter=8))
    story.append(
        Paragraph(
            invoice.get("retention_note")
            or "Please retain this tax invoice for your records (SARS: keep for at least five years).",
            foot,
        )
    )
    story.append(
        Paragraph(
            "This document is a tax invoice for the purposes of the Value-Added Tax Act 89 of 1991 (Section 20).",
            foot,
        )
    )
    if sandbox:
        story.append(Spacer(1, 4))
        story.append(
            Paragraph(
                "Issued in test mode for pipeline verification — not a live settlement.",
                ParagraphStyle(
                    "SandboxFoot",
                    parent=foot,
                    textColor=colors.HexColor("#9CA3AF"),
                    fontSize=7,
                ),
            )
        )

    def _chrome(canvas, _doc):
        canvas.saveState()
        # Top accent bar
        canvas.setFillColor(accent)
        canvas.rect(0, page_h - 4.5, page_w, 4.5, fill=1, stroke=0)
        # Footer page mark
        canvas.setFillColor(muted)
        canvas.setFont("Helvetica", 7)
        canvas.drawString(margin_x, 10 * mm, str(invoice.get("invoice_number") or ""))
        canvas.drawRightString(
            page_w - margin_x,
            10 * mm,
            (supplier.get("trading_name") or supplier.get("legal_name") or "Rugby AI Predictor"),
        )
        canvas.restoreState()

    doc.build(story, onFirstPage=_chrome, onLaterPages=_chrome)
    return buffer.getvalue()


def build_invoice_pdf_base64(invoice: Dict[str, Any]) -> str:
    return base64.b64encode(build_invoice_pdf_bytes(invoice)).decode("ascii")
