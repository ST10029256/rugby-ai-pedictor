"""Sandbox accounting ledger (Option A stand-in for Xero/QuickBooks).

Invoices are the source of truth. Later swap create_tax_invoice() to call Xero API
while keeping the same return shape.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from google.cloud import firestore

from .config import (
    CURRENCY,
    PAYMENT_MODE,
    PLANS,
    SUPPLIER,
    VAT_RATE,
    VAT_REGISTERED,
    split_vat,
)

logger = logging.getLogger(__name__)


def _next_invoice_number(db) -> str:
    """Sequential INV-YYYY-###### using a Firestore counter (audit-friendly)."""
    year = datetime.now(timezone.utc).year
    counter_ref = db.collection("billing_meta").document("invoice_counter")

    @firestore.transactional
    def _bump(transaction):
        snap = counter_ref.get(transaction=transaction)
        data = snap.to_dict() if snap.exists else {}
        year_key = str(year)
        current = int((data.get("by_year") or {}).get(year_key) or 0) + 1
        by_year = dict(data.get("by_year") or {})
        by_year[year_key] = current
        transaction.set(
            counter_ref,
            {
                "by_year": by_year,
                "updated_at": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        )
        return current

    seq = _bump(db.transaction())
    return f"INV-{year}-{seq:06d}"


def create_tax_invoice(
    db,
    *,
    customer: Dict[str, Any],
    plan_id: str,
    payment: Dict[str, Any],
    license_key: str,
    subscription_id: str,
) -> Dict[str, Any]:
    """Create a SARS-oriented tax invoice in the ledger and return the record."""
    plan = PLANS.get(plan_id)
    if not plan:
        raise ValueError(f"Unknown plan: {plan_id}")

    amounts = split_vat(plan["amount_incl_vat_cents"])
    invoice_number = _next_invoice_number(db)
    issued_at = datetime.now(timezone.utc)

    invoice: Dict[str, Any] = {
        "invoice_number": invoice_number,
        "document_title": "Tax Invoice",
        "status": "paid",
        "sandbox": PAYMENT_MODE in {"sandbox", "test"},
        "currency": CURRENCY,
        "issued_at": issued_at,
        "issued_at_iso": issued_at.isoformat(),
        "supply_date": issued_at.date().isoformat(),
        "supplier": {
            **SUPPLIER,
            "vat_registered": VAT_REGISTERED,
            "vat_rate": VAT_RATE if VAT_REGISTERED else 0.0,
        },
        "customer": {
            "name": (customer.get("name") or "").strip(),
            "email": (customer.get("email") or "").strip().lower(),
            "address": (customer.get("address") or "").strip() or None,
            "vat_number": (customer.get("vat_number") or "").strip() or None,
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
        "totals": {
            "excl_cents": amounts["excl_cents"],
            "vat_cents": amounts["vat_cents"],
            "incl_cents": amounts["incl_cents"],
        },
        "payment": {
            "payment_id": payment.get("payment_id"),
            "provider": payment.get("provider"),
            "method": payment.get("method"),
            "brand": payment.get("brand"),
            "last4": payment.get("last4"),
            "status": payment.get("status"),
            "paid_at": payment.get("paid_at"),
        },
        "license_key": license_key,
        "subscription_id": subscription_id,
        "plan_id": plan_id,
        "plan_name": plan["name"],
        "duration_days": plan["duration_days"],
        "accounting_system": "sandbox_ledger",  # swap to "xero" later
        "retention_note": "Retain for SARS audit (minimum 5 years).",
        "created_at": firestore.SERVER_TIMESTAMP,
    }

    # Full tax invoice threshold fields when > R5,000 incl.
    if amounts["incl_cents"] > 500000:
        invoice["full_tax_invoice"] = True
    else:
        invoice["full_tax_invoice"] = False

    _, doc_ref = db.collection("invoices").add(invoice)
    invoice["id"] = doc_ref.id

    # Audit mirror for owner exports
    db.collection("billing_audit").add(
        {
            "type": "invoice_created",
            "invoice_id": doc_ref.id,
            "invoice_number": invoice_number,
            "payment_id": payment.get("payment_id"),
            "subscription_id": subscription_id,
            "email": invoice["customer"]["email"],
            "amount_incl_cents": amounts["incl_cents"],
            "currency": CURRENCY,
            "sandbox": invoice["sandbox"],
            "created_at": firestore.SERVER_TIMESTAMP,
        }
    )

    logger.info(
        "Ledger invoice %s created for %s (sandbox=%s)",
        invoice_number,
        invoice["customer"]["email"],
        invoice["sandbox"],
    )
    return invoice


def get_invoice(db, invoice_id: str) -> Optional[Dict[str, Any]]:
    doc = db.collection("invoices").document(invoice_id).get()
    if not doc.exists:
        return None
    data = doc.to_dict() or {}
    data["id"] = doc.id
    return data
