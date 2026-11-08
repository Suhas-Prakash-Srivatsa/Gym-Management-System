"""Rupees that add up: every monetary value in the system is a Decimal."""

import re
from decimal import ROUND_HALF_UP, Decimal

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
