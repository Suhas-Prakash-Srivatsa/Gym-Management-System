"""Independent acceptance tests for the ticket 05 follow-up (shared identity scheme,
duplicate Membership IDs, ASCII-only instalments), written by the tester."""

from pathlib import Path

import pytest

from src.assemble import build_dataset
from src.identity import effective_membership_ids
from src.sheet import read_rows
from src.validation import Fix, apply_fixes, check_duplicate_membership_ids, validate

FILES = Path(__file__).resolve().parent.parent / "src" / "files"


def base(**kw):
    r = {
        "member_id": "M001", "member_name": "Suhas Prakash", "membership_id": "MS-1",
        "membership_type": "Yearly", "date_joined": "2026-06-01", "membership_amount": "12000",
        "instalments": "2", "paid_amount": "6000", "last_payment_date": "2026-06-01",
    }
    r.update(kw)
    return r


COLS = list(base())
BLANK = {k: "" for k in COLS}


def test_two_rows_one_typed_id_for_different_members_is_not_clean():
    rows = [base(), base(member_id="M002", member_name="Vandana Rao")]
    report = validate(rows, COLS)
    assert [(i.code, i.related_rows) for i in report.issues] == [("duplicate_membership_id", (1, 2))]


def test_generated_id_colliding_with_typed_id_is_not_clean():
    rows = [base(membership_id=""), base(membership_id="M001-01", date_joined="2026-07-01")]
    assert not validate(rows, COLS).is_clean


@pytest.mark.parametrize("row_to_fix", [1, 2])
def test_entering_a_new_id_on_either_row_clears_the_duplicate(row_to_fix):
    rows = [base(membership_id=""), base(membership_id="M001-01")]
    fixed = apply_fixes(rows, [Fix(row_to_fix, "membership_id", "enter_manually", "MS-7")])
    assert validate(fixed, COLS).is_clean
    ids = [ms.membership_id for ms in build_dataset(fixed).memberships]
    assert len(set(ids)) == 2 and "MS-7" in ids


def test_entering_another_colliding_id_stays_dirty():
    rows = [base(), base(member_id="M002", member_name="Vandana Rao"),
            base(member_id="M003", member_name="Arjun Menon", membership_id="MS-3")]
    fixed = apply_fixes(rows, [Fix(1, "membership_id", "enter_manually", " MS-3 ")])
    assert [i.related_rows for i in validate(fixed, COLS).issues] == [(1, 3)]


def test_several_blank_rows_are_never_a_duplicate():
    rows = [base(), BLANK, dict(BLANK), {k: "  " for k in COLS}, base(membership_id="MS-2")]
    assert check_duplicate_membership_ids(rows) == []
    assert validate(rows, COLS).is_clean


def test_book1_with_trailing_blank_rows_stays_clean_and_unique():
    rows, columns = read_rows(FILES / "Book1.csv")
    padded = rows + [dict.fromkeys(rows[0], "")] * 3
    assert validate(padded, columns).is_clean
    without_ids = [{k: v for k, v in r.items() if k != "membership_id"} for r in padded]
    assert validate(without_ids, [c for c in columns if c != "membership_id"]).is_clean
    ids = [ms.membership_id for ms in build_dataset(without_ids).memberships]
    assert len(ids) == len(set(ids)) == 26


def test_book1_errors_still_gives_nine_issues():
    rows, columns = read_rows(FILES / "Book1_errors.csv")
    assert len(validate(rows, columns).issues) == 9


@pytest.mark.parametrize("raw", ["²", "２", "١", "2²", " ", "+2", "2.0"])
def test_non_ascii_or_non_integer_instalments_are_an_issue_not_a_crash(raw):
    report = validate([base(instalments=raw)], COLS)
    assert [i.code for i in report.issues] == ["invalid_instalments"]


def test_assembly_uses_exactly_the_ids_validation_checked():
    rows = [base(membership_id=""), BLANK, base(membership_id=" MS-5 "), base(membership_id="")]
    effective = [i for i in effective_membership_ids(rows) if i is not None]
    assert [ms.membership_id for ms in build_dataset(rows).memberships] == effective
    assert effective == ["M001-01", "MS-5", "M001-03"]


def test_membership_ids_are_compared_case_sensitively():
    # Business decision pinned: MS-1 and ms-1 are two contracts, each owning only
    # its own Payments, so no receivable is hidden. Change this deliberately.
    rows = [base(), base(membership_id="ms-1")]
    assert validate(rows, COLS).is_clean
    ds = build_dataset(rows)
    assert {p.membership_id for p in ds.payments} == {"MS-1", "ms-1"}
