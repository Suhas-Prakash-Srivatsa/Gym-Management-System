"""Independent acceptance tests for ticket 08 (recording a payment), written by the tester.

Hand-derived from src/files/Book1.csv at a frozen today of 2026-11-08.
"""

import ast
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from src.assemble import build_dataset, with_ledger
from src.balances import all_statuses, outstanding_balance
from src.ledger import append_payment, read_payments
from src.money import format_money
from src.recording import attribution_required, build_payment, default_membership, validate_payment
from src.sheet import read_rows

ROOT = Path(__file__).resolve().parent.parent
BOOK1 = ROOT / "src" / "files" / "Book1.csv"
TODAY = date(2026, 11, 8)
NOW = datetime(2026, 11, 8, 12, 0)


@pytest.fixture
def ds():
    return build_dataset(read_rows(BOOK1)[0])


def ms(dataset, membership_id):
    return next(m for m in dataset.memberships if m.membership_id == membership_id)


def codes(issues):
    return [(i.code, i.blocking) for i in issues]


def receivable(dataset):
    return sum(s.outstanding for s in all_statuses(dataset, TODAY) if s.outstanding > 0)


# --- Attribution -------------------------------------------------------------

@pytest.mark.parametrize("member_id", [f"M{n:03d}" for n in range(2, 25) if n != 9])
def test_every_single_membership_member_is_attributed_automatically(ds, member_id):
    assert attribution_required(ds, member_id) is False


@pytest.mark.parametrize("member_id", ["M001", "M009"])
def test_renewing_members_must_choose(ds, member_id):
    assert attribution_required(ds, member_id) is True


def test_suhas_defaults_to_ms_001_due_1_august(ds):
    assert default_membership(ds, "M001", TODAY).membership_id == "MS-001"


def test_manoj_defaults_to_the_contract_that_can_still_take_money(ds):
    # MS-009 is settled (Next Due 2026-03-05); any payment there is refused.
    assert validate_payment(ds, ms(ds, "MS-009"), Decimal("1"), TODAY, TODAY)[0].code == \
        "exceeds_outstanding"
    assert default_membership(ds, "M009", TODAY).membership_id == "MS-026"


def test_single_membership_default_is_that_membership(ds):
    assert default_membership(ds, "M022", TODAY).membership_id == "MS-022"


# --- Validation --------------------------------------------------------------

def test_ceiling_message_matches_the_ticket(ds):
    [issue] = validate_payment(ds, ms(ds, "MS-001"), Decimal("6001"), TODAY, TODAY)
    assert issue.code == "exceeds_outstanding" and issue.blocking
    assert "Suhas Prakash / MS-001 has ₹6,000 outstanding — enter ₹6,000 or less" in issue.message


@pytest.mark.parametrize("amount", ["0", "-1", "-0.01", "0.00"])
def test_non_positive_amounts_are_rejected(ds, amount):
    assert [c for c, b in codes(validate_payment(ds, ms(ds, "MS-001"), Decimal(amount), TODAY, TODAY))
            if b]


@pytest.mark.parametrize("amount", ["100.005", "NaN", "Infinity"])
def test_unreal_amounts_are_rejected_not_rounded(ds, amount):
    assert codes(validate_payment(ds, ms(ds, "MS-001"), Decimal(amount), TODAY, TODAY)) == [
        ("invalid_amount", True)]


def test_issues_are_returned_never_raised_for_any_amount(ds):
    for amount in ["1E+30", "123456789012345678901234567890"]:
        issues = validate_payment(ds, ms(ds, "MS-001"), Decimal(amount), TODAY, TODAY)
        assert issues and all(i.blocking for i in issues)


def test_back_dated_payment_is_allowed(ds):
    assert validate_payment(ds, ms(ds, "MS-001"), Decimal("100"), date(2026, 6, 1), TODAY) == []
    assert validate_payment(ds, ms(ds, "MS-001"), Decimal("100"), date(2026, 10, 1), TODAY) == []


def test_payment_dated_before_joining_warns_but_does_not_block(ds):
    # A renewal paid in advance (MS-026 starts 1 Nov; Manoj pays 30 Oct).
    issues = validate_payment(ds, ms(ds, "MS-026"), Decimal("6000"), date(2026, 10, 30), TODAY)
    assert issues and not any(i.blocking for i in issues)


def test_future_date_warns_and_payment_is_still_constructible(ds):
    future = date(2026, 12, 1)
    issues = validate_payment(ds, ms(ds, "MS-001"), Decimal("100"), future, TODAY)
    assert codes(issues) == [("paid_on_in_future", False)]
    p = build_payment(ms(ds, "MS-001"), Decimal("100"), future, [], NOW)
    assert p.paid_on == future and p.source == "recorded"


def test_today_is_not_the_future(ds):
    assert validate_payment(ds, ms(ds, "MS-001"), Decimal("100"), TODAY, TODAY) == []


# --- End to end through the real ledger file ---------------------------------

def record(tmp_path, dataset, membership_id, amount, paid_on=TODAY):
    ledger = tmp_path / "payments.csv"
    target = ms(dataset, membership_id)
    issues = validate_payment(dataset, target, Decimal(amount), paid_on, TODAY)
    if any(i.blocking for i in issues):
        return issues, dataset
    append_payment(ledger, build_payment(target, Decimal(amount), paid_on,
                                         read_payments(ledger), NOW))
    merged = with_ledger(build_dataset(read_rows(BOOK1)[0]), read_payments(ledger))
    assert not merged.orphaned and not merged.conflicting
    return issues, merged.dataset


def test_paying_exactly_the_outstanding_zeroes_it(tmp_path, ds):
    _, after = record(tmp_path, ds, "MS-001", "6000")
    assert outstanding_balance(ms(after, "MS-001"), after.payments) == 0
    assert receivable(after) == Decimal("91300")


def test_three_payments_of_3000_against_6000(tmp_path, ds):
    issues, ds = record(tmp_path, ds, "MS-001", "3000")
    assert issues == []
    issues, ds = record(tmp_path, ds, "MS-001", "3000")
    assert issues == []
    issues, ds = record(tmp_path, ds, "MS-001", "3000")
    assert codes(issues) == [("exceeds_outstanding", True)]
    assert "nothing outstanding" in issues[0].message
    ids = [p.payment_id for p in read_payments(tmp_path / "payments.csv")]
    assert ids == ["P-0001", "P-0002"]


def test_paise_payment_reduces_receivable_exactly(tmp_path, ds):
    _, after = record(tmp_path, ds, "MS-003", "0.10")
    assert receivable(after) == Decimal("97299.90")
    assert str(read_payments(tmp_path / "payments.csv")[0].amount) == "0.10"


def test_new_ids_skip_ids_taken_by_orphans_in_the_raw_ledger(tmp_path, ds):
    ledger = tmp_path / "payments.csv"
    stray = build_payment(ms(ds, "MS-001"), Decimal("1"), TODAY, [], NOW)
    append_payment(ledger, stray.__class__(**{**stray.__dict__, "membership_id": "MS-999"}))
    p = build_payment(ms(ds, "MS-001"), Decimal("1"), TODAY, read_payments(ledger), NOW)
    assert p.payment_id == "P-0002"


def test_build_payment_stores_plain_two_place_amounts(ds):
    for raw in ["6E+3", "6000", "6000.5"]:
        text = str(build_payment(ms(ds, "MS-001"), Decimal(raw), TODAY, [], NOW).amount)
        assert "E" not in text and text.split(".")[1].__len__() == 2


# --- Formatting --------------------------------------------------------------

@pytest.mark.parametrize("value, text", [
    ("97300", "₹97,300"), ("6000", "₹6,000"), ("999", "₹999"), ("0", "₹0"),
    ("1000.5", "₹1,000.50"), ("60950", "₹60,950"),
])
def test_format_money_below_one_lakh(value, text):
    assert format_money(Decimal(value)) == text


@pytest.mark.parametrize("value, text", [
    ("235400", "₹2,35,400"), ("100000", "₹1,00,000"), ("1234567", "₹12,34,567"),
    ("12345678.9", "₹1,23,45,678.90"),
])
def test_format_money_uses_indian_grouping(value, text):
    assert format_money(Decimal(value)) == text


# --- Constraints ---------------------------------------------------------------

def test_recording_is_pure():
    src = (ROOT / "src" / "recording.py").read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Call):
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            assert name not in {"open", "today", "now", "float", "utcnow"}, name
    assert "streamlit" not in src


@pytest.mark.parametrize("value, text", [
    ("0.005", "₹0.01"), ("0.015", "₹0.02"), ("2.675", "₹2.68"), ("99999.995", "₹1,00,000"),
    ("-97300", "-₹97,300"), ("-1234567.5", "-₹12,34,567.50"), ("1000000000", "₹1,00,00,00,000"),
])
def test_format_money_rounds_half_up_and_signs_negatives(value, text):
    assert format_money(Decimal(value)) == text


def test_payment_before_joining_still_records(tmp_path, ds):
    issues, after = record(tmp_path, ds, "MS-026", "6000", paid_on=date(2026, 10, 30))
    assert codes(issues) == [("paid_before_joining", False)]
    assert receivable(after) == Decimal("91300")
