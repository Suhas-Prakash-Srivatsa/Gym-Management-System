"""The grace-period calendar: calendar-month arithmetic and date parsing."""

import calendar
import re
from datetime import date, datetime

_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d %B %Y", "%d %b %Y")
_ORDINAL = re.compile(r"(?<=\d)(st|nd|rd|th)\b", re.IGNORECASE)


def add_calendar_months(d: date, months: int) -> date:
    """Add whole calendar months, clamping to month end (31 Dec + 2 -> 28/29 Feb)."""
    index = d.month - 1 + months
    year, month = d.year + index // 12, index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def parse_date(raw: str) -> date | None:
    """Parse `2026-06-01`, `01/06/2026` or `1 June 2026`.

    Returns None for anything without a year (e.g. `1st June`) or otherwise
    unparseable; validation turns that into a question for the owner.
    """
    cleaned = " ".join(_ORDINAL.sub("", raw).split())
    for fmt in _FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None
