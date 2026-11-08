"""Independent acceptance tests for ticket 09 (view projections), written by the tester.

Expected figures are hand-derived from src/files/Book1.csv at 2026-11-08.
"""

import ast
import csv
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from src.assemble import build_dataset, with_ledger
from src.balances import all_statuses
from src.recording import build_payment
from src.sheet import read_rows
from src.views import ROW_COLUMNS, TILE_LABELS, receivables_rows, tiles

ROOT = Path(__file__).resolve().parent.parent
BOOK1 = ROOT / "src" / "files" / "Book1.csv"
TODAY = date(2026, 11, 8)
NOW = datetime(2026, 11, 8, 12)

SETTLED = ["MS-009", "MS-023", "MS-005", "MS-013", "MS-016", "MS-025", "MS-004"]


@pytest.fixture
def ds():
    return build_dataset(read_rows(BOOK1)[0])


@pytest.fixture
def statuses(ds):
    return all_statuses(ds, TODAY)


def pay(ds, membership_id, amount):
    target = next(m for m in ds.memberships if m.membership_id == membership_id)
    p = build_payment(target, Decimal(amount), TODAY, [], NOW)
    return all_statuses(with_ledger(ds, [p]).dataset, TODAY)


# --- Tiles ---------------------------------------------------------------------

def test_tiles_match_hand_totals_from_the_raw_csv(statuses):
    with BOOK1.open(encoding="utf-8-sig", newline="") as f:
        raw = list(csv.DictReader(f))
    contract_total = sum(Decimal(r["Membership Amount"]) for r in raw)
    t = tiles(statuses)
    assert t["total_members"] == len({r["Member ID"] for r in raw}) == 24
    assert t["total_membership_value"] == contract_total == Decimal("235400")
    assert t["total_receivable"] == Decimal("97300")
    assert t["overdue"] == Decimal("60950")
    assert t["overdue_count"] == 11
    assert t["display"] == {
        "Total Members": "24", "Total Membership Value": "₹2,35,400",
        "Total Receivable": "₹97,300", "Overdue": "₹60,950",
    }
    assert tuple(t["display"]) == TILE_LABELS


def test_no_due_this_month_tile(statuses):
    assert not any("month" in k.casefold() for k in tiles(statuses)["display"])


def test_members_are_counted_once_not_per_membership(statuses):
    assert len(statuses) == 26
    assert tiles(statuses)["total_members"] == 24


# --- Table ---------------------------------------------------------------------

def test_receivables_table(statuses):
    rows = receivables_rows(statuses)
    assert len(rows) == 19
    assert (rows[0]["member_name"], rows[0]["membership_id"], rows[0]["next_due_date"]) == (
        "Pooja Shetty", "MS-020", date(2026, 4, 20))
    assert (rows[-1]["member_name"], rows[-1]["membership_id"], rows[-1]["next_due_date"]) == (
        "Ritu Malhotra", "MS-022", date(2027, 1, 5))
    dues = [r["next_due_date"] for r in rows]
    assert dues == sorted(dues)
    assert all(r["outstanding"] > 0 for r in rows)


def test_exactly_the_eleven_overdue_rows_are_tagged(statuses):
    rows = receivables_rows(statuses)
    tagged = [r for r in rows if r["display"]["Status"] == "DUE"]
    assert len(tagged) == 11
    for r in rows:
        assert (r["status"] == "DUE") == (r["next_due_date"] < TODAY) == r["is_overdue"]
    # Owing but inside the grace window: no tag.
    ms_022 = next(r for r in rows if r["membership_id"] == "MS-022")
    assert ms_022["status"] == "" and ms_022["display"]["Status"] == ""


def test_show_fully_paid_appends_the_seven_settled_rows(statuses):
    rows = receivables_rows(statuses, show_fully_paid=True)
    assert len(rows) == 26
    assert [r["outstanding"] > 0 for r in rows] == [True] * 19 + [False] * 7
    assert [r["membership_id"] for r in rows[19:]] == SETTLED
    assert {r["status"] for r in rows[19:]} == {"Paid"}
    assert rows[:19] == receivables_rows(statuses)


def test_ties_keep_sheet_order(ds):
    # Two Memberships with the same Next Due Date, listed in reverse sheet order.
    rows = receivables_rows(all_statuses(ds, TODAY))
    by_due = {}
    for r in rows:
        by_due.setdefault(r["next_due_date"], []).append(r["membership_id"])
    sheet = [m.membership_id for m in ds.memberships]
    for ids in by_due.values():
        assert ids == sorted(ids, key=sheet.index)


def test_ties_keep_input_order_on_a_constructed_tie(statuses):
    a, b = statuses[0], statuses[1]
    tied = [b.__class__(**{**s.__dict__, "next_due_on": date(2026, 9, 1)}) for s in (b, a)]
    assert [r["membership_id"] for r in receivables_rows(tied)] == [
        b.membership.membership_id, a.membership.membership_id]


def test_display_row_shows_names_and_formatted_money(statuses):
    row = receivables_rows(statuses)[0]
    assert tuple(row["display"]) == ROW_COLUMNS
    assert row["display"] == {
        "Member Name": "Pooja Shetty", "Membership ID": "MS-020",
        "Membership Type": "Half-Yearly", "Date Joined": "2026-02-20",
        "Contract Amount": "₹9,000", "Paid": "₹4,500", "Outstanding": "₹4,500",
        "Last Payment Date": "2026-02-20", "Next Due Date": "2026-04-20", "Status": "DUE",
    }


def test_never_paid_row_shows_a_placeholder_date(statuses):
    ms_022 = next(r for r in receivables_rows(statuses) if r["membership_id"] == "MS-022")
    assert ms_022["last_payment_date"] is None
    assert ms_022["display"]["Last Payment Date"] == "—"


def test_name_keyed_member_shows_the_name_not_the_key():
    rows, _ = read_rows(BOOK1)
    no_ids = [{k: v for k, v in r.items() if k != "member_id"} for r in rows]
    statuses = all_statuses(build_dataset(no_ids), TODAY)
    first = receivables_rows(statuses)[0]
    assert first["member_id"] == "pooja shetty"
    assert first["display"]["Member Name"] == "Pooja Shetty"
    assert tiles(statuses)["total_members"] == 24


# --- Ledger interaction ---------------------------------------------------------

def test_partial_payment_moves_receivable_by_exactly_its_amount(ds, statuses):
    before = tiles(statuses)
    after = tiles(pay(ds, "MS-003", "100.50"))  # not overdue: Overdue tile unchanged
    assert before["total_receivable"] - after["total_receivable"] == Decimal("100.50")
    assert after["overdue"] == before["overdue"]
    assert after["total_membership_value"] == before["total_membership_value"]
    assert after["display"]["Total Receivable"] == "₹97,199.50"


def test_clearing_an_overdue_balance_moves_both_tiles_and_the_row(ds, statuses):
    before = tiles(statuses)
    after_statuses = pay(ds, "MS-020", "4500")
    after = tiles(after_statuses)
    assert before["total_receivable"] - after["total_receivable"] == Decimal("4500")
    assert before["overdue"] - after["overdue"] == Decimal("4500")
    assert after["overdue_count"] == 10
    unpaid = receivables_rows(after_statuses)
    assert len(unpaid) == 18 and "MS-020" not in [r["membership_id"] for r in unpaid]
    everything = receivables_rows(after_statuses, show_fully_paid=True)
    settled = [r["membership_id"] for r in everything[18:]]
    assert "MS-020" in settled and everything[18 + settled.index("MS-020")]["status"] == "Paid"


def test_partial_payment_on_an_overdue_row_restarts_its_grace(ds, statuses):
    # Spec rule 4: Next Due Date runs from the Last Payment Date, so any payment
    # lifts the DUE tag; the Overdue tile drops by the whole remaining balance.
    after_statuses = pay(ds, "MS-020", "100")
    after = tiles(after_statuses)
    assert tiles(statuses)["overdue"] - after["overdue"] == Decimal("4500")
    row = next(r for r in receivables_rows(after_statuses) if r["membership_id"] == "MS-020")
    assert row["status"] == "" and row["next_due_date"] == date(2027, 1, 8)


# --- Shape and constraints --------------------------------------------------------

def test_projections_serialise_to_json_with_str_for_decimal_and_date(statuses):
    def only_known(o):
        assert isinstance(o, (Decimal, date)), type(o)
        return str(o)

    payload = {"tiles": tiles(statuses), "rows": receivables_rows(statuses, True)}
    back = json.loads(json.dumps(payload, default=only_known))
    assert back["tiles"]["total_receivable"] == "97300"
    assert back["rows"][0]["next_due_date"] == "2026-04-20"


def test_display_values_are_all_strings(statuses):
    for r in receivables_rows(statuses, True):
        assert all(isinstance(v, str) for v in r["display"].values())
    assert all(isinstance(v, str) for v in tiles(statuses)["display"].values())


def test_empty_dataset():
    assert receivables_rows([]) == []
    t = tiles([])
    assert t["display"] == {"Total Members": "0", "Total Membership Value": "₹0",
                            "Total Receivable": "₹0", "Overdue": "₹0"}


def test_views_is_pure_and_presentation_free():
    src = (ROOT / "src" / "views.py").read_text(encoding="utf-8")
    imported = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.ImportFrom):
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported |= {a.name for a in node.names}
        elif isinstance(node, ast.Call):
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            assert name not in {"open", "today", "now", "float"}, name
    assert not any("streamlit" in m for m in imported)
    lowered = src.casefold()
    assert "<span" not in lowered and "color" not in lowered and "#ff" not in lowered


def test_two_people_sharing_a_name_are_two_members():
    rows, _ = read_rows(BOOK1)
    twin = {**rows[1], "member_id": "M099", "membership_id": "MS-099"}  # another Vandana Rao
    statuses = all_statuses(build_dataset([*rows, twin]), TODAY)
    assert tiles(statuses)["total_members"] == 25
