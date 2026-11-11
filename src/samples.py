"""The built-in sheets (core; reads only its own src/files): the sample and the demo gym.

The sample sheet is what the upload screen offers to download: the exact
headers the tool reads, filled in so that it passes validation with nothing
to fix. The demo gym is a made-up members sheet for trying the dashboard
without a sheet of one's own. Both are ordinary sheets: every figure the
dashboard shows for them is computed from their rows, like any upload.
"""

import csv
import io
from datetime import date, timedelta
from pathlib import Path

from src.dates import parse_date
from src.models import RawRow
from src.sheet import HEADER_ALIASES, read_rows
from src.validation import COLUMN_LABELS, REQUIRED_COLUMNS

FILES = Path(__file__).resolve().parent / "files"
SAMPLE_FILE_NAME = "sample_members_sheet.csv"
DEMO_SOURCE = FILES / "demo_members.csv"
# The demo's dates are written as they look on this day; demo_sheet_csv moves
# them by however far today is from it, so the demo never goes stale.
DEMO_ANCHOR = date(2026, 11, 8)
_DATE_COLUMNS = ("date_joined", "last_payment_date")

SAMPLE_ROWS: tuple[RawRow, ...] = (
    {"member_id": "M001", "member_name": "Asha Kumar", "membership_id": "MS-001",
     "membership_type": "Yearly", "date_joined": "2025-01-10", "membership_amount": "12000",
     "instalments": "1", "paid_amount": "12000", "last_payment_date": "2025-01-10"},
    {"member_id": "M001", "member_name": "Asha Kumar", "membership_id": "MS-002",
     "membership_type": "Yearly", "date_joined": "2026-01-10", "membership_amount": "12000",
     "instalments": "2", "paid_amount": "6000", "last_payment_date": "2026-01-10"},
    {"member_id": "M002", "member_name": "Ravi Shankar", "membership_id": "MS-003",
     "membership_type": "Half-Yearly", "date_joined": "2026-04-01", "membership_amount": "9000",
     "instalments": "2", "paid_amount": "4500", "last_payment_date": "2026-04-01"},
    {"member_id": "M003", "member_name": "Neha Gupta", "membership_id": "MS-004",
     "membership_type": "Monthly", "date_joined": "2026-10-15", "membership_amount": "2000",
     "instalments": "1", "paid_amount": "0", "last_payment_date": ""},
)

# One line per column, for the sample sheet's guide on the upload screen.
_WHAT_IT_HOLDS = {
    "member_id": "The same ID on every row of the same person.",
    "member_name": "The member's name.",
    "membership_id": "One ID per membership. Left empty, the tool makes one.",
    "membership_type": "Monthly, Half-Yearly or Yearly.",
    "date_joined": "When the membership started, with a 4-digit year.",
    "membership_amount": "The full price for the whole period, e.g. 12000 or ₹12,000.",
    "instalments": "How many payments the price is split into. 1 = paid in one go.",
    "paid_amount": "What has been paid so far. 0 if nothing yet.",
    "last_payment_date": "When the last payment was made. Needed if anything was paid.",
}


def _csv_bytes(rows) -> bytes:
    """Rows as a CSV with the tool's own column names, in UTF-8 with a BOM for Excel."""
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(COLUMN_LABELS.values())
    for row in rows:
        writer.writerow([row.get(column) or "" for column in COLUMN_LABELS])
    return buffer.getvalue().encode("utf-8-sig")


def sample_sheet_csv() -> bytes:
    """The sample sheet to download: uploaded back as it is, it has nothing to fix."""
    return _csv_bytes(SAMPLE_ROWS)


def sample_preview() -> list[dict[str, str]]:
    """The sample's rows as the owner sees them in a spreadsheet, keyed by column name."""
    return [{label: row.get(column, "") for column, label in COLUMN_LABELS.items()}
            for row in SAMPLE_ROWS]


def column_guide() -> list[dict[str, str]]:
    """One row per column the tool reads: required or not, other names it accepts, what goes in."""
    def other_names(column: str) -> str:
        own = COLUMN_LABELS[column].casefold()
        return ", ".join(alias for alias, canonical in HEADER_ALIASES.items()
                         if canonical == column and alias != own)
    return [{
        "Column": label,
        "Required": "Yes" if column in REQUIRED_COLUMNS else "No",
        "Also accepted as": other_names(column),
        "What goes in it": _WHAT_IT_HOLDS[column],
    } for column, label in COLUMN_LABELS.items()]


def _shifted(raw: str, shift: timedelta) -> str:
    parsed = parse_date(raw)
    return (parsed + shift).isoformat() if parsed else raw


def demo_sheet_csv(today: date) -> bytes:
    """The demo gym's sheet as of `today`: every date moved by the days since DEMO_ANCHOR.

    On DEMO_ANCHOR itself it is src/files/demo_members.csv unchanged in
    content, so its figures can be checked by hand; on any other day members
    are just as late or early relative to today, so the demo always shows a
    realistic mix of overdue, owing and paid memberships.
    """
    shift = today - DEMO_ANCHOR
    rows, _ = read_rows(DEMO_SOURCE)
    return _csv_bytes({**row, **{c: _shifted(row.get(c) or "", shift) for c in _DATE_COLUMNS}}
                      for row in rows)
