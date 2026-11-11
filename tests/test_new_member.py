"""Adding a Member from the dashboard (src/new_member.py), on Book1.csv at 2026-11-08."""

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from src.assemble import build_dataset, with_ledger
from src.balances import all_statuses
from src.ledger import append_payment, read_payments
from src.models import Payment
from src.new_member import NewMember, check_new_member, first_payment, next_id
from src.recording import member_options
from src.sheet import read_rows
from src.sidecar import corrections_stale, resolve_input, write_clean_members
from src.validation import validate
from src.views import ledger_warnings, tiles

ROOT = Path(__file__).resolve().parent.parent
BOOK1 = ROOT / "src" / "files" / "Book1.csv"
TODAY = date(2026, 11, 8)
NOW = datetime(2026, 11, 8, 12, 0)


@pytest.fixture
def book1():
    return read_rows(BOOK1)


def form(**changes) -> NewMember:
    fields = dict(name="Kiran Rao", membership_type="Yearly", joined_on=date(2026, 11, 1),
                  amount_text="12000", instalments_text="2", paid_text="", paid_on=TODAY)
    return NewMember(**{**fields, **changes})


def check(book1, ledger=(), **changes):
    rows, columns = book1
    return check_new_member(rows, columns, ledger, form(**changes), TODAY)


def codes(issues):
    return [(i.code, i.blocking) for i in issues]


# --- The row it becomes ------------------------------------------------------------------

def test_a_good_form_becomes_one_more_row_in_the_sheet_s_own_id_style(book1):
    result = check(book1)
    assert result.accepted and result.issues == ()
    assert result.row == {
        "member_id": "M025", "member_name": "Kiran Rao", "membership_id": "MS-027",
        "membership_type": "Yearly", "date_joined": "2026-11-01",
        "membership_amount": "12000", "instalments": "2", "paid_amount": "0",
        "last_payment_date": "",
    }
    assert list(result.rows) == [*book1[0], result.row]
    assert result.first_payment is None


def test_the_rows_stay_a_clean_sheet_and_the_new_member_is_on_the_dashboard(book1):
    result = check(book1)
    rows = list(result.rows)
    assert validate(rows, book1[1]).is_clean
    dataset = build_dataset(rows)
    assert "Kiran Rao" in member_options(dataset)
    figures = tiles(all_statuses(dataset, TODAY))["display"]
    assert figures["Total Members"] == "25"
    assert figures["Total Receivable"] == "₹1,09,300"  # 97,300 + 12,000 owed
    assert figures["Overdue"] == "₹60,950"  # joined a week ago: not late


def test_name_and_amount_are_tidied(book1):
    result = check(book1, name="  Kiran   Rao ", amount_text="₹12,000.50", instalments_text=" 3 ")
    assert result.row["member_name"] == "Kiran Rao"
    assert result.row["membership_amount"] == "12000.5"
    assert result.row["instalments"] == "3"


@pytest.mark.parametrize("kind", ["Monthly", "Half-Yearly", "Yearly", "half yearly"])
def test_every_membership_type_is_accepted(book1, kind):
    assert check(book1, membership_type=kind).accepted


# --- Errors: nothing is saved ------------------------------------------------------------

@pytest.mark.parametrize("changes, code, column", [
    ({"name": "   "}, "missing_member_name", "name"),
    ({"membership_type": "Weekly"}, "unknown_membership_type", "membership_type"),
    ({"joined_on": None}, "date_missing", "joined_on"),
    ({"amount_text": ""}, "invalid_amount", "amount"),
    ({"amount_text": "twelve"}, "invalid_amount", "amount"),
    ({"amount_text": "-500"}, "invalid_amount", "amount"),
    ({"amount_text": "100.005"}, "invalid_amount", "amount"),
    ({"amount_text": "0"}, "amount_not_positive", "amount"),
    ({"instalments_text": "0"}, "invalid_instalments", "instalments"),
    ({"instalments_text": "1.5"}, "invalid_instalments", "instalments"),
    ({"instalments_text": ""}, "invalid_instalments", "instalments"),
    ({"instalments_text": "²"}, "invalid_instalments", "instalments"),
    ({"paid_text": "lots"}, "invalid_amount", "paid"),
    ({"paid_text": "12000.01"}, "paid_exceeds_contract", "paid"),
    ({"paid_text": "500", "paid_on": None}, "date_missing", "paid_on"),
], ids=["blank-name", "type", "no-date", "no-amount", "words", "negative", "sub-paisa", "zero",
        "zero-instalments", "fraction-instalments", "no-instalments", "superscript",
        "paid-words", "paid-too-much", "paid-no-date"])
def test_each_error_blocks_and_names_its_field(book1, changes, code, column):
    result = check(book1, **changes)
    assert not result.accepted and result.rows == () and result.row is None
    assert [(i.code, i.column) for i in result.errors] == [(code, column)]


def test_errors_never_raise_for_anything_typed(book1):
    result = check(book1, name="", amount_text="1E+40", instalments_text="x", paid_text="NaN")
    assert {i.column for i in result.errors} == {"name", "amount", "instalments", "paid"}


# --- Warnings: shown, but the member is still added --------------------------------------

def test_a_future_join_date_warns(book1):
    result = check(book1, joined_on=date(2026, 12, 1))
    assert result.accepted
    assert codes(result.issues) == [("joined_on_in_future", False)]


def test_a_payment_before_joining_or_in_the_future_warns(book1):
    early = check(book1, paid_text="6000", paid_on=date(2026, 10, 30))
    assert early.accepted and codes(early.issues) == [("paid_before_joining", False)]
    late = check(book1, paid_text="6000", paid_on=date(2026, 11, 20))
    assert late.accepted and codes(late.issues) == [("paid_on_in_future", False)]


def test_the_payment_date_is_ignored_when_nothing_was_paid(book1):
    assert check(book1, paid_text="", paid_on=None).accepted
    assert check(book1, paid_text="0", paid_on=date(2030, 1, 1)).issues == ()


def test_a_name_already_in_the_sheet_warns_and_still_adds_a_different_person(book1):
    result = check(book1, name="suhas  PRAKASH")
    assert result.accepted
    [warning] = result.warnings
    assert warning.code == "duplicate_name" and "MS-001, MS-025" in warning.message
    assert result.row["member_id"] == "M025"  # not M001: a different person
    assert validate(list(result.rows), book1[1]).is_clean  # every row has an ID: no question


def test_a_same_name_member_without_a_member_id_is_refused_rather_than_asked_about():
    rows = [{"member_name": "Asha", "membership_type": "Monthly", "date_joined": "2026-11-01",
             "membership_amount": "2000", "instalments": "1", "paid_amount": "0"}]
    columns = list(rows[0])
    result = check_new_member(rows, columns, [], form(name="Asha"), TODAY)
    assert not result.accepted
    assert "duplicate_name_without_id" in [i.code for i in result.errors]


# --- IDs never collide -------------------------------------------------------------------

def test_next_id_follows_the_sheet_s_style_and_skips_anything_taken():
    assert next_id(["M001", "M024", "M009"], ["M001", "M024", "M009"], "M") == "M025"
    assert next_id(["MS-001", "MS-026"], ["MS-001", "MS-026", "ms-027"], "MS-") == "MS-028"
    assert next_id(["D1", "D2"], ["D1", "D2"], "M") == "D3"
    assert next_id([], [], "MS-") == "MS-001"
    assert next_id(["", "  "], ["kiran"], "M") == "M001"
    assert next_id(["M999"], ["M999"], "M") == "M1000"


def test_a_sheet_without_ids_gets_ids_that_leave_existing_members_alone():
    rows = [{"member_name": "Asha", "membership_type": "Monthly", "date_joined": "2026-11-01",
             "membership_amount": "2000", "instalments": "1", "paid_amount": "0"}]
    result = check_new_member(rows, list(rows[0]), [], form(), TODAY)
    assert (result.row["member_id"], result.row["membership_id"]) == ("M001", "MS-001")
    ids = [m.membership_id for m in build_dataset(list(result.rows)).memberships]
    assert ids == ["asha-01", "MS-001"]  # Asha's generated ID is unchanged


def test_a_membership_id_named_only_by_the_ledger_is_never_reused(book1):
    orphan = Payment("P-0001", "MS-027", Decimal("500"), TODAY, "recorded", NOW)
    assert check(book1, ledger=[orphan]).row["membership_id"] == "MS-028"


# --- Money paid at sign-up goes to the ledger --------------------------------------------

def test_money_paid_at_sign_up_is_one_recorded_payment_and_counts_once(book1, tmp_path):
    ledger_path = tmp_path / "payments.csv"
    append_payment(ledger_path, Payment("P-0001", "MS-001", Decimal("100"), TODAY, "recorded", NOW))
    ledger = read_payments(ledger_path)
    result = check(book1, ledger=ledger, paid_text="₹6,000", paid_on=date(2026, 11, 1))
    assert result.row["paid_amount"] == "0"  # never an Opening Balance in the row
    payment = first_payment(result, ledger, NOW)
    assert payment == Payment("P-0002", "MS-027", Decimal("6000.00"), date(2026, 11, 1),
                              "recorded", NOW)
    append_payment(ledger_path, payment)
    merge = with_ledger(build_dataset(list(result.rows)), read_payments(ledger_path))
    assert ledger_warnings(merge) == []
    [status] = [s for s in all_statuses(merge.dataset, TODAY)
                if s.membership.membership_id == "MS-027"]
    assert (status.paid, status.outstanding) == (Decimal("6000.00"), Decimal("6000"))
    assert status.last_payment_on == date(2026, 11, 1)


def test_no_money_paid_means_no_payment(book1):
    assert first_payment(check(book1), [], NOW) is None


def test_a_refused_form_has_no_payment_to_record(book1):
    with pytest.raises(ValueError):
        first_payment(check(book1, name=""), [], NOW)


# --- Saved as members_clean.csv: the sheet is untouched and nothing goes stale ------------

def test_saving_the_rows_shows_the_member_next_run_and_asks_nothing(tmp_path):
    sheet = tmp_path / "Book1.csv"
    sheet.write_bytes(BOOK1.read_bytes())
    before = sheet.read_bytes()
    resolved = resolve_input(sheet)
    result = check_new_member(resolved.rows, resolved.columns, [], form(), TODAY)
    write_clean_members(tmp_path / "members_clean.csv", list(result.rows))
    assert not corrections_stale(sheet)
    again = resolve_input(sheet)
    assert again.used_clean_sidecar and validate(again.rows, again.columns).issues == ()
    assert again.rows[-1]["member_name"] == "Kiran Rao"
    assert again.rows[:-1] == [{**r, "last_payment_date": r.get("last_payment_date", "")}
                               for r in resolved.rows]
    assert sheet.read_bytes() == before


def test_a_second_member_follows_the_first(tmp_path):
    sheet = tmp_path / "Book1.csv"
    sheet.write_bytes(BOOK1.read_bytes())
    resolved = resolve_input(sheet)
    first = check_new_member(resolved.rows, resolved.columns, [], form(), TODAY)
    write_clean_members(tmp_path / "members_clean.csv", list(first.rows))
    resolved = resolve_input(sheet)
    second = check_new_member(resolved.rows, resolved.columns, [], form(name="Lata Iyer"), TODAY)
    assert (second.row["member_id"], second.row["membership_id"]) == ("M026", "MS-028")


# --- Fix round 1: bounds, formula-like names, a type must be chosen, ID styles -------------

@pytest.mark.parametrize("changes, code", [
    ({"membership_type": None}, "unknown_membership_type"),
    ({"name": "=HYPERLINK(\"x\")"}, "name_looks_like_formula"),
    ({"name": "+91 Ravi"}, "name_looks_like_formula"),
    ({"name": "-Ravi"}, "name_looks_like_formula"),
    ({"name": "@Ravi"}, "name_looks_like_formula"),
    ({"amount_text": "10000000.01"}, "amount_too_large"),
    ({"instalments_text": "121"}, "invalid_instalments"),
], ids=["no-type", "equals", "plus", "minus", "at", "amount-cap", "instalments-cap"])
def test_round_1_errors(book1, changes, code):
    result = check(book1, **changes)
    assert not result.accepted and code in [i.code for i in result.errors]


def test_the_upper_bounds_themselves_are_allowed(book1):
    assert check(book1, amount_text="10000000", instalments_text="120").accepted


def test_a_name_with_a_hyphen_or_apostrophe_inside_is_fine(book1):
    assert check(book1, name="Mary-Ann D'Souza").accepted


def test_membership_ids_made_of_member_ids_do_not_file_the_newcomer_under_another_member():
    rows = [
        {"member_id": "M001", "member_name": "Asha", "membership_id": "M001-01"},
        {"member_id": "M001", "member_name": "Asha", "membership_id": "M001-02"},
        {"member_id": "M002", "member_name": "Ravi", "membership_id": "M002-01"},
    ]
    for row in rows:
        row.update(membership_type="Monthly", date_joined="2026-11-01",
                   membership_amount="2000", instalments="1", paid_amount="0")
    result = check_new_member(rows, list(rows[0]), [], form(), TODAY)
    assert (result.row["member_id"], result.row["membership_id"]) == ("M003", "M003-01")


def test_a_gym_wide_membership_numbering_is_still_continued(book1):
    assert check(book1).row["membership_id"] == "MS-027"


# --- Fix round 2 -------------------------------------------------------------------------

def test_a_name_may_be_100_characters_but_not_more(book1):
    assert check(book1, name="A" * 100).accepted
    assert [i.code for i in check(book1, name="A" * 101).errors] == ["name_too_long"]


def test_a_refused_same_name_shows_only_the_error_not_the_warning_too():
    rows = [{"member_name": "Asha", "membership_type": "Monthly", "date_joined": "2026-11-01",
             "membership_amount": "2000", "instalments": "1", "paid_amount": "0"}]
    result = check_new_member(rows, list(rows[0]), [], form(name="Asha"), TODAY)
    assert [i.code for i in result.issues] == ["duplicate_name_without_id"]
