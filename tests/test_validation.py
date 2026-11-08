from datetime import date
from pathlib import Path

import pytest

from src.sheet import read_rows
from src.validation import (
    Fix,
    FixPreview,
    Issue,
    Report,
    apply_fixes,
    check_amounts,
    check_dates,
    check_duplicate_membership_ids,
    check_duplicate_names,
    check_instalments,
    check_last_payment_date,
    check_membership_type,
    check_member_name,
    check_required_columns,
    fix_for,
    is_blank_row,
    preview_fix,
    validate,
)

FILES = Path(__file__).resolve().parent.parent / "src" / "files"


def row(**overrides):
    base = {
        "member_id": "M001",
        "member_name": "Suhas Prakash",
        "membership_id": "MS-001",
        "membership_type": "Yearly",
        "date_joined": "2026-06-01",
        "membership_amount": "12000",
        "instalments": "2",
        "paid_amount": "6000",
        "last_payment_date": "2026-06-01",
    }
    return {**base, **overrides}


def test_yearless_date_offers_infer_current_year_or_enter_manually():
    issues = check_dates(row(date_joined="1st June"), 1)
    assert [(i.row_number, i.column, i.code, i.fix_options) for i in issues] == [
        (1, "date_joined", "date_missing_year", ("infer_current_year", "enter_manually")),
    ]
    assert "1st June" in issues[0].message


def codes(issues):
    return [(i.column, i.code, i.fix_options) for i in issues]


def test_yearless_last_payment_date_is_also_a_date_issue():
    assert codes(check_dates(row(last_payment_date="1st September"), 1)) == [
        ("last_payment_date", "date_missing_year", ("infer_current_year", "enter_manually")),
    ]


@pytest.mark.parametrize("raw", ["01/06/26", "0026-06-01", "soon", "31 June 2026"])
def test_short_year_or_unreadable_date_is_only_correctable_by_hand(raw):
    # The century is never guessed, so there is nothing to infer.
    assert codes(check_dates(row(date_joined=raw), 3)) == [
        ("date_joined", "date_invalid", ("enter_manually",)),
    ]


def test_empty_date_joined_is_an_issue_but_empty_last_payment_date_is_left_to_its_own_rule():
    assert codes(check_dates(row(date_joined="", last_payment_date=""), 2)) == [
        ("date_joined", "date_missing", ("enter_manually",)),
    ]


def test_valid_dates_raise_nothing():
    assert check_dates(row(date_joined=" 1 June 2026 ", last_payment_date="01/06/2026"), 1) == []


@pytest.mark.parametrize("raw", ["Quarterly", "", "Annual"])
def test_unrecognised_membership_type_must_be_corrected(raw):
    issues = check_membership_type(row(membership_type=raw), 6)
    assert codes(issues) == [("membership_type", "unknown_membership_type", ("enter_manually",))]
    assert "Monthly, Half-Yearly, Yearly" in issues[0].message


@pytest.mark.parametrize(
    "raw", ["Monthly", "Half-Yearly", " Yearly ", "yearly", "YEARLY", "Half Yearly", "half_yearly"]
)
def test_known_membership_types_pass(raw):
    assert check_membership_type(row(membership_type=raw), 1) == []


@pytest.mark.parametrize("raw", ["0", "-1", "1.5", "two", "", "²", "2²", "١"])
def test_instalments_below_one_or_not_an_integer_must_be_corrected(raw):
    assert codes(check_instalments(row(instalments=raw), 5)) == [
        ("instalments", "invalid_instalments", ("enter_manually",)),
    ]


@pytest.mark.parametrize("raw", ["1", " 3 "])
def test_whole_instalments_of_at_least_one_pass(raw):
    assert check_instalments(row(instalments=raw), 1) == []


def test_superscript_instalments_are_reported_not_a_crash():
    report = validate([row(instalments="²")], list(row()))
    assert [i.code for i in report.issues] == ["invalid_instalments"]


def test_paid_more_than_contract_must_be_corrected():
    issues = check_amounts(row(membership_amount="12000", paid_amount="15000"), 5)
    assert codes(issues) == [("paid_amount", "paid_exceeds_contract", ("enter_manually",))]
    assert "15000" in issues[0].message and "12000" in issues[0].message


@pytest.mark.parametrize(
    "overrides, column",
    [
        ({"membership_amount": "abc"}, "membership_amount"),
        ({"membership_amount": ""}, "membership_amount"),
        ({"paid_amount": "-500"}, "paid_amount"),
        ({"paid_amount": ""}, "paid_amount"),
    ],
)
def test_unreadable_or_negative_amounts_must_be_corrected(overrides, column):
    assert codes(check_amounts(row(**overrides), 1)) == [(column, "invalid_amount", ("enter_manually",))]


@pytest.mark.parametrize("paid", ["0", "₹12,000", "6000"])
def test_paid_up_to_the_contract_amount_passes(paid):
    assert check_amounts(row(membership_amount="12,000", paid_amount=paid), 1) == []


def test_paid_without_last_payment_date_offers_date_joined_or_enter_manually():
    issues = check_last_payment_date(row(paid_amount="8000", last_payment_date=""), 2)
    assert codes(issues) == [
        ("last_payment_date", "last_payment_date_missing", ("use_date_joined", "enter_manually")),
    ]


@pytest.mark.parametrize("paid, last", [("0", ""), ("6000", "2026-06-01"), ("abc", "")])
def test_last_payment_date_not_required_when_nothing_was_paid_or_amount_is_unreadable(paid, last):
    # An unreadable Paid Amount is check_amounts' issue, not this rule's.
    assert check_last_payment_date(row(paid_amount=paid, last_payment_date=last), 1) == []


def test_missing_last_payment_date_column_counts_as_empty():
    r = row(paid_amount="500")
    del r["last_payment_date"]
    assert codes(check_last_payment_date(r, 1))[0][1] == "last_payment_date_missing"


CANONICAL = list(row().keys())


def test_full_canonical_columns_raise_nothing():
    assert check_required_columns(CANONICAL) == []


def test_member_id_membership_id_and_last_payment_date_columns_are_optional():
    optional = {"member_id", "membership_id", "last_payment_date"}
    assert check_required_columns([c for c in CANONICAL if c not in optional]) == []


def test_missing_required_column_is_sheet_level_and_not_fixable():
    issues = check_required_columns([c for c in CANONICAL if c != "membership_amount"])
    assert [(i.row_number, i.column, i.code, i.fix_options) for i in issues] == [
        (None, "membership_amount", "missing_column", ()),
    ]
    assert "Membership Amount" in issues[0].message


def test_blank_header_row_is_missing_every_required_column():
    issues = check_required_columns(["", "", ""])
    assert {i.code for i in issues} == {"missing_column"}
    assert len(issues) == 6


def test_two_headers_meaning_the_same_column_is_ambiguous():
    # e.g. a sheet with both "Name" and "Member Name"
    issues = check_required_columns(CANONICAL + ["member_name"])
    assert [(i.row_number, i.column, i.code, i.fix_options) for i in issues] == [
        (None, "member_name", "ambiguous_column", ()),
    ]


def test_duplicate_name_without_member_id_asks_same_person_or_different_people():
    rows = [
        row(member_id="", member_name="Rakesh Sharma", membership_id="MS-103"),
        row(member_id="", member_name="Anita Rao", membership_id="MS-105"),
        row(member_id="", member_name=" rakesh  sharma", membership_id="MS-104"),
    ]
    issues = check_duplicate_names(rows)
    assert [(i.row_number, i.column, i.code, i.fix_options, i.related_rows) for i in issues] == [
        (1, "member_name", "duplicate_name", ("same_person", "different_people"), (1, 3)),
    ]
    assert "renewal" in issues[0].message


def test_repeated_name_is_fine_when_member_ids_say_who_is_who():
    rows = [row(member_id="M001"), row(member_id="M001"), row(member_id="M007")]
    assert check_duplicate_names(rows) == []


def test_unique_names_without_member_ids_raise_nothing():
    rows = [row(member_id="", member_name="Suhas"), row(member_id="", member_name="Vandana")]
    assert check_duplicate_names(rows) == []


def test_a_row_of_only_blank_cells_is_blank():
    assert is_blank_row({c: "" for c in CANONICAL})
    assert is_blank_row({"member_name": "  ", "paid_amount": ""})
    assert not is_blank_row(row())
    assert not is_blank_row({c: "" for c in CANONICAL} | {"paid_amount": "0"})


def test_empty_member_name_must_be_entered():
    assert codes(check_member_name(row(member_name="  "), 4)) == [
        ("member_name", "missing_member_name", ("enter_manually",)),
    ]
    assert check_member_name(row(), 1) == []


def test_clean_book1_produces_an_empty_non_fatal_report():
    report = validate(*read_rows(FILES / "Book1.csv"))
    assert report.issues == ()
    assert report.is_fatal is False
    assert report.is_clean is True


def test_blank_rows_are_skipped_but_keep_their_row_numbers():
    rows = [row(), {c: "" for c in CANONICAL}, row(membership_id="MS-002", instalments="0")]
    report = validate(rows, CANONICAL)
    assert [(i.row_number, i.code) for i in report.issues] == [(3, "invalid_instalments")]


def test_missing_required_column_makes_the_report_fatal_without_row_noise():
    columns = [c for c in CANONICAL if c != "membership_type"]
    rows = [{c: v for c, v in row().items() if c != "membership_type"}]
    report = validate(rows, columns)
    assert [i.code for i in report.issues] == ["missing_column"]
    assert report.is_fatal is True
    assert report.is_clean is False


@pytest.fixture
def error_report():
    return validate(*read_rows(FILES / "Book1_errors.csv"))


def by(report, row_number, code):
    return [i for i in report.issues if i.row_number == row_number and i.code == code]


def test_error_fixture_blocks_the_dashboard_but_is_fixable(error_report):
    assert error_report.is_clean is False
    assert error_report.is_fatal is False


def test_error_fixture_yearless_dates_offer_infer_current_year(error_report):
    yearless = [(i.row_number, i.column) for i in error_report.issues if i.code == "date_missing_year"]
    assert yearless == [(1, "date_joined"), (1, "last_payment_date"), (2, "date_joined")]
    assert all("infer_current_year" in i.fix_options
               for i in error_report.issues if i.code == "date_missing_year")


def test_error_fixture_vandana_paid_without_last_payment_date_offers_date_joined(error_report):
    [issue] = by(error_report, 2, "last_payment_date_missing")
    assert "use_date_joined" in issue.fix_options


def test_error_fixture_rakesh_sharma_twice_is_one_duplicate_name_question(error_report):
    [issue] = [i for i in error_report.issues if i.code == "duplicate_name"]
    assert issue.related_rows == (3, 4)
    assert issue.fix_options == ("same_person", "different_people")


def test_error_fixture_anita_rao_has_bad_instalments_and_overpayment(error_report):
    assert len(by(error_report, 5, "invalid_instalments")) == 1
    assert len(by(error_report, 5, "paid_exceeds_contract")) == 1


def test_error_fixture_vinod_bhatt_quarterly_is_unrecognised(error_report):
    assert len(by(error_report, 6, "unknown_membership_type")) == 1


def test_error_fixture_full_issue_list(error_report):
    # Beyond the ticket's one-per-rule list, Rakesh's MS-103 (row 3) also has
    # Paid 4000 with no Last Payment Date.
    assert [(i.row_number, i.column, i.code) for i in error_report.issues] == [
        (1, "date_joined", "date_missing_year"),
        (1, "last_payment_date", "date_missing_year"),
        (2, "date_joined", "date_missing_year"),
        (2, "last_payment_date", "last_payment_date_missing"),
        (3, "last_payment_date", "last_payment_date_missing"),
        (5, "paid_amount", "paid_exceeds_contract"),
        (5, "instalments", "invalid_instalments"),
        (6, "membership_type", "unknown_membership_type"),
        (3, "member_name", "duplicate_name"),
    ]


def test_infer_current_year_returns_corrected_copies_and_leaves_input_unmutated():
    rows = [row(date_joined="1st June", last_payment_date="1st September"), row()]
    snapshot = [dict(r) for r in rows]
    fixed = apply_fixes(
        rows,
        [Fix(1, "date_joined", "infer_current_year"),
         Fix(1, "last_payment_date", "infer_current_year")],
        current_year=2026,
    )
    assert rows == snapshot
    assert fixed[0]["date_joined"] == "2026-06-01"
    assert fixed[0]["last_payment_date"] == "2026-09-01"
    assert fixed[1] == snapshot[1]
    assert fixed[0] is not rows[0] and fixed[1] is not rows[1]


def test_enter_manually_writes_the_typed_value():
    fixed = apply_fixes([row(membership_type="Quarterly")],
                        [Fix(1, "membership_type", "enter_manually", "Half-Yearly")])
    assert fixed[0]["membership_type"] == "Half-Yearly"


def test_use_date_joined_copies_the_corrected_join_date_whatever_the_fix_order():
    rows = [row(date_joined="5th August", paid_amount="8000", last_payment_date="")]
    fixed = apply_fixes(
        rows,
        [Fix(1, "last_payment_date", "use_date_joined"),
         Fix(1, "date_joined", "infer_current_year")],
        current_year=2026,
    )
    assert fixed[0]["date_joined"] == "2026-08-05"
    assert fixed[0]["last_payment_date"] == "2026-08-05"


def rakesh_rows():
    return [
        row(member_id="", member_name="Rakesh Sharma", membership_id="MS-103"),
        row(member_id="GEN-001", member_name="Anita Rao", membership_id="MS-105"),
        row(member_id="", member_name="Rakesh Sharma", membership_id="MS-104"),
    ]


def test_same_person_answer_writes_one_generated_member_id_onto_every_row():
    fixed = apply_fixes(rakesh_rows(), [Fix(1, "member_name", "same_person")])
    assert fixed[0]["member_id"] == fixed[2]["member_id"]
    assert fixed[0]["member_id"] not in ("", "GEN-001")  # never collides with a real ID
    assert fixed[1]["member_id"] == "GEN-001"


def test_different_people_answer_writes_a_distinct_member_id_per_row():
    fixed = apply_fixes(rakesh_rows(), [Fix(1, "member_name", "different_people")])
    ids = {fixed[0]["member_id"], fixed[2]["member_id"], fixed[1]["member_id"]}
    assert len(ids) == 3 and "" not in ids


def test_answered_duplicate_names_no_longer_raise_an_issue():
    for option in ("same_person", "different_people"):
        assert check_duplicate_names(apply_fixes(rakesh_rows(), [Fix(1, "member_name", option)])) == []


@pytest.mark.parametrize(
    "fix, kwargs",
    [
        (Fix(1, "date_joined", "infer_current_year"), {}),  # no year supplied
        (Fix(1, "date_joined", "infer_current_year"), {"current_year": 2026}),  # "soon" has no day/month
        (Fix(1, "membership_type", "enter_manually"), {}),  # nothing typed
        (Fix(1, "membership_type", "guess"), {}),  # not an option
        (Fix(0, "membership_type", "enter_manually", "Yearly"), {}),  # no row 0
        (Fix(2, "membership_type", "enter_manually", "Yearly"), {}),  # past the last row
        (Fix(1, "member_name", "same_person"), {}),  # row has a Member ID: nothing to answer
    ],
)
def test_apply_fixes_rejects_answers_it_cannot_apply(fix, kwargs):
    with pytest.raises(ValueError):
        apply_fixes([row(date_joined="soon")], [fix], **kwargs)


def test_answering_every_error_fixture_question_yields_a_clean_report():
    rows, columns = read_rows(FILES / "Book1_errors.csv")
    fixes = [
        Fix(1, "date_joined", "infer_current_year"),
        Fix(1, "last_payment_date", "infer_current_year"),
        Fix(2, "date_joined", "infer_current_year"),
        Fix(2, "last_payment_date", "use_date_joined"),
        Fix(3, "last_payment_date", "enter_manually", "2026-07-01"),
        Fix(3, "member_name", "different_people"),
        Fix(5, "instalments", "enter_manually", "2"),
        Fix(5, "paid_amount", "enter_manually", "12000"),
        Fix(6, "membership_type", "enter_manually", "Half-Yearly"),
    ]
    fixed = apply_fixes(rows, fixes, current_year=2026)
    assert validate(fixed, columns).is_clean
    assert fixed[1]["last_payment_date"] == "2026-08-05"


def mixed_suhas_rows():
    return [
        row(member_id="M001", member_name="Suhas Prakash", membership_id="MS-001"),
        row(member_id="M002", member_name="Vandana Rao", membership_id="MS-002"),
        row(member_id="", member_name="suhas prakash", membership_id="MS-025"),
    ]


def test_name_repeated_where_some_rows_lack_member_id_is_still_asked():
    issues = check_duplicate_names(mixed_suhas_rows())
    assert [(i.row_number, i.code, i.fix_options, i.related_rows) for i in issues] == [
        (1, "duplicate_name", ("same_person", "different_people"), (1, 3)),
    ]


def test_same_person_reuses_the_one_member_id_already_in_the_group():
    fixed = apply_fixes(mixed_suhas_rows(), [Fix(1, "member_name", "same_person")])
    assert [r["member_id"] for r in fixed] == ["M001", "M002", "M001"]


def test_different_people_keeps_existing_ids_and_generates_for_the_rest():
    fixed = apply_fixes(mixed_suhas_rows(), [Fix(1, "member_name", "different_people")])
    assert fixed[0]["member_id"] == "M001"
    assert fixed[2]["member_id"] not in ("", "M001", "M002")
    assert check_duplicate_names(fixed) == []


def test_same_person_is_refused_when_the_group_already_carries_conflicting_ids():
    rows = mixed_suhas_rows() + [row(member_id="M009", member_name="Suhas Prakash")]
    with pytest.raises(ValueError, match="M001.*M009|M009.*M001"):
        apply_fixes(rows, [Fix(1, "member_name", "same_person")])


def test_group_already_carrying_conflicting_ids_offers_only_different_people():
    rows = mixed_suhas_rows() + [row(member_id="M009", member_name="Suhas Prakash")]
    [issue] = check_duplicate_names(rows)
    assert issue.related_rows == (1, 3, 4)
    assert issue.fix_options == ("different_people",)
    fixed = apply_fixes(rows, [Fix(1, "member_name", issue.fix_options[0])])
    assert check_duplicate_names(fixed) == []


# --- Duplicate Membership IDs: two rows one contract would hide receivable ---


def test_rows_sharing_a_typed_membership_id_are_flagged_once_naming_every_row():
    rows = [row(membership_id="MS-1"), row(member_id="M002", member_name="Vandana Rao",
                                           membership_id="MS-2"),
            row(membership_id=" MS-1 "), row(member_id="M003", member_name="Arjun Menon",
                                             membership_id="MS-1")]
    issues = check_duplicate_membership_ids(rows)
    assert [(i.row_number, i.column, i.code, i.fix_options, i.related_rows) for i in issues] == [
        (1, "membership_id", "duplicate_membership_id", ("enter_manually",), (1, 3, 4)),
    ]
    assert "MS-1" in issues[0].message and "1, 3, 4" in issues[0].message


def test_generated_membership_id_colliding_with_a_typed_one_is_flagged():
    # Row 1 has no ID, so assembly would call it M001-01: the ID typed on row 2.
    rows = [row(membership_id=""), row(membership_id="M001-01")]
    issues = check_duplicate_membership_ids(rows)
    assert [(i.code, i.related_rows) for i in issues] == [("duplicate_membership_id", (1, 2))]
    assert "M001-01" in issues[0].message


def test_distinct_and_generated_membership_ids_pass():
    rows = [row(membership_id=""), row(membership_id=""), row(membership_id="MS-9")]
    assert check_duplicate_membership_ids(rows) == []


def test_blank_rows_are_ignored_but_counted_for_duplicate_membership_ids():
    blank = {k: "" for k in row()}
    rows = [row(membership_id="MS-1"), blank, row(membership_id="MS-1")]
    assert [i.related_rows for i in check_duplicate_membership_ids(rows)] == [(1, 3)]


def test_validate_reports_duplicate_membership_ids():
    report = validate([row(), row()], list(row()))
    assert [i.code for i in report.issues] == ["duplicate_membership_id"]
    assert not report.is_clean


def test_entering_a_new_membership_id_resolves_the_duplicate():
    rows = [row(membership_id="MS-1"), row(membership_id="MS-1")]
    issue = check_duplicate_membership_ids(rows)[0]
    fixed = apply_fixes(rows, [Fix(issue.row_number, issue.column, "enter_manually", "MS-7")])
    assert validate(fixed, list(row())).is_clean


def test_a_report_with_only_warnings_is_still_clean():
    warning = Issue(1, "paid_on", "some_warning", "Look again.", severity="warning")
    error = Issue(1, "member_name", "missing_member_name", "Row 1: Member Name is empty.")
    assert Report((warning,), is_fatal=False).is_clean
    assert not Report((warning, error), is_fatal=False).is_clean


# --- Helpers the app's fix form calls, so app.py holds no rules ---

TODAY = date(2026, 11, 8)


def test_fix_for_turns_an_answer_into_a_fix():
    issue = Issue(3, "instalments", "invalid_instalments", "…", ("enter_manually",))
    assert fix_for(issue, "enter_manually", " 2 ") == Fix(3, "instalments", "enter_manually", "2")
    choice = Issue(1, "date_joined", "date_missing_year", "…",
                   ("infer_current_year", "enter_manually"))
    assert fix_for(choice, "infer_current_year", None) == Fix(1, "date_joined", "infer_current_year")


@pytest.mark.parametrize("option, value", [(None, None), (None, "x"),
                                           ("enter_manually", ""), ("enter_manually", "   "),
                                           ("enter_manually", None)])
def test_an_unanswered_question_is_no_fix(option, value):
    issue = Issue(1, "date_joined", "date_missing_year", "…", ("infer_current_year", "enter_manually"))
    assert fix_for(issue, option, value) is None


def test_fix_for_refuses_an_option_the_issue_does_not_offer():
    issue = Issue(1, "date_joined", "date_missing_year", "…", ("infer_current_year", "enter_manually"))
    with pytest.raises(ValueError):
        fix_for(issue, "same_person", None)


def test_preview_shows_what_infer_current_year_will_write():
    rows = [row(date_joined="1st June")]
    issue = check_dates(rows[0], 1)[0]
    assert preview_fix(rows, issue, "infer_current_year", today=TODAY) == FixPreview(
        "Becomes 2026-06-01.", warning=False)


def test_preview_warns_when_the_inferred_date_is_in_the_future():
    rows = [row(), row(date_joined="25 December")]
    issue = check_dates(rows[1], 2)[0]
    preview = preview_fix(rows, issue, "infer_current_year", today=TODAY)
    assert preview.warning is True
    assert "2026-12-25" in preview.message and "future" in preview.message


def test_other_options_have_no_preview():
    rows = [row(date_joined="1st June")]
    issue = check_dates(rows[0], 1)[0]
    assert preview_fix(rows, issue, "enter_manually", today=TODAY) is None
    assert preview_fix(rows, issue, None, today=TODAY) is None


def test_sheet_level_messages_do_not_assume_an_upload():
    issues = check_required_columns(["member_name", "member_name"])
    assert issues and all("upload" not in i.message for i in issues)
    assert all("reload" in i.message for i in issues)
