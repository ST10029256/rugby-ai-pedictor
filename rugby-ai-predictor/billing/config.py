"""Billing config for sandbox and (later) live Mode.

PAYMENT_MODE=sandbox means no real money moves. Swap to live + Xero adapter later.
"""

from __future__ import annotations

import os
from typing import Any, Dict

# sandbox | live
PAYMENT_MODE = (os.getenv("PAYMENT_MODE") or "sandbox").strip().lower()

# SA VAT rate. Set VAT_REGISTERED=false if you are not yet a vendor — invoices still
# look real but omit VAT number and show "VAT not charged" wording.
VAT_RATE = float(os.getenv("VAT_RATE") or "0.15")
VAT_REGISTERED = (os.getenv("VAT_REGISTERED") or "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "y",
}

SUPPLIER: Dict[str, Any] = {
    "legal_name": os.getenv("BILLING_LEGAL_NAME") or "Rugby AI Predictor (Pty) Ltd",
    "trading_name": os.getenv("BILLING_TRADING_NAME") or "Rugby AI Predictor",
    "address_lines": [
        os.getenv("BILLING_ADDRESS_LINE1") or "1 Test Sandbox Street",
        os.getenv("BILLING_ADDRESS_LINE2") or "Cape Town, 8001",
        os.getenv("BILLING_COUNTRY") or "South Africa",
    ],
    "email": os.getenv("BILLING_EMAIL") or "billing@rugbyaipredictor.test",
    "phone": os.getenv("BILLING_PHONE") or "+27 21 000 0000",
    "vat_number": os.getenv("BILLING_VAT_NUMBER") or "4123456789",
    "company_reg": os.getenv("BILLING_COMPANY_REG") or "2024/000000/07",
}

CURRENCY = "ZAR"

# Amounts are VAT-inclusive ZAR (what the customer pays at checkout).
PLANS: Dict[str, Dict[str, Any]] = {
    "monthly": {
        "id": "monthly",
        "name": "Monthly",
        "description": "Rugby AI Predictor – Monthly subscription",
        "duration_days": 30,
        "amount_incl_vat_cents": 49900,  # R499.00
        "period_label": "per month",
        "features": [
            "Full access to all predictions",
            "AI-powered match analysis",
            "Real-time updates",
            "All leagues included",
            "Email support",
        ],
    },
    "6months": {
        "id": "6months",
        "name": "6 Months",
        "description": "Rugby AI Predictor – 6 Month subscription",
        "duration_days": 180,
        "amount_incl_vat_cents": 249900,  # R2,499.00
        "period_label": "Save vs monthly",
        "featured": True,
        "features": [
            "Everything in Monthly",
            "6 months of predictions",
            "Priority support",
            "Advanced analytics",
            "Best value option",
        ],
    },
    "yearly": {
        "id": "yearly",
        "name": "Annual",
        "description": "Rugby AI Predictor – Annual subscription",
        "duration_days": 365,
        "amount_incl_vat_cents": 419900,  # R4,199.00
        "period_label": "Maximum savings",
        "features": [
            "Everything in 6 Months",
            "Full year of access",
            "Premium support",
            "Early access to features",
            "Maximum savings",
        ],
    },
}

# Stripe/Paystack-style sandbox cards (no real charge).
TEST_CARDS = {
    "4242424242424242": {"result": "success", "brand": "visa", "label": "Visa success"},
    "4000000000000002": {"result": "declined", "brand": "visa", "label": "Generic decline"},
    "4000000000009995": {
        "result": "insufficient_funds",
        "brand": "visa",
        "label": "Insufficient funds",
    },
    "5555555555554444": {
        "result": "success",
        "brand": "mastercard",
        "label": "Mastercard success",
    },
}


def public_plans() -> list[Dict[str, Any]]:
    """Plans shaped for the frontend pricing page."""
    out = []
    for plan in PLANS.values():
        cents = int(plan["amount_incl_vat_cents"])
        out.append(
            {
                "id": plan["id"],
                "name": plan["name"],
                "duration": f"{plan['duration_days']} days access"
                if plan["duration_days"] != 365
                else "1 Year Access",
                "price_cents": cents,
                "price_display": f"R{(cents / 100):,.2f}".replace(".00", ""),
                "period": plan["period_label"],
                "durationDays": plan["duration_days"],
                "featured": bool(plan.get("featured")),
                "features": list(plan["features"]),
                "currency": CURRENCY,
            }
        )
    # nicer duration labels
    for item in out:
        if item["id"] == "monthly":
            item["duration"] = "1 Month Access"
        elif item["id"] == "6months":
            item["duration"] = "6 Months Access"
    return out


def split_vat(amount_incl_vat_cents: int) -> Dict[str, int]:
    """Split VAT-inclusive cents into excl + VAT + incl."""
    incl = int(amount_incl_vat_cents)
    if not VAT_REGISTERED or VAT_RATE <= 0:
        return {"excl_cents": incl, "vat_cents": 0, "incl_cents": incl}
    excl = int(round(incl / (1.0 + VAT_RATE)))
    vat = incl - excl
    return {"excl_cents": excl, "vat_cents": vat, "incl_cents": incl}
