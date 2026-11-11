from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from src.assemble import build_dataset, with_ledger
from src.balances import outstanding_balance
from src.ledger import append_payment, read_payments
from src.models import Dataset, Member, Membership, MembershipType, Payment
from src.recording import (
    attribution_required,
    build_payment,
    check_payment,
    default_membership,
    member_options,
    membership_options,
    memberships_of,
    validate_payment,
)
from src.sheet import read_rows

FILES = Path(__file__).resolve().parent.parent / "src" / "files"
TODAY = date(2026, 11, 8)
RECORDED_AT = datetime(2026, 11, 8, 18, 5, 30)


@pytest.fixture(scope="module")
def book1():
    """Book1.csv merged with an empty ledger, as the app would see it on first run."""
    rows, _ = read_rows(FILES / "Book1.csv")
    return with_ledger(build_dataset(rows), []).dataset


def _ms(membership_id, joined_on, member_id="M100"):
    return Membership(membership_id, member_id, MembershipType.MONTHLY, joined_on,
                      Decimal("2000"), 1)


# --- attribution_required ---


def test_a_member_with_one_membership_needs_no_attribution(book1):
    assert attribution_required(book1, "M002") is False  # Vandana Rao, MS-002 only


def test_a_member_with_two_memberships_must_say_which(book1):
    assert attribution_required(book1, "M001") is True  # Suhas Prakash: MS-001, MS-025
    assert attribution_required(book1, "M009") is True  # Manoj Verma: MS-009, MS-026


def test_attribution_matches_member_ids_exactly(book1):
    assert attribution_required(book1, "m001") is False


# --- default_membership ---


def test_suhas_defaults_to_ms_001_due_first(book1):
    # MS-001 is due 2026-08-01; MS-025 (paid in full on 2026-10-20) is due 2026-12-20.
    assert default_membership(book1, "M001", TODAY).membership_id == "MS-001"


def test_a_settled_membership_is_skipped_when_another_still_owes(book1):
    # Manoj Verma: MS-009 is fully paid, due 2026-03-05; MS-026 owes 6,000, due 2027-01-01.
    # The earliest Next Due Date is the settled one; defaulting there would invite
    # a payment the over-payment rule then has to refuse.
    assert default_membership(book1, "M009", TODAY).membership_id == "MS-026"


def test_when_everything_is_settled_the_earliest_due_is_still_the_default():
    member = Member("M100", "Test")
    first, second = _ms("A", date(2026, 1, 1)), _ms("B", date(2026, 3, 1))
    paid = [Payment(f"OPEN-{m.membership_id}", m.membership_id, Decimal("2000"),
                    m.joined_on, "opening", datetime(2026, 1, 1)) for m in (first, second)]
    dataset = Dataset((member,), (second, first), tuple(paid))
    assert default_membership(dataset, "M100", TODAY).membership_id == "A"


def test_equal_next_due_dates_fall_back_to_sheet_order():
    member = Member("M100", "Test")
    later_row, earlier_row = _ms("Z", date(2026, 9, 1)), _ms("A", date(2026, 9, 1))
    dataset = Dataset((member,), (later_row, earlier_row), ())
    assert default_membership(dataset, "M100", TODAY).membership_id == "Z"


def test_a_member_with_no_memberships_has_no_default():
    with pytest.raises(ValueError, match="M404"):
        default_membership(Dataset((), (), ()), "M404", TODAY)


# --- validate_payment ---


def _membership(dataset, membership_id):
    return next(m for m in dataset.memberships if m.membership_id == membership_id)


def _summary(issues):
    return [(i.column, i.code, i.severity) for i in issues]


def test_paying_one_rupee_more_than_outstanding_is_refused_naming_the_ceiling(book1):
    issues = validate_payment(book1, _membership(book1, "MS-001"), Decimal("6001"), TODAY, TODAY)
    assert _summary(issues) == [("amount", "exceeds_outstanding", "error")]
    assert issues[0].message == (
        "Suhas Prakash / MS-001 has ₹6,000 outstanding — enter ₹6,000 or less.")
    assert issues[0].blocking


def test_paying_exactly_the_outstanding_balance_is_allowed(book1):
    assert validate_payment(book1, _membership(book1, "MS-001"), Decimal("6000"), TODAY, TODAY) == []


def test_amounts_in_exponent_or_padded_form_are_the_same_money(book1):
    ms = _membership(book1, "MS-001")
    for amount in (Decimal("6E+3"), Decimal("6000.00"), Decimal("1000.5")):
        assert validate_payment(book1, ms, amount, TODAY, TODAY) == []


def test_a_settled_membership_accepts_nothing(book1):
    issues = validate_payment(book1, _membership(book1, "MS-025"), Decimal("1"), TODAY, TODAY)
    assert _summary(issues) == [("amount", "exceeds_outstanding", "error")]
    assert issues[0].message == "Suhas Prakash / MS-025 has nothing outstanding."


@pytest.mark.parametrize("amount", [Decimal("0"), Decimal("-1"), Decimal("-0.01"), Decimal("0.00")])
def test_zero_or_negative_amounts_are_refused(book1, amount):
    issues = validate_payment(book1, _membership(book1, "MS-001"), amount, TODAY, TODAY)
    assert _summary(issues) == [("amount", "amount_not_positive", "error")]


@pytest.mark.parametrize("amount", [Decimal("100.005"), Decimal("0.001"), Decimal("NaN"),
                                    Decimal("Infinity"), Decimal("sNaN")])
def test_sub_paisa_and_non_finite_amounts_are_refused_not_rounded(book1, amount):
    issues = validate_payment(book1, _membership(book1, "MS-001"), amount, TODAY, TODAY)
    assert _summary(issues) == [("amount", "invalid_amount", "error")]


def test_a_future_payment_date_only_warns(book1):
    issues = validate_payment(book1, _membership(book1, "MS-001"), Decimal("3000"),
                              date(2026, 11, 9), TODAY)
    assert _summary(issues) == [("paid_on", "paid_on_in_future", "warning")]
    assert not issues[0].blocking
    assert "2026-11-09" in issues[0].message


@pytest.mark.parametrize("paid_on", [TODAY, date(2026, 7, 1), date(2026, 6, 1)])
def test_back_dated_payments_are_allowed(book1, paid_on):
    # Cash gets recorded days late; MS-001 was joined on 2026-06-01.
    assert validate_payment(book1, _membership(book1, "MS-001"), Decimal("100"), paid_on, TODAY) == []


def test_a_payment_dated_before_the_membership_began_only_warns(book1):
    # An advance on a renewal: Manoj's MS-026 starts 2026-11-01, paid 2026-10-30.
    issues = validate_payment(book1, _membership(book1, "MS-026"), Decimal("6000"),
                              date(2026, 10, 30), TODAY)
    assert _summary(issues) == [("paid_on", "paid_before_joining", "warning")]
    assert "2026-11-01" in issues[0].message and "year" in issues[0].message


@pytest.mark.parametrize("amount", ["1E+30", "123456789012345678901234567890", "1E+999999"])
def test_huge_amounts_are_reported_never_raised(book1, amount):
    issues = validate_payment(book1, _membership(book1, "MS-001"), Decimal(amount), TODAY, TODAY)
    assert _summary(issues) == [("amount", "invalid_amount", "error")]


def test_build_payment_refuses_huge_amounts_with_a_value_error(book1):
    with pytest.raises(ValueError):
        build_payment(_membership(book1, "MS-001"), Decimal("1E+30"), TODAY, [], RECORDED_AT)


def test_every_problem_is_reported_at_once(book1):
    issues = validate_payment(book1, _membership(book1, "MS-001"), Decimal("7000"),
                              date(2027, 1, 1), TODAY)
    assert _summary(issues) == [("amount", "exceeds_outstanding", "error"),
                                ("paid_on", "paid_on_in_future", "warning")]


def test_a_membership_outside_the_dataset_is_a_programming_error(book1):
    stranger = _ms("MS-999", date(2026, 1, 1))
    with pytest.raises(ValueError, match="MS-999"):
        validate_payment(book1, stranger, Decimal("1"), TODAY, TODAY)


def test_sheet_validation_issues_still_default_to_blocking_errors():
    from src.validation import Issue

    issue = Issue(1, "member_name", "missing_member_name", "Row 1: Member Name is empty.")
    assert issue.severity == "error" and issue.blocking


# --- build_payment, and the full record cycle through a real ledger ---



@pytest.fixture
def sheet_dataset():
    rows, _ = read_rows(FILES / "Book1.csv")
    return build_dataset(rows)


def _record(sheet_dataset, ledger_path, membership_id, amount, paid_on=TODAY):
    """What the shell does: merge, validate, build, append. Returns the issues."""
    raw = read_payments(ledger_path)
    dataset = with_ledger(sheet_dataset, raw).dataset
    membership = _membership(dataset, membership_id)
    issues = validate_payment(dataset, membership, amount, paid_on, TODAY)
    if not any(i.blocking for i in issues):
        append_payment(ledger_path, build_payment(membership, amount, paid_on, raw, RECORDED_AT))
    return issues


def _outstanding(sheet_dataset, ledger_path, membership_id):
    dataset = with_ledger(sheet_dataset, read_payments(ledger_path)).dataset
    return outstanding_balance(_membership(dataset, membership_id), dataset.payments)


def test_build_payment_records_new_money_with_the_next_id(book1):
    payment = build_payment(_membership(book1, "MS-001"), Decimal("3000"), TODAY, [], RECORDED_AT)
    assert payment == Payment("P-0001", "MS-001", Decimal("3000.00"), TODAY, "recorded", RECORDED_AT)
    assert str(payment.amount) == "3000.00"


def test_build_payment_takes_its_id_from_the_raw_ledger_orphans_included(book1):
    orphan = Payment("P-0007", "MS-999", Decimal("10"), TODAY, "recorded", RECORDED_AT)
    payment = build_payment(_membership(book1, "MS-001"), Decimal("1"), TODAY, [orphan], RECORDED_AT)
    assert payment.payment_id == "P-0008"


def test_a_normalised_amount_still_records_and_round_trips(book1, tmp_path):
    ledger = tmp_path / "payments.csv"
    amount = Decimal("6000.00").normalize()  # Decimal('6E+3')
    assert str(amount) == "6E+3"
    payment = build_payment(_membership(book1, "MS-001"), amount, TODAY, [], RECORDED_AT)
    append_payment(ledger, payment)
    assert read_payments(ledger) == [payment]
    assert read_payments(ledger)[0].amount == Decimal("6000")


def test_build_payment_refuses_to_round_sub_paisa_money(book1):
    with pytest.raises(ValueError, match="100.005"):
        build_payment(_membership(book1, "MS-001"), Decimal("100.005"), TODAY, [], RECORDED_AT)


def test_paying_the_whole_balance_leaves_exactly_zero(sheet_dataset, tmp_path):
    ledger = tmp_path / "payments.csv"
    assert _outstanding(sheet_dataset, ledger, "MS-001") == Decimal("6000")
    assert _record(sheet_dataset, ledger, "MS-001", Decimal("6000")) == []
    remaining = _outstanding(sheet_dataset, ledger, "MS-001")
    assert remaining == 0 and remaining.is_zero()


def test_two_halves_are_accepted_and_a_third_payment_is_refused(sheet_dataset, tmp_path):
    ledger = tmp_path / "payments.csv"
    assert _record(sheet_dataset, ledger, "MS-001", Decimal("3000")) == []
    assert _record(sheet_dataset, ledger, "MS-001", Decimal("3000")) == []
    third = _record(sheet_dataset, ledger, "MS-001", Decimal("3000"))
    assert [i.code for i in third] == ["exceeds_outstanding"]
    assert third[0].message == "Suhas Prakash / MS-001 has nothing outstanding."
    assert [p.payment_id for p in read_payments(ledger)] == ["P-0001", "P-0002"]
    assert _outstanding(sheet_dataset, ledger, "MS-001") == 0


def test_two_payments_cannot_sum_past_the_contract(sheet_dataset, tmp_path):
    # MS-001 is a ₹12,000 contract with ₹6,000 already paid at import.
    ledger = tmp_path / "payments.csv"
    assert _record(sheet_dataset, ledger, "MS-001", Decimal("5000")) == []
    second = _record(sheet_dataset, ledger, "MS-001", Decimal("1001"))
    assert second[0].message == "Suhas Prakash / MS-001 has ₹1,000 outstanding — enter ₹1,000 or less."


def test_a_future_dated_payment_warns_but_is_still_constructible(book1):
    ms = _membership(book1, "MS-001")
    future = date(2026, 12, 1)
    issues = validate_payment(book1, ms, Decimal("1000"), future, TODAY)
    assert [i.code for i in issues] == ["paid_on_in_future"]
    assert not any(i.blocking for i in issues)
    payment = build_payment(ms, Decimal("1000"), future, [], RECORDED_AT)
    assert payment.paid_on == future


def test_recording_imports_no_shell_module():
    import ast

    tree = ast.parse((Path(__file__).resolve().parent.parent / "src" / "recording.py")
                     .read_text(encoding="utf-8"))
    imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not imported & {"src.ledger", "src.sheet", "src.sidecar", "streamlit"}


def test_recording_reads_no_clock_or_files():
    source = (Path(__file__).resolve().parent.parent / "src" / "recording.py").read_text(
        encoding="utf-8")
    for forbidden in ("today()", "now()", "open(", "streamlit", "float", "import datetime"):
        assert forbidden not in source


# --- check_payment: the payment form's typed amount, parsed then validated ---


def test_a_typed_amount_is_parsed_and_accepted(book1):
    check = check_payment(book1, _membership(book1, "MS-001"), " ₹6,000 ", TODAY, TODAY)
    assert check.amount == Decimal("6000")
    assert check.issues == ()
    assert check.accepted


@pytest.mark.parametrize("typed", ["", "   ", "six thousand", "6,000/-", "-500", "1e3"])
def test_text_that_is_not_an_amount_is_refused_beside_the_amount(book1, typed):
    check = check_payment(book1, _membership(book1, "MS-001"), typed, TODAY, TODAY)
    assert check.amount is None
    assert _summary(check.issues) == [("amount", "invalid_amount", "error")]
    assert "6000" in check.issues[0].message  # shows how to type it
    assert not check.accepted


def test_date_warnings_still_show_when_the_amount_is_unreadable(book1):
    check = check_payment(book1, _membership(book1, "MS-001"), "", date(2026, 12, 1), TODAY)
    assert _summary(check.issues) == [("amount", "invalid_amount", "error"),
                                      ("paid_on", "paid_on_in_future", "warning")]


def test_check_payment_carries_validate_payments_rules(book1):
    ms = _membership(book1, "MS-001")
    over = check_payment(book1, ms, "6001", TODAY, TODAY)
    assert over.amount == Decimal("6001") and not over.accepted
    assert over.issues[0].message == (
        "Suhas Prakash / MS-001 has ₹6,000 outstanding — enter ₹6,000 or less.")
    assert _summary(check_payment(book1, ms, "0", TODAY, TODAY).issues) == [
        ("amount", "amount_not_positive", "error")]
    assert _summary(check_payment(book1, ms, "100.005", TODAY, TODAY).issues) == [
        ("amount", "invalid_amount", "error")]


def test_a_warning_alone_does_not_stop_the_payment(book1):
    check = check_payment(book1, _membership(book1, "MS-001"), "3000", date(2026, 11, 9), TODAY)
    assert _summary(check.issues) == [("paid_on", "paid_on_in_future", "warning")]
    assert check.accepted


# --- what the payment form offers ---


def test_members_are_offered_by_name_in_sheet_order_never_by_key(book1):
    options = member_options(book1)  # what the form shows -> which Member it means
    assert len(options) == 24
    assert list(options)[:2] == ["Suhas Prakash", "Vandana Rao"]
    assert options["Suhas Prakash"] == "M001"
    assert options["Priya Nair"] == "M004"
    assert not any(key in label for label, key in options.items())


def test_two_people_who_share_a_name_are_told_apart_by_their_memberships():
    a, b = Member("rakesh sharma", "Rakesh Sharma"), Member("rakesh sharma#2", "Rakesh Sharma")
    dataset = Dataset((a, b), (_ms("MS-003", date(2026, 1, 1), a.member_id),
                               _ms("MS-004", date(2026, 2, 1), b.member_id),
                               _ms("MS-009", date(2026, 3, 1), b.member_id)), ())
    assert member_options(dataset) == {
        "Rakesh Sharma (MS-003)": "rakesh sharma",
        "Rakesh Sharma (MS-004, MS-009)": "rakesh sharma#2",
    }


def test_only_two_of_book1s_24_members_are_asked_which_membership(book1):
    asked = [label for label, key in member_options(book1).items()
             if attribution_required(book1, key)]
    assert asked == ["Suhas Prakash", "Manoj Verma"]  # Suhas Prakash, Manoj Verma: 22 never see the selector


def test_a_members_memberships_are_offered_with_what_each_still_owes(book1):
    assert membership_options(book1, "M001") == {
        "MS-001": "MS-001 · Yearly · ₹6,000 outstanding",
        "MS-025": "MS-025 · Monthly · fully paid",
    }
    assert list(membership_options(book1, "M004")) == ["MS-004"]


def test_a_check_splits_its_issues_into_errors_and_warnings(book1):
    check = check_payment(book1, _membership(book1, "MS-001"), "6001", date(2026, 12, 1), TODAY)
    assert [i.code for i in check.errors] == ["exceeds_outstanding"]
    assert [i.code for i in check.warnings] == ["paid_on_in_future"]


def test_memberships_of_a_member_are_in_sheet_order(book1):
    assert [m.membership_id for m in memberships_of(book1, "M009")] == ["MS-009", "MS-026"]
    assert memberships_of(book1, "m009") == []


def test_an_untouched_form_does_not_warn_about_paying_before_joining(book1):
    # MS-022 starts on 2026-11-05; seen on 2026-11-04 with nothing entered yet.
    ms = _membership(book1, "MS-022")
    day = date(2026, 11, 4)
    assert check_payment(book1, ms, "", day, day).warnings == ()
    typed = check_payment(book1, ms, "500", day, day)
    assert [w.code for w in typed.warnings] == ["paid_before_joining"]
    picked = check_payment(book1, ms, "", date(2026, 11, 3), day)
    assert [w.code for w in picked.warnings] == ["paid_before_joining"]
