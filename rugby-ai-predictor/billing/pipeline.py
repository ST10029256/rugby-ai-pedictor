"""End-to-end sandbox checkout: pay → ledger invoice → license → email PDF."""

from __future__ import annotations

import logging
import secrets
import string
from datetime import datetime, timedelta, timezone
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, Optional

from google.cloud import firestore

from .config import CURRENCY, PAYMENT_MODE, PLANS, public_plans
from .invoice_pdf import build_invoice_pdf_base64, build_invoice_pdf_bytes
from .ledger import create_tax_invoice, get_invoice
from .payment_provider import process_apple_pay, process_card_payment

logger = logging.getLogger(__name__)


def _generate_license_key() -> str:
    alphabet = string.ascii_uppercase + string.digits
    parts = ["".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(4)]
    return "-".join(parts)


def _money(cents: int) -> str:
    return f"R{(cents / 100):,.2f}"


def _send_purchase_email(
    *,
    email: str,
    name: str,
    license_key: str,
    plan_name: str,
    duration_days: int,
    expires_at: datetime,
    invoice: Dict[str, Any],
    pdf_bytes: bytes,
    gmail_credentials_fn,
) -> Dict[str, Any]:
    """Send license + tax invoice PDF. Uses same Gmail secrets as license emails."""
    try:
        gmail_user, gmail_password = gmail_credentials_fn()
    except Exception as exc:
        return {"success": False, "error": f"Credentials error: {exc}"}

    if not gmail_user or not gmail_password:
        return {
            "success": False,
            "error": "Gmail credentials not configured (email skipped in sandbox UI still works).",
        }

    try:
        import smtplib

        expires_str = expires_at.strftime("%B %d, %Y")
        invoice_number = invoice.get("invoice_number")
        totals = invoice.get("totals") or {}
        sandbox = bool(invoice.get("sandbox"))

        msg = MIMEMultipart("mixed")
        subject_prefix = "[SANDBOX] " if sandbox else ""
        msg["Subject"] = (
            f"{subject_prefix}Your Rugby AI license + tax invoice {invoice_number}"
        )
        msg["From"] = f"Rugby AI Predictor <{gmail_user}>"
        msg["To"] = email
        msg["Reply-To"] = gmail_user

        html = f"""
        <html><body style="font-family:Arial,sans-serif;color:#0f172a;line-height:1.5">
          <div style="max-width:640px;margin:0 auto;padding:20px">
            {"<p style='background:#fff7ed;border:1px solid #fdba74;padding:10px;border-radius:8px'><b>Sandbox test</b> — no real payment was taken.</p>" if sandbox else ""}
            <h2 style="color:#15803d">Payment successful</h2>
            <p>Hi {name},</p>
            <p>Your <b>{plan_name}</b> subscription is active. Your tax invoice
            <b>{invoice_number}</b> is attached (PDF).</p>
            <div style="background:#f8fafc;border:2px solid #22c55e;border-radius:8px;padding:16px;text-align:center;margin:20px 0">
              <div style="font-size:12px;color:#64748b;text-transform:uppercase;letter-spacing:1px">License key</div>
              <div style="font-size:22px;font-weight:700;letter-spacing:2px;font-family:monospace;color:#15803d;margin-top:8px">{license_key}</div>
            </div>
            <ul>
              <li>Plan: {plan_name}</li>
              <li>Duration: {duration_days} days</li>
              <li>Expires: {expires_str}</li>
              <li>Amount paid: {_money(int(totals.get('incl_cents') or 0))}</li>
              <li>Invoice: {invoice_number}</li>
            </ul>
            <p>Keep the attached tax invoice for your records (and ours for SARS audits).</p>
            <p style="color:#64748b;font-size:13px">Rugby AI Predictor</p>
          </div>
        </body></html>
        """
        alt = MIMEMultipart("alternative")
        alt.attach(
            MIMEText(
                f"License key: {license_key}\nInvoice: {invoice_number}\nExpires: {expires_str}\n",
                "plain",
            )
        )
        alt.attach(MIMEText(html, "html"))
        msg.attach(alt)

        attachment = MIMEApplication(pdf_bytes, _subtype="pdf")
        attachment.add_header(
            "Content-Disposition",
            "attachment",
            filename=f"{invoice_number}.pdf",
        )
        msg.attach(attachment)

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(gmail_user, gmail_password)
            server.send_message(msg)

        return {"success": True}
    except Exception as exc:
        logger.exception("Purchase email failed")
        return {"success": False, "error": str(exc)}


def process_sandbox_checkout(
    db,
    *,
    email: str,
    name: str,
    plan_id: str,
    payment_method: str,
    card: Optional[Dict[str, Any]] = None,
    customer_address: Optional[str] = None,
    customer_vat_number: Optional[str] = None,
    gmail_credentials_fn=None,
) -> Dict[str, Any]:
    """Full Option A pipeline in sandbox mode."""
    if PAYMENT_MODE not in {"sandbox", "test"}:
        return {
            "error": "Live mode is locked. Set PAYMENT_MODE=sandbox to test.",
            "code": "live_disabled",
        }

    email = (email or "").strip().lower()
    name = (name or "").strip()
    plan_id = (plan_id or "").strip()
    payment_method = (payment_method or "card").strip().lower()

    if not email or "@" not in email:
        return {"error": "Valid email is required", "code": "invalid_email"}
    if not name:
        return {"error": "Full name is required", "code": "invalid_name"}

    plan = PLANS.get(plan_id)
    if not plan:
        return {"error": "Unknown plan", "code": "invalid_plan"}

    amount_cents = int(plan["amount_incl_vat_cents"])

    if payment_method == "apple_pay":
        payment = process_apple_pay(
            amount_cents=amount_cents,
            currency=CURRENCY,
            wallet_email=email,
        )
    elif payment_method == "card":
        card = card or {}
        payment = process_card_payment(
            amount_cents=amount_cents,
            currency=CURRENCY,
            card_number=str(card.get("number") or ""),
            exp_month=str(card.get("exp_month") or ""),
            exp_year=str(card.get("exp_year") or ""),
            cvc=str(card.get("cvc") or ""),
            cardholder_name=str(card.get("name") or name),
        )
    else:
        return {"error": "Unsupported payment method", "code": "invalid_method"}

    if not payment.get("ok"):
        return {
            "error": payment.get("error") or "Payment failed",
            "code": payment.get("code") or "payment_failed",
            "payment_id": payment.get("payment_id"),
        }

    # Idempotency: same payment_id should not mint two licenses
    existing = list(
        db.collection("subscriptions")
        .where("payment_id", "==", payment["payment_id"])
        .limit(1)
        .stream()
    )
    if existing:
        sub = existing[0].to_dict() or {}
        invoice_id = sub.get("invoice_id")
        invoice = get_invoice(db, invoice_id) if invoice_id else None
        pdf_b64 = build_invoice_pdf_base64(invoice) if invoice else None
        return {
            "ok": True,
            "idempotent": True,
            "license_key": sub.get("license_key"),
            "subscription_id": existing[0].id,
            "invoice_id": invoice_id,
            "invoice_number": (invoice or {}).get("invoice_number"),
            "invoice": _public_invoice(invoice) if invoice else None,
            "invoice_pdf_base64": pdf_b64,
            "email_sent": False,
            "sandbox": True,
            "message": "Payment already processed.",
        }

    license_key = _generate_license_key()
    duration_days = int(plan["duration_days"])
    expires_at = datetime.now(timezone.utc) + timedelta(days=duration_days)

    subscription_data = {
        "license_key": license_key,
        "email": email,
        "name": name,
        "subscription_type": plan_id,
        "duration_days": duration_days,
        "amount": amount_cents / 100.0,
        "amount_cents": amount_cents,
        "currency": CURRENCY,
        "created_at": firestore.SERVER_TIMESTAMP,
        "expires_at": expires_at,
        "used": False,
        "reusable": True,
        "active": True,
        "payment_completed": True,
        "payment_date": firestore.SERVER_TIMESTAMP,
        "payment_id": payment["payment_id"],
        "payment_provider": payment.get("provider"),
        "payment_method": payment.get("method"),
        "sandbox": True,
    }
    _, sub_ref = db.collection("subscriptions").add(subscription_data)
    subscription_id = sub_ref.id

    invoice = create_tax_invoice(
        db,
        customer={
            "name": name,
            "email": email,
            "address": customer_address,
            "vat_number": customer_vat_number,
        },
        plan_id=plan_id,
        payment=payment,
        license_key=license_key,
        subscription_id=subscription_id,
    )

    pdf_bytes = build_invoice_pdf_bytes(invoice)
    pdf_b64 = build_invoice_pdf_base64(invoice)

    # Link invoice back onto subscription
    db.collection("subscriptions").document(subscription_id).update(
        {
            "invoice_id": invoice["id"],
            "invoice_number": invoice["invoice_number"],
        }
    )

    # Persist PDF bytes pointer-free: store base64 for audit retrieval in sandbox
    db.collection("invoices").document(invoice["id"]).update(
        {
            "pdf_base64": pdf_b64,
            "pdf_generated_at": firestore.SERVER_TIMESTAMP,
        }
    )

    email_result = {"success": False, "error": "Email helper not provided"}
    if gmail_credentials_fn:
        email_result = _send_purchase_email(
            email=email,
            name=name,
            license_key=license_key,
            plan_name=plan["name"],
            duration_days=duration_days,
            expires_at=expires_at,
            invoice=invoice,
            pdf_bytes=pdf_bytes,
            gmail_credentials_fn=gmail_credentials_fn,
        )

    return {
        "ok": True,
        "sandbox": True,
        "license_key": license_key,
        "expires_at": expires_at.timestamp(),
        "subscription_id": subscription_id,
        "invoice_id": invoice["id"],
        "invoice_number": invoice["invoice_number"],
        "invoice": _public_invoice(invoice),
        "invoice_pdf_base64": pdf_b64,
        "payment": {
            "payment_id": payment["payment_id"],
            "method": payment.get("method"),
            "brand": payment.get("brand"),
            "last4": payment.get("last4"),
            "amount_cents": amount_cents,
            "currency": CURRENCY,
        },
        "email_sent": bool(email_result.get("success")),
        "email_error": email_result.get("error"),
        "test_cards_hint": [
            "4242 4242 4242 4242 → success",
            "4000 0000 0000 0002 → declined",
            "4000 0000 0000 9995 → insufficient funds",
        ],
    }


def _public_invoice(invoice: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not invoice:
        return None
    # Strip bulky pdf from nested public payload (returned separately)
    return {
        "id": invoice.get("id"),
        "invoice_number": invoice.get("invoice_number"),
        "document_title": invoice.get("document_title"),
        "status": invoice.get("status"),
        "sandbox": invoice.get("sandbox"),
        "currency": invoice.get("currency"),
        "issued_at_iso": invoice.get("issued_at_iso"),
        "supply_date": invoice.get("supply_date"),
        "supplier": invoice.get("supplier"),
        "customer": invoice.get("customer"),
        "line_items": invoice.get("line_items"),
        "totals": invoice.get("totals"),
        "payment": invoice.get("payment"),
        "license_key": invoice.get("license_key"),
        "plan_id": invoice.get("plan_id"),
        "plan_name": invoice.get("plan_name"),
        "duration_days": invoice.get("duration_days"),
        "full_tax_invoice": invoice.get("full_tax_invoice"),
        "accounting_system": invoice.get("accounting_system"),
        "retention_note": invoice.get("retention_note"),
    }


def get_invoice_record(db, invoice_id: str, *, include_pdf: bool = True) -> Dict[str, Any]:
    invoice = get_invoice(db, invoice_id)
    if not invoice:
        return {"error": "Invoice not found", "code": "not_found"}

    pdf_b64 = invoice.get("pdf_base64")
    if include_pdf and not pdf_b64:
        pdf_b64 = build_invoice_pdf_base64(invoice)

    return {
        "ok": True,
        "invoice": _public_invoice(invoice),
        "invoice_pdf_base64": pdf_b64 if include_pdf else None,
    }


def list_public_plans() -> Dict[str, Any]:
    return {
        "ok": True,
        "mode": PAYMENT_MODE,
        "currency": CURRENCY,
        "plans": public_plans(),
    }
