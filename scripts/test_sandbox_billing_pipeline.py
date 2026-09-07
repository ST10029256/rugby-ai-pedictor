"""
Local sandbox billing smoke test (no Firebase, no real money).

Usage:
  python scripts/test_sandbox_billing_pipeline.py
"""

from __future__ import annotations

import base64
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "rugby-ai-predictor"))

from billing.config import PLANS, split_vat  # noqa: E402
from billing.invoice_pdf import build_invoice_pdf_bytes  # noqa: E402
from billing.payment_provider import process_apple_pay, process_card_payment  # noqa: E402


def main() -> int:
    out_dir = ROOT / "artifacts" / "sandbox_invoices"
    out_dir.mkdir(parents=True, exist_ok=True)

    ok = process_card_payment(
        amount_cents=49900,
        currency="ZAR",
        card_number="4242424242424242",
        exp_month="12",
        exp_year="30",
        cvc="123",
        cardholder_name="Test User",
    )
    assert ok["ok"], ok
    print("card success:", ok["payment_id"], ok["last4"])

    declined = process_card_payment(
        amount_cents=49900,
        currency="ZAR",
        card_number="4000000000000002",
        exp_month="12",
        exp_year="30",
        cvc="123",
        cardholder_name="Test User",
    )
    assert not declined["ok"], declined
    print("card decline ok:", declined["code"])

    apple = process_apple_pay(amount_cents=249900, currency="ZAR", wallet_email="test@example.com")
    assert apple["ok"], apple
    print("apple pay success:", apple["payment_id"])

    plan = PLANS["monthly"]
    amounts = split_vat(plan["amount_incl_vat_cents"])
    invoice = {
        "invoice_number": "INV-2026-000001",
        "document_title": "Tax Invoice",
        "status": "paid",
        "sandbox": True,
        "currency": "ZAR",
        "issued_at_iso": datetime.now(timezone.utc).isoformat(),
        "supply_date": datetime.now(timezone.utc).date().isoformat(),
        "supplier": {
            "legal_name": "Rugby AI Predictor (Pty) Ltd",
            "trading_name": "Rugby AI Predictor",
            "address_lines": ["1 Test Sandbox Street", "Cape Town, 8001", "South Africa"],
            "email": "billing@rugbyaipredictor.test",
            "phone": "+27 21 000 0000",
            "vat_number": "4123456789",
            "company_reg": "2024/000000/07",
            "vat_registered": True,
            "vat_rate": 0.15,
        },
        "customer": {
            "name": "Test Customer",
            "email": "customer@example.com",
            "address": "12 Long Street, Cape Town",
        },
        "line_items": [
            {
                "description": plan["description"],
                "quantity": 1,
                "unit_excl_cents": amounts["excl_cents"],
                "line_excl_cents": amounts["excl_cents"],
                "vat_cents": amounts["vat_cents"],
                "line_incl_cents": amounts["incl_cents"],
            }
        ],
        "totals": amounts,
        "payment": {
            "payment_id": ok["payment_id"],
            "provider": "sandbox_card",
            "method": "card",
            "brand": "visa",
            "last4": "4242",
            "status": "succeeded",
        },
        "license_key": "TEST-KEY1-KEY2-KEY3",
        "retention_note": "Retain for SARS audit (minimum 5 years).",
    }

    try:
        pdf = build_invoice_pdf_bytes(invoice)
    except ImportError:
        print("Installing reportlab is required: pip install reportlab")
        return 1

    pdf_path = out_dir / "sample_tax_invoice.pdf"
    pdf_path.write_bytes(pdf)
    print("wrote", pdf_path, f"({len(pdf)} bytes)")
    print("base64 prefix:", base64.b64encode(pdf).decode("ascii")[:40], "...")
    print("OK — sandbox payment + PDF pipeline smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
