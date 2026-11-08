"""The golden test: Book1.csv through the whole chain, at a frozen today.

sheet.read_rows -> validation.validate -> assemble.build_dataset -> with_ledger
(empty ledger) -> balances.all_statuses -> views.tiles / receivables_rows.

The four figures were calculated by hand from the fixture during design
(issue 13), never from this code. Any wrong boundary, sign or anchor between
the sheet reader and the views changes at least one of them.
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

from src.assemble import build_dataset, with_ledger
from src.balances import all_statuses
from src.ledger import read_payments
from src.sheet import read_rows
from src.validation import validate
from src.views import receivables_rows, tiles

BOOK1 = Path(__file__).resolve().parent.parent / "src" / "files" / "Book1.csv"
GOLDEN_TODAY = date(2026, 11, 8)


def _dashboard(today: date, tmp_path: Path):
    rows, columns = read_rows(BOOK1)
    report = validate(rows, columns)
    assert report.is_clean, report.issues
    ledger = read_payments(tmp_path / "payments.csv")  # no file yet: an empty ledger
    assert ledger == []
    merge = with_ledger(build_dataset(rows), ledger)
    assert merge.orphaned == () and merge.conflicting == ()
    statuses = all_statuses(merge.dataset, today)
    return tiles(statuses), receivables_rows(statuses)


def test_book1_at_8_november_owes_97300_of_which_60950_is_overdue(tmp_path):
    figures, rows = _dashboard(GOLDEN_TODAY, tmp_path)

    assert len(rows) == 19  # Memberships with Outstanding > 0
    assert sum(1 for r in rows if r["is_overdue"]) == 11
    assert figures["overdue_count"] == 11
    assert figures["total_receivable"] == Decimal("97300")
    assert figures["overdue"] == Decimal("60950")
    assert figures["display"]["Total Receivable"] == "₹97,300"
    assert figures["display"]["Overdue"] == "₹60,950"


def _rohit(rows):
    return next(r for r in rows if r["membership_id"] == "MS-011")


def test_rohit_desai_is_not_overdue_on_5_november(tmp_path):
    # Joined 2026-09-05, nothing paid: Next Due Date is 2026-11-05, and on
    # that day itself the grace has not yet passed.
    _, rows = _dashboard(date(2026, 11, 5), tmp_path)

    rohit = _rohit(rows)
    assert rohit["member_name"] == "Rohit Desai"
    assert rohit["next_due_date"] == date(2026, 11, 5)
    assert rohit["is_overdue"] is False
    assert rohit["status"] == ""


def test_rohit_desai_is_overdue_on_8_november(tmp_path):
    _, rows = _dashboard(GOLDEN_TODAY, tmp_path)

    rohit = _rohit(rows)
    assert rohit["is_overdue"] is True
    assert rohit["status"] == "DUE"
