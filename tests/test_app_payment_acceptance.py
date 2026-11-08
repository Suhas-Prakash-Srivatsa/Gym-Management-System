"""Tester's acceptance tests for ticket 12 (record a payment), independent of the coder's.

Every expectation is hand-calculated from src/files/Book1.csv at today = 2026-11-08:

    Outstanding per Membership (Membership Amount - Paid Amount, floored at 0):
    MS-001 6000, 002 16000, 003 4500, 006 4500, 007 2200, 008 4000, 010 5000,
    011 2000, 012 6250, 014 8000, 015 2100, 017 6200, 018 6400, 019 1000,
    020 4500, 021 6000, 022 2000, 024 4650, 026 6000; all others 0.
    Total Receivable = 97,300.

    Members holding two Memberships: M001 Suhas Prakash (MS-001 owes, MS-025 paid)
    and M009 Manoj Verma (MS-009 paid, MS-026 owes 6000, last paid 2026-11-01).
    Next Due = last payment (or Date Joined) + 2 calendar months.
"""

import ast
import shutil
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
FILES = ROOT / "src" / "files"
APP = ROOT / "app.py"


@pytest.fixture
def sheet(tmp_path, monkeypatch):
    path = tmp_path / "gym" / "Book1.csv"
    path.parent.mkdir()
    shutil.copy(FILES / "Book1.csv", path)
    monkeypatch.setenv("GYM_TODAY", "2026-11-08")
    monkeypatch.setenv("GYM_SHEET", str(path))
    return path


@pytest.fixture
def ledger(sheet):
    return sheet.parent / "payments.csv"


def start():
    at = AppTest.from_file(str(APP), default_timeout=30)
    at.run()
    ok(at)
    return at


@pytest.fixture
def at(sheet):
    return start()


def ok(at):
    assert not at.exception, [e.value for e in at.exception]


def receivable(at):
    return {m.label: m.value for m in at.metric}["Total Receivable"]


def table(at):
    [t] = [d for d in at.dataframe if "Next Due Date" in d.value.columns]
    return t.value.set_index("Membership ID")


def text(elements):
    return " ".join(e.value for e in elements)


def amount_box(at):
    [box] = [t for t in at.text_input if t.label == "Amount (₹)"]
    return box


def date_box(at):
    [box] = [d for d in at.date_input if d.label == "Paid on"]
    return box


def selectors(at):
    return [s for s in at.selectbox if s.label == "Membership"]


def choose(at, name):
    at.selectbox(key="payment_member").select(name)
    at.run()
    ok(at)


def press(at, amount, paid_on=None):
    amount_box(at).input(amount)
    if paid_on is not None:
        date_box(at).set_value(paid_on)
    at.run()
    at.button(key="record_payment").click()
    at.run()
    ok(at)


def rows(ledger):
    return ledger.read_text(encoding="utf-8").splitlines()[1:] if ledger.exists() else []


# --- who is asked which Membership ---


def test_exactly_suhas_and_manoj_hold_two_memberships_in_the_data(sheet):
    import csv
    from collections import Counter

    with sheet.open(encoding="utf-8-sig", newline="") as f:
        counts = Counter(r["Member ID"] for r in csv.DictReader(f))
    assert len(counts) == 24
    assert sorted(m for m, n in counts.items() if n > 1) == ["M001", "M009"]


def test_manoj_defaults_to_the_owing_ms_026_not_the_settled_ms_009(at):
    choose(at, "Manoj Verma")
    [selector] = selectors(at)
    assert [o.split(" ")[0] for o in selector.options] == ["MS-009", "MS-026"]
    assert selector.value.membership_id == "MS-026"


def test_a_single_membership_member_is_told_where_the_money_goes(at):
    choose(at, "Vandana Rao")
    assert not selectors(at)
    assert "MS-002" in text(at.caption)


# --- the money lands on the right Membership ---


def test_3000_against_manoj_default_lowers_receivable_by_exactly_3000(at, ledger):
    assert receivable(at) == "₹97,300"
    assert table(at).loc["MS-026", "Next Due Date"] == "2027-01-01"
    choose(at, "Manoj Verma")
    press(at, "3000")
    assert receivable(at) == "₹94,300"
    t = table(at)
    assert t.loc["MS-026", "Outstanding"] == "₹3,000"
    assert t.loc["MS-026", "Next Due Date"] == "2027-01-08"
    assert "MS-009" not in t.index  # the settled contract was not touched
    [row] = rows(ledger)
    assert row.startswith("P-0001,MS-026,3000.00,2026-11-08,recorded,")


def test_choosing_the_non_default_membership_is_honoured(at, ledger):
    choose(at, "Suhas Prakash")
    [selector] = selectors(at)
    # AppTest exposes the formatted labels; the label leads with the Membership ID.
    selector.select(next(o for o in selector.options if o.startswith("MS-025")))
    at.run()
    ok(at)
    assert selectors(at)[0].value.membership_id == "MS-025"
    press(at, "100")
    assert "Suhas Prakash / MS-025 has nothing outstanding." in text(at.error)
    assert not ledger.exists()


def test_paying_exactly_the_outstanding_settles_it(at, ledger):
    choose(at, "Arjun Menon")
    press(at, "₹4,500")
    assert "MS-003" not in table(at).index
    assert receivable(at) == "₹92,800"
    [row] = rows(ledger)
    assert row.startswith("P-0001,MS-003,4500.00,")


def test_two_partial_payments_then_the_remainder_is_the_new_ceiling(at, ledger):
    choose(at, "Imran Khan")  # MS-019 owes 1000
    press(at, "400.50")
    press(at, "600")
    assert "₹599.50" in text(at.error)
    press(at, "599.50")
    assert "MS-019" not in table(at).index
    assert [r.split(",")[2] for r in rows(ledger)] == ["400.50", "599.50"]
    assert receivable(at) == "₹96,300"


def test_selector_survives_its_label_changing_after_a_payment(at, ledger):
    choose(at, "Manoj Verma")
    press(at, "1000")
    [selector] = selectors(at)
    assert selector.value.membership_id == "MS-026"
    press(at, "5000")  # the remaining ceiling exactly
    assert receivable(at) == "₹91,300"
    assert [r.split(",")[1] for r in rows(ledger)] == ["MS-026", "MS-026"]


# --- what is typed ---


@pytest.mark.parametrize("typed", ["", "   ", "6000.555", "-5", "₹-5", "0", "0.00", "1e3",
                                   "6,000.5.5", "NaN", "Infinity"])
def test_amounts_that_must_never_be_recorded(at, ledger, typed):
    choose(at, "Suhas Prakash")
    press(at, typed)
    assert at.error, f"{typed!r} was not refused"
    assert not ledger.exists()
    assert receivable(at) == "₹97,300"


def test_symbol_and_comma_are_understood(at, ledger):
    choose(at, "Suhas Prakash")
    press(at, " ₹6,000 ")
    assert rows(ledger)[0].split(",")[2] == "6000.00"
    assert receivable(at) == "₹91,300"


def test_paise_are_kept_exactly_never_through_float(at, ledger):
    choose(at, "Vandana Rao")
    press(at, "0.1")
    press(at, "0.2")
    assert [r.split(",")[2] for r in rows(ledger)] == ["0.10", "0.20"]
    assert table(at).loc["MS-002", "Outstanding"] == "₹15,999.70"


def test_check_payment_never_hands_back_a_float():
    from src import recording
    from src.assemble import build_dataset
    from src.sheet import read_rows

    dataset = build_dataset(read_rows(FILES / "Book1.csv")[0])
    ms = next(m for m in dataset.memberships if m.membership_id == "MS-001")
    check = recording.check_payment(dataset, ms, "₹6,000", date(2026, 11, 8), date(2026, 11, 8))
    assert type(check.amount) is Decimal and check.amount == Decimal("6000")
    assert check.accepted
    over = recording.check_payment(dataset, ms, "6000.01", date(2026, 11, 8), date(2026, 11, 8))
    assert not over.accepted and "₹6,000" in over.errors[0].message


# --- warnings allow, errors block ---


def test_a_date_before_joining_warns_and_still_records(at, ledger):
    choose(at, "Suhas Prakash")  # MS-001 joined 2026-06-01
    date_box(at).set_value(date(2026, 5, 1))
    at.run()
    assert "2026-06-01" in text(at.warning)
    press(at, "100")
    [row] = rows(ledger)
    assert ",2026-05-01,recorded," in row


def test_a_warning_does_not_rescue_an_error(at, ledger):
    choose(at, "Suhas Prakash")
    press(at, "6001", paid_on=date(2026, 12, 1))
    assert "in the future" in text(at.warning)
    assert "₹6,000" in text(at.error)
    assert not ledger.exists()


# --- double submit ---


def test_pressing_record_twice_records_once(at, ledger):
    choose(at, "Suhas Prakash")
    press(at, "500")
    assert amount_box(at).value == ""
    assert date_box(at).value == date(2026, 11, 8)
    for _ in range(2):
        at.button(key="record_payment").click()
        at.run()
        ok(at)
    assert len(rows(ledger)) == 1
    assert receivable(at) == "₹96,800"


def test_a_fresh_session_continues_the_payment_ids(sheet, ledger):
    first = start()
    choose(first, "Suhas Prakash")
    press(first, "500")
    second = start()
    choose(second, "Vandana Rao")
    press(second, "500")
    assert [r.split(",")[0] for r in rows(ledger)] == ["P-0001", "P-0002"]
    assert receivable(second) == "₹96,300"


# --- file trouble ---


def test_a_ledger_that_cannot_be_read_when_recording_is_explained(at, ledger, monkeypatch):
    def locked(path):
        raise PermissionError(13, "Permission denied", str(path))

    choose(at, "Suhas Prakash")
    amount_box(at).input("500")
    at.run()
    monkeypatch.setattr("src.ledger.read_payments", locked)
    at.button(key="record_payment").click()
    at.run()
    assert "payments.csv" in text(at.error) and "Excel" in text(at.error)
    assert not ledger.exists()


def test_a_ledger_missing_a_column_names_it_and_is_left_alone(sheet, ledger):
    # read_payments refuses it at load (ticket 07), so the form never offers to append.
    content = ("payment_id,membership_id,amount,paid_on,source\r\n"
               "P-0001,MS-002,500,2026-11-01,recorded\r\n").encode()
    ledger.write_bytes(content)
    at = start()
    assert "recorded_at" in text(at.error)
    assert not [b for b in at.button if b.key == "record_payment"]
    assert ledger.read_bytes() == content


def test_payments_recorded_on_corrected_data_go_beside_the_sheet(sheet, ledger):
    shutil.copy(sheet, sheet.parent / "members_clean.csv")  # newer than the sheet
    at = start()
    assert "members_clean.csv" in text(at.info)
    choose(at, "Suhas Prakash")
    press(at, "6000")
    assert receivable(at) == "₹91,300"
    [row] = rows(ledger)
    assert row.startswith("P-0001,MS-001,6000.00,")
    assert not (sheet.parent / "members_clean.csv.payments.csv").exists()


def test_the_input_sheet_is_never_written(at, sheet):
    before = sheet.read_bytes()
    choose(at, "Suhas Prakash")
    press(at, "6000")
    assert sheet.read_bytes() == before


# --- ADR 0001 ---


def test_payment_form_functions_hold_no_arithmetic_or_comparison():
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    form = {"payment_form", "choose_membership", "record_payment"}
    funcs = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name in form]
    assert {f.name for f in funcs} == form
    for f in funcs:
        for node in ast.walk(f):
            assert not isinstance(node, (ast.BinOp, ast.AugAssign, ast.Compare)), (
                f"{f.name}: {ast.dump(node)[:80]}")
