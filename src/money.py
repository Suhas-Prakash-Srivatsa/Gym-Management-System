"""Rupees that add up: every monetary value in the system is a Decimal."""

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

# \d deliberately accepts any Unicode decimal digit ("١٢"): Decimal parses them
# correctly and every amount is written back in ASCII digits.
_NUMBER = re.compile(r"\d+(\.\d+)?")
_TWO_PLACES = Decimal("0.01")


def parse_money(raw: str) -> Decimal:
    """Parse a human-typed rupee amount such as "₹12,000" or " 9500 ".

    Raises ValueError for negatives and anything non-numeric.
    """
    cleaned = raw.replace("₹", "").replace(",", "").replace(" ", "").strip()
    if cleaned.startswith("-"):
        raise ValueError(f"Amount cannot be negative: {raw!r}")
    if not _NUMBER.fullmatch(cleaned):
        raise ValueError(f"Not a valid amount: {raw!r}")
    return Decimal(cleaned)


def quantize(d: Decimal) -> Decimal:
    """Round to two decimal places, half up."""
    return d.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)


def is_whole_paise(amount: Decimal) -> bool:
    """Finite, and exactly representable in rupees and paise.

    Never raises: `quantize` signals InvalidOperation for amounts beyond the
    Decimal context's 28 digits (1E+30), and those are simply not money.
    """
    if not amount.is_finite():
        return False
    try:
        return quantize(amount) == amount
    except InvalidOperation:
        return False


def format_money(d: Decimal) -> str:
    """Render rupees the Indian way: `₹97,300`, `₹2,35,400`, `₹1,23,45,678.90`.

    Rounded half up to the paisa; paise shown only when there are any. Indian
    grouping: the last three digits, then pairs (thousand, lakh, crore). The
    one formatter, shared by recording messages and the dashboard views.
    """
    rupees, paise = f"{quantize(d):.2f}".split(".")
    sign, digits = ("-", rupees[1:]) if rupees.startswith("-") else ("", rupees)
    head, tail = digits[:-3], digits[-3:]
    pairs = []
    while head:
        head, pairs = head[:-2], [head[-2:], *pairs]
    grouped = ",".join([*pairs, tail])
    return f"{sign}₹{grouped}" + ("" if paise == "00" else f".{paise}")
