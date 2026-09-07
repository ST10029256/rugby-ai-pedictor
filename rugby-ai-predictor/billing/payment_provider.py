"""Sandbox payment provider — same shape as Paystack/Stripe webhooks later."""

from __future__ import annotations

import secrets
import time
from typing import Any, Dict, Optional

from .config import PAYMENT_MODE, TEST_CARDS


def _digits_only(value: str) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


def _luhn_ok(card_number: str) -> bool:
    digits = [int(d) for d in card_number]
    if len(digits) < 13:
        return False
    checksum = 0
    parity = len(digits) % 2
    for i, d in enumerate(digits):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


def process_card_payment(
    *,
    amount_cents: int,
    currency: str,
    card_number: str,
    exp_month: str,
    exp_year: str,
    cvc: str,
    cardholder_name: str,
) -> Dict[str, Any]:
    """Simulate a card charge. Never talks to a real gateway in sandbox mode."""
    if PAYMENT_MODE not in {"sandbox", "test"}:
        return {
            "ok": False,
            "error": "Live payments are not enabled yet. Keep PAYMENT_MODE=sandbox.",
            "code": "live_disabled",
        }

    number = _digits_only(card_number)
    exp_m = _digits_only(exp_month)
    exp_y = _digits_only(exp_year)
    cvc_digits = _digits_only(cvc)

    if len(number) < 13 or len(number) > 19:
        return {"ok": False, "error": "Invalid card number", "code": "invalid_number"}
    if not _luhn_ok(number):
        return {"ok": False, "error": "Invalid card number", "code": "invalid_number"}
    if not exp_m or not exp_y or int(exp_m) < 1 or int(exp_m) > 12:
        return {"ok": False, "error": "Invalid expiry date", "code": "invalid_expiry"}
    if len(cvc_digits) < 3 or len(cvc_digits) > 4:
        return {"ok": False, "error": "Invalid CVC", "code": "invalid_cvc"}
    if not (cardholder_name or "").strip():
        return {"ok": False, "error": "Cardholder name required", "code": "invalid_name"}

    preset = TEST_CARDS.get(number)
    if preset is None:
        return {
            "ok": False,
            "error": (
                "Use a sandbox test card (e.g. 4242 4242 4242 4242). "
                "No real cards are accepted in test mode."
            ),
            "code": "unknown_test_card",
        }

    payment_id = f"pay_test_{secrets.token_hex(8)}"
    brand = preset.get("brand", "card")

    if preset["result"] != "success":
        return {
            "ok": False,
            "error": {
                "declined": "Your card was declined.",
                "insufficient_funds": "Insufficient funds.",
            }.get(preset["result"], "Payment failed."),
            "code": preset["result"],
            "payment_id": payment_id,
            "brand": brand,
        }

    return {
        "ok": True,
        "payment_id": payment_id,
        "provider": "sandbox_card",
        "method": "card",
        "brand": brand,
        "last4": number[-4:],
        "amount_cents": int(amount_cents),
        "currency": currency,
        "status": "succeeded",
        "paid_at": int(time.time()),
        "sandbox": True,
        "cardholder_name": cardholder_name.strip(),
    }


def process_apple_pay(
    *,
    amount_cents: int,
    currency: str,
    wallet_email: Optional[str] = None,
) -> Dict[str, Any]:
    """Simulate Apple Pay confirmation (Face ID / Touch ID already done in UI)."""
    if PAYMENT_MODE not in {"sandbox", "test"}:
        return {
            "ok": False,
            "error": "Live Apple Pay is not enabled yet.",
            "code": "live_disabled",
        }

    payment_id = f"pay_apple_test_{secrets.token_hex(8)}"
    return {
        "ok": True,
        "payment_id": payment_id,
        "provider": "sandbox_apple_pay",
        "method": "apple_pay",
        "brand": "apple_pay",
        "last4": "0000",
        "amount_cents": int(amount_cents),
        "currency": currency,
        "status": "succeeded",
        "paid_at": int(time.time()),
        "sandbox": True,
        "wallet_email": (wallet_email or "").strip().lower() or None,
    }
