"""Demo payment gateway. Charges a card at checkout and refunds to the same account.

No live processor is called. Full card numbers are never stored.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

GATEWAY = "ResolveX Pay"
DEMO_CARD_NUMBER = "4242424242424242"
DECLINED_CARDS = {"4000000000000002", "4000000000009995"}


class PaymentError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def brand_for(number: str) -> str:
    if number.startswith("4"):
        return "Visa"
    if number.startswith(("51", "52", "53", "54", "55", "2")):
        return "Mastercard"
    if number.startswith(("34", "37")):
        return "Amex"
    return "Card"


def account_label(payment: dict | None) -> str:
    if not payment:
        return f"{GATEWAY} wallet"
    if payment.get("account"):
        return payment["account"]
    last4 = payment.get("last4")
    brand = payment.get("brand") or "Card"
    if last4:
        return f"{brand} ••{last4}"
    return f"{GATEWAY} wallet"


def _parse_expiry(expiry: str) -> tuple[int, int]:
    digits = _digits(expiry)
    if len(digits) == 4:
        month, year = int(digits[:2]), 2000 + int(digits[2:])
    elif len(digits) == 6:
        month, year = int(digits[:2]), int(digits[2:])
    else:
        raise PaymentError("Enter card expiry as MM/YY")
    if month < 1 or month > 12:
        raise PaymentError("Enter a valid expiry month")
    return month, year


def charge(holder: str, number: str, expiry: str, cvc: str, amount: float, currency: str = "LKR") -> dict:
    name = (holder or "").strip()
    if len(name) < 2:
        raise PaymentError("Enter the name on the card")
    pan = _digits(number)
    if len(pan) < 13 or len(pan) > 19:
        raise PaymentError("Enter a valid card number")
    if pan in DECLINED_CARDS:
        raise PaymentError("Payment declined by the demo gateway")
    month, year = _parse_expiry(expiry)
    now = datetime.now(timezone.utc)
    if (year, month) < (now.year, now.month):
        raise PaymentError("This demo card has expired")
    if not (3 <= len(_digits(cvc)) <= 4):
        raise PaymentError("Enter a valid CVC")
    if amount <= 0:
        raise PaymentError("Nothing to charge")

    last4 = pan[-4:]
    brand = brand_for(pan)
    payment_id = str(uuid.uuid4())
    charge_id = "chg_" + payment_id.replace("-", "")[:16]
    return {
        "gateway": GATEWAY,
        "payment_id": payment_id,
        "charge_id": charge_id,
        "status": "captured",
        "amount": round(float(amount), 2),
        "currency": currency,
        "brand": brand,
        "last4": last4,
        "holder": name,
        "account": f"{brand} ••{last4}",
        "method": "card",
        "captured_at": now.isoformat(),
        "mocked": True,
    }


def pending(amount: float, currency: str = "LKR") -> dict:
    return {
        "gateway": GATEWAY,
        "status": "pending",
        "amount": round(float(amount), 2),
        "currency": currency,
        "method": "card",
        "mocked": True,
    }


def is_captured(payment: dict | None) -> bool:
    return bool(payment) and payment.get("status") == "captured"


def charge_demo(amount: float, holder: str = "Demo Customer", currency: str = "LKR") -> dict:
    return charge(holder, DEMO_CARD_NUMBER, "12/28", "123", amount, currency)


def payment_from_order(order) -> dict | None:
    if isinstance(order, dict):
        items = order.get("items") or []
    else:
        items = getattr(order, "items", None) or []
    for item in items:
        payment = item.get("payment") if isinstance(item, dict) else None
        if payment:
            return payment
    return None


def refund_to_source(payment: dict | None, amount: float, currency: str = "LKR") -> dict:
    destination = account_label(payment)
    refund_id = "re_" + str(uuid.uuid4()).replace("-", "")[:16]
    return {
        "gateway": GATEWAY,
        "refund_id": refund_id,
        "payment_id": (payment or {}).get("payment_id"),
        "charge_id": (payment or {}).get("charge_id"),
        "status": "completed",
        "amount": round(float(amount), 2),
        "currency": currency,
        "brand": (payment or {}).get("brand"),
        "last4": (payment or {}).get("last4"),
        "destination": destination,
        "account": destination,
        "mocked": True,
        "processed_at": datetime.now(timezone.utc).isoformat(),
    }
