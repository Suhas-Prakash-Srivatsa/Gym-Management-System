"""Tester's independent checks on the golden chain (ticket 13).

Per-Membership values hand-calculated from src/files/Book1.csv at 2026-11-08,
with an empty ledger: Outstanding = Membership Amount - Paid Amount; Next Due
Date = (Last Payment Date, or Date Joined if nothing paid) + 2 calendar months;
Overdue when today is after it and money is owed.
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from src.assemble import build_dataset, with_ledger
from src.balances import all_statuses
from src.sheet import read_rows
from src.validation import validate
from src.views import receivables_rows

BOOK1 = Path(__file__).resolve().parent.parent / "src" / "files" / "Book1.csv"

# membership_id: (outstanding, next_due, last_payment, overdue on 2026-11-08)
HAND = {
    "MS-001": (6000, date(2026, 8, 1), date(2026, 6, 1), True),
    "MS-002": (16000, date(2026, 10, 5), date(2026, 8, 5), True),
    "MS-003": (4500, date(2026, 12, 1), date(2026, 10, 1), False),
    "MS-007": (2200, date(2026, 12, 25), None, False),
    "MS-011": (2000, date(2026, 11, 5), None, True),
    "MS-014": (8000, date(2026, 11, 18), date(2026, 9, 18), False),
    "MS-015": (2100, date(2026, 10, 1), None, True),
    "MS-020": (4500, date(2026, 4, 20), date(2026, 2, 20), True),
    "MS-021": (6000, date(2026, 11, 1), date(2026, 9, 1), True),
    "MS-022": (2000, date(2027, 1, 5), None, False),
    "MS-026": (6000, date(2027, 1, 1), date(2026, 11, 1), False),
}
OVERDUE_IDS = {"MS-001", "MS-002", "MS-006", "MS-008", "MS-010", "MS-011",
               "MS-015", "MS-017", "MS-020", "MS-021", "MS-024"}
SETTLED_IDS = {"MS-004", "MS-005", "MS-009", "MS-013", "MS-016", "MS-023", "MS-025"}


def _rows(today):
    rows, columns = read_rows(BOOK1)
    assert validate(rows, columns).is_clean
    merge = with_ledger(build_dataset(rows), [])
    return {r["membership_id"]: r for r in receivables_rows(all_statuses(merge.dataset, today),
                                                             show_fully_paid=True)}


@pytest.mark.parametrize("ms_id", sorted(HAND))
def test_hand_checked_membership(ms_id):
    row = _rows(date(2026, 11, 8))[ms_id]
    outstanding, next_due, last_paid, overdue = HAND[ms_id]
    assert row["outstanding"] == Decimal(outstanding)
    assert row["next_due_date"] == next_due
    assert row["last_payment_date"] == last_paid
    assert row["is_overdue"] is overdue


def test_exact_overdue_and_settled_sets():
    rows = _rows(date(2026, 11, 8))
    assert {i for i, r in rows.items() if r["is_overdue"]} == OVERDUE_IDS
    assert {i for i, r in rows.items() if r["outstanding"] == 0} == SETTLED_IDS
    assert all(r["status"] == "Paid" for i, r in rows.items() if i in SETTLED_IDS)


def test_most_overdue_first():
    owing = [r["membership_id"] for r in _rows(date(2026, 11, 8)).values() if r["outstanding"] > 0]
    assert owing[:3] == ["MS-020", "MS-001", "MS-010"]  # due 04-20, 08-01, 08-10


def test_unpaid_member_has_no_last_payment_date():
    # A ₹0 Paid Amount is not a Payment: no date, so the grace runs from Date Joined.
    rohit = _rows(date(2026, 11, 8))["MS-011"]
    assert rohit["paid"] == Decimal("0") and rohit["last_payment_date"] is None
    assert rohit["display"]["Last Payment Date"] == "—"
