from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from src.assemble import LedgerMerge, build_dataset, with_ledger
from src.balances import all_statuses
from src.models import Dataset, Member, Membership, MembershipType, Payment
from src.sheet import read_rows
from src.validation import Issue, validate
from src.views import (
    ISSUE_COLUMNS,
    ROW_COLUMNS,
    TILE_LABELS,
    format_money,
    issue_rows,
    ledger_warnings,
    receivables_rows,
    tiles,
)

ROOT = Path(__file__).resolve().parent.parent
TODAY = date(2026, 11, 8)


@pytest.fixture(scope="module")
def statuses():
    """Book1.csv with an empty ledger, as the app sees it on first run."""
    rows, _ = read_rows(ROOT / "src" / "files" / "Book1.csv")
    return all_statuses(with_ledger(build_dataset(rows), []).dataset, TODAY)


# --- tiles ---


def test_tiles_match_the_hand_calculated_book1_figures(statuses):
    t = tiles(statuses)
    assert t["total_members"] == 24
    assert t["total_membership_value"] == Decimal("235400")
    assert t["total_receivable"] == Decimal("97300")
    assert t["overdue"] == Decimal("60950")
    assert t["overdue_count"] == 11


def test_tile_display_strings_are_ready_to_show_in_order(statuses):
    assert tiles(statuses)["display"] == {
        "Total Members": "24",
        "Total Membership Value": "₹2,35,400",
        "Total Receivable": "₹97,300",
        "Overdue": "₹60,950",
    }
    assert list(TILE_LABELS) == ["Total Members", "Total Membership Value",
                                 "Total Receivable", "Overdue"]


def test_there_is_no_due_this_month_tile(statuses):
    keys = " ".join(tiles(statuses)).lower() + " ".join(TILE_LABELS).lower()
    assert "month" not in keys


def test_tiles_of_nothing_are_zero():
    assert tiles([]) == {
        "total_members": 0, "total_membership_value": Decimal("0"),
        "total_receivable": Decimal("0"), "overdue": Decimal("0"), "overdue_count": 0,
        "display": {"Total Members": "0", "Total Membership Value": "₹0",
                    "Total Receivable": "₹0", "Overdue": "₹0"},
    }


# --- receivables_rows ---


def test_nineteen_rows_owe_money_worst_first(statuses):
    rows = receivables_rows(statuses)
    assert len(rows) == 19
    assert (rows[0]["member_name"], rows[0]["membership_id"], rows[0]["next_due_date"]) == (
        "Pooja Shetty", "MS-020", date(2026, 4, 20))
    assert (rows[-1]["member_name"], rows[-1]["membership_id"], rows[-1]["next_due_date"]) == (
        "Ritu Malhotra", "MS-022", date(2027, 1, 5))
    dues = [r["next_due_date"] for r in rows]
    assert dues == sorted(dues)
    assert all(r["outstanding"] > 0 for r in rows)


def test_exactly_eleven_rows_carry_the_due_tag(statuses):
    rows = receivables_rows(statuses)
    assert sum(r["status"] == "DUE" for r in rows) == 11
    assert all((r["status"] == "DUE") == r["is_overdue"] for r in rows)
    assert {r["status"] for r in rows} == {"DUE", ""}


def test_a_row_carries_every_dashboard_column_typed(statuses):
    row = next(r for r in receivables_rows(statuses) if r["membership_id"] == "MS-001")
    assert row == {
        "member_id": "M001",
        "member_name": "Suhas Prakash",
        "membership_id": "MS-001",
        "membership_type": "Yearly",
        "date_joined": date(2026, 6, 1),
        "contract_amount": Decimal("12000"),
        "paid": Decimal("6000"),
        "outstanding": Decimal("6000"),
        "last_payment_date": date(2026, 6, 1),
        "next_due_date": date(2026, 8, 1),
        "is_overdue": True,
        "status": "DUE",
        "display": {
            "Member Name": "Suhas Prakash",
            "Membership ID": "MS-001",
            "Membership Type": "Yearly",
            "Date Joined": "2026-06-01",
            "Contract Amount": "₹12,000",
            "Paid": "₹6,000",
            "Outstanding": "₹6,000",
            "Last Payment Date": "2026-06-01",
            "Next Due Date": "2026-08-01",
            "Status": "DUE",
        },
    }
    assert list(row["display"]) == list(ROW_COLUMNS)


def test_a_never_paid_membership_has_no_last_payment_date(statuses):
    row = next(r for r in receivables_rows(statuses) if r["membership_id"] == "MS-022")
    assert row["last_payment_date"] is None
    assert row["paid"] == Decimal("0")
    assert row["display"]["Last Payment Date"] == "—"
    assert row["display"]["Paid"] == "₹0"


def test_show_fully_paid_appends_the_seven_settled_rows_last(statuses):
    rows = receivables_rows(statuses, show_fully_paid=True)
    assert len(rows) == 26
    assert rows[:19] == receivables_rows(statuses)
    settled = rows[19:]
    assert len(settled) == 7
    assert all(r["outstanding"] == 0 and r["status"] == "Paid" and not r["is_overdue"]
               for r in settled)
    dues = [r["next_due_date"] for r in settled]
    assert dues == sorted(dues)
    assert settled[0]["membership_id"] == "MS-009"  # Manoj, settled, due 2026-03-05


def test_a_settled_row_shows_no_next_due_date(statuses):
    # Typed value kept (it orders the rows); on screen a due date means nothing once paid.
    settled = receivables_rows(statuses, show_fully_paid=True)[19:]
    assert all(r["next_due_date"] is not None for r in settled)
    assert {r["display"]["Next Due Date"] for r in settled} == {"—"}


def test_member_name_is_the_display_name_never_the_normalised_key():
    member = Member("suhas prakash", "Suhas Prakash")
    ms = Membership("suhas prakash-01", "suhas prakash", MembershipType.MONTHLY,
                    date(2026, 10, 1), Decimal("2000"), 1)
    [row] = receivables_rows(all_statuses(Dataset((member,), (ms,), ()), TODAY))
    assert row["member_name"] == "Suhas Prakash" and row["member_id"] == "suhas prakash"


def test_equal_next_due_dates_keep_sheet_order():
    member = Member("M1", "A")
    joined = date(2026, 10, 1)
    memberships = tuple(Membership(i, "M1", MembershipType.MONTHLY, joined, Decimal("100"), 1)
                        for i in ("MS-Z", "MS-A", "MS-M"))
    rows = receivables_rows(all_statuses(Dataset((member,), memberships, ()), TODAY))
    assert [r["membership_id"] for r in rows] == ["MS-Z", "MS-A", "MS-M"]


def test_paise_are_shown_when_present(statuses):
    member = Member("M1", "A")
    ms = Membership("MS-1", "M1", MembershipType.YEARLY, date(2026, 10, 1), Decimal("12000"), 2)
    paid = Payment("P-0001", "MS-1", Decimal("1000.50"), date(2026, 10, 2), "recorded",
                   datetime(2026, 10, 2))
    [row] = receivables_rows(all_statuses(Dataset((member,), (ms,), (paid,)), TODAY))
    assert row["display"]["Outstanding"] == "₹10,999.50"


def test_format_money_is_the_shared_one():
    from src import money

    assert format_money is money.format_money
    assert format_money(Decimal("97300")) == "₹97,300"


def test_views_are_pure():
    source = (ROOT / "src" / "views.py").read_text(encoding="utf-8")
    for forbidden in ("streamlit", "today()", "now()", "open(", "<span", "<div", "html", "color", "colour", "float"):
        assert forbidden not in source


# --- Issues and ledger problems, shaped for the screen ---



def test_issue_rows_name_the_row_column_and_offending_value():
    rows, columns = read_rows(ROOT / "src" / "files" / "Book1_errors.csv")
    report = validate(rows, columns)
    shown = issue_rows(report.issues, rows)
    assert len(shown) == 9
    first = next(r for r in shown if r["code"] == "date_missing_year")
    assert first["display"] == {
        "Row": "1", "Column": "Date Joined", "Value": "1st June",
        "Problem": "Row 1: Date Joined '1st June' has no year.",
    }
    assert list(first["display"]) == list(ISSUE_COLUMNS)


def test_sheet_level_issues_have_no_row_or_value():
    issue = Issue(None, "membership_type", "missing_column", "The sheet has no Membership Type column.")
    [shown] = issue_rows([issue], [])
    assert shown["display"]["Row"] == "—" and shown["display"]["Value"] == ""
    assert shown["display"]["Column"] == "Membership Type"


def test_ledger_warnings_list_every_payment_left_out():
    when = datetime(2026, 11, 1)
    orphan = Payment("P-0003", "MS-999", Decimal("1500"), date(2026, 11, 1), "recorded", when)
    clash = Payment("P-0001", "MS-001", Decimal("200.50"), date(2026, 11, 2), "recorded", when)
    merge = LedgerMerge(Dataset((), (), ()), (orphan,), (clash,))
    warnings = ledger_warnings(merge)
    assert len(warnings) == 2
    assert "P-0003" in warnings[0] and "MS-999" in warnings[0] and "₹1,500" in warnings[0]
    assert "not counted" in warnings[0]
    assert "P-0001" in warnings[1] and "₹200.50" in warnings[1] and "not counted" in warnings[1]
    assert ledger_warnings(LedgerMerge(Dataset((), (), ()), (), ())) == []
