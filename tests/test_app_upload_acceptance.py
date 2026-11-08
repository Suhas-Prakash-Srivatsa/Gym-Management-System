"""Independent acceptance tests for ticket 10 (upload and in-dashboard fixing), by the tester.

Driven through Streamlit's AppTest in path mode on COPIES of the fixtures in
tmp_path, with GYM_TODAY pinned. save_upload is exercised directly, because
AppTest cannot drive st.file_uploader.
"""

import os
import shutil
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src.sidecar import clean_members_path, save_upload

ROOT = Path(__file__).resolve().parent.parent
FILES = ROOT / "src" / "files"
APP = str(ROOT / "app.py")

HEADER = ("Member ID,Member Name,Membership ID,Membership Type,Date Joined,"
          "Membership Amount,Installments,Paid Amount,Last Payment Date\n")


@pytest.fixture(autouse=True)
def pinned(monkeypatch):
    monkeypatch.setenv("GYM_TODAY", "2026-11-08")


@pytest.fixture
def errors_sheet(tmp_path):
    path = tmp_path / "gym" / "Book1_errors.csv"
    path.parent.mkdir()
    shutil.copy(FILES / "Book1_errors.csv", path)
    return path


@pytest.fixture
def book1(tmp_path):
    path = tmp_path / "gym" / "Book1.csv"
    path.parent.mkdir()
    shutil.copy(FILES / "Book1.csv", path)
    return path


def fp(path):
    return path.read_bytes(), os.stat(path).st_mtime_ns


def start(monkeypatch, sheet):
    monkeypatch.setenv("GYM_SHEET", str(sheet))
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def issue_tables(at):
    """The validation-issues table(s): the dashboard also shows a table since ticket 11."""
    return [d for d in at.dataframe if "Problem" in d.value.columns]


def step(at):
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def all_text(at):
    parts = [e.value for kind in (at.error, at.warning, at.info, at.caption, at.markdown)
             for e in kind]
    return " ".join(str(p) for p in parts)


def answer_everything(at, rakesh="different_people"):
    for key, option in {
        "date_missing_year:1:date_joined": "infer_current_year",
        "date_missing_year:1:last_payment_date": "infer_current_year",
        "date_missing_year:2:date_joined": "infer_current_year",
        "last_payment_date_missing:2:last_payment_date": "use_date_joined",
        "last_payment_date_missing:3:last_payment_date": "use_date_joined",
        "duplicate_name:3:member_name": rakesh,
    }.items():
        at.radio(key=f"{key}:option").set_value(option)
    for key, value in {
        "invalid_instalments:5:instalments": "1",
        "paid_exceeds_contract:5:paid_amount": "12000",
        "unknown_membership_type:6:membership_type": "half yearly",
    }.items():
        at.text_input(key=f"{key}:value").input(value)
    step(at)  # the browser reruns on every answer, enabling Apply
    at.button(key="apply_fixes").click()
    return step(at)


# --- Gating ---------------------------------------------------------------------

def test_clean_sheet_goes_straight_to_tiles(monkeypatch, book1):
    before = fp(book1)
    at = start(monkeypatch, book1)
    assert {m.label: m.value for m in at.metric}["Total Receivable"] == "₹97,300"
    assert not at.error and not issue_tables(at) and not at.info
    assert not clean_members_path(book1).exists()
    assert fp(book1) == before


def test_error_sheet_lists_every_issue_with_row_column_value_and_problem(monkeypatch, errors_sheet):
    at = start(monkeypatch, errors_sheet)
    assert not at.metric
    table = at.dataframe[0].value
    assert list(table.columns) == ["Row", "Column", "Value", "Problem"]
    assert len(table) == 9
    # Every offending data row of the fixture is surfaced (row 4 via the duplicate).
    assert set(table["Row"]) == {"1", "2", "3", "5", "6"}
    assert "Rows 3, 4" in " ".join(table["Problem"])
    assert {"Date Joined", "Last Payment Date", "Paid Amount", "Installments",
            "Membership Type", "Member Name"} <= set(table["Column"])
    assert "1st June" in set(table["Value"]) and "Quarterly" in set(table["Value"])
    assert "9 problem" in all_text(at)


def test_owner_questions_start_unanswered_and_nothing_is_written(monkeypatch, errors_sheet):
    at = start(monkeypatch, errors_sheet)
    assert at.radio(key="duplicate_name:3:member_name:option").value is None
    assert at.radio(key="date_missing_year:1:date_joined:option").value is None
    assert all(r.value is None for r in at.radio if r.key != "mode")
    assert at.button(key="apply_fixes").disabled
    # Typing a value without picking "Type the correct value" is still no answer.
    at.text_input(key="date_missing_year:1:date_joined:value").input("2026-06-01")
    step(at)
    assert at.button(key="apply_fixes").disabled
    assert not clean_members_path(errors_sheet).exists()


def test_future_year_preview_warns(monkeypatch, tmp_path):
    sheet = tmp_path / "gym" / "s.csv"
    sheet.parent.mkdir()
    sheet.write_text(HEADER + "M1,A,MS-1,Yearly,25th December,12000,2,0,\n", encoding="utf-8")
    at = start(monkeypatch, sheet)
    at.radio(key="date_missing_year:1:date_joined:option").set_value("infer_current_year")
    step(at)
    assert "2026-12-25" in " ".join(w.value for w in at.warning)
    assert "future" in " ".join(w.value for w in at.warning)


# --- Full flow --------------------------------------------------------------------

def test_ticket_flow_then_rerun_asks_nothing_and_the_sheet_never_changes(monkeypatch, errors_sheet):
    before = fp(errors_sheet)
    at = answer_everything(start(monkeypatch, errors_sheet))
    assert {m.label: m.value for m in at.metric} == {
        "Total Members": "6", "Total Membership Value": "₹65,000",
        "Total Receivable": "₹32,000", "Overdue": "₹32,000"}
    assert "corrected data" in " ".join(i.value for i in at.info)
    assert clean_members_path(errors_sheet).exists()

    again = start(monkeypatch, errors_sheet)  # a fresh session: a later run
    assert again.metric and not issue_tables(again)
    assert not [r for r in again.radio if r.key != "mode"] and not again.text_input(
        key="sheet_path").value == ""
    assert "corrected data" in " ".join(i.value for i in again.info)
    assert fp(errors_sheet) == before


def test_same_person_makes_one_member(monkeypatch, errors_sheet):
    at = answer_everything(start(monkeypatch, errors_sheet), rakesh="same_person")
    assert {m.label: m.value for m in at.metric}["Total Members"] == "5"


def test_an_invalid_typed_correction_is_asked_again_not_accepted(monkeypatch, errors_sheet):
    at = start(monkeypatch, errors_sheet)
    at.text_input(key="invalid_instalments:5:instalments:value").input("zero")
    step(at)
    at.button(key="apply_fixes").click()
    step(at)
    assert not at.metric
    problems = " ".join(at.dataframe[0].value["Problem"])
    assert "Installments 'zero'" in problems


# --- Stale corrections ---------------------------------------------------------------

def make_stale(sheet):
    clean = clean_members_path(sheet)
    t = os.stat(clean).st_mtime_ns + 10_000_000_000
    os.utime(sheet, ns=(t, t))  # the owner edited the sheet after correcting
    return fp(sheet)


def test_stale_corrections_block_until_answered(monkeypatch, errors_sheet):
    answer_everything(start(monkeypatch, errors_sheet))
    make_stale(errors_sheet)
    at = start(monkeypatch, errors_sheet)
    assert not at.metric and not at.dataframe  # no table of any kind
    assert "changed since your corrections" in " ".join(w.value for w in at.warning)


def test_keep_corrections_touches_only_the_sidecar(monkeypatch, errors_sheet):
    answer_everything(start(monkeypatch, errors_sheet))
    sheet_fp = make_stale(errors_sheet)
    clean_bytes = clean_members_path(errors_sheet).read_bytes()
    at = start(monkeypatch, errors_sheet)
    at.button(key="keep_corrections").click()
    step(at)
    assert at.metric and "corrected data" in " ".join(i.value for i in at.info)
    assert clean_members_path(errors_sheet).read_bytes() == clean_bytes
    assert fp(errors_sheet) == sheet_fp
    assert start(monkeypatch, errors_sheet).metric  # no longer stale on a later run


def test_discard_keeps_a_backup_and_returns_to_the_sheet(monkeypatch, errors_sheet):
    answer_everything(start(monkeypatch, errors_sheet))
    sheet_fp = make_stale(errors_sheet)
    clean = clean_members_path(errors_sheet)
    clean_bytes = clean.read_bytes()
    at = start(monkeypatch, errors_sheet)
    at.button(key="discard_corrections").click()
    step(at)
    assert not clean.exists()
    [backup] = clean.parent.glob("members_clean.csv.*.bak")  # timestamped since ticket 11
    assert backup.read_bytes() == clean_bytes
    assert not at.metric and len(at.dataframe[0].value) == 9
    assert fp(errors_sheet) == sheet_fp


# --- Errors are messages ----------------------------------------------------------------

def test_fatal_missing_column_stops_with_instructions(monkeypatch, tmp_path):
    sheet = tmp_path / "gym" / "s.csv"
    sheet.parent.mkdir()
    sheet.write_text("Member Name,Membership Type,Date Joined,Membership Amount,Installments\n"
                     "A,Yearly,2026-01-01,1000,1\n", encoding="utf-8")
    at = start(monkeypatch, sheet)
    assert not at.metric and not at.button and not [r for r in at.radio if r.key != "mode"]
    text = " ".join(e.value for e in at.error)
    assert "Paid Amount" in " ".join(at.dataframe[0].value["Problem"])
    assert "add or rename the column" in text


def test_a_sheet_named_like_a_sidecar_is_refused(monkeypatch, tmp_path):
    sheet = tmp_path / "gym" / "members_clean.csv"
    sheet.parent.mkdir()
    shutil.copy(FILES / "Book1.csv", sheet)
    at = start(monkeypatch, sheet)
    assert not at.metric and "rename the sheet" in " ".join(e.value for e in at.error)


# --- save_upload (upload mode) ---------------------------------------------------------------

@pytest.mark.parametrize("name", [
    "../../evil.csv", "..\\..\\evil.csv", "C:\\Windows\\evil.csv", "/etc/evil.csv",
    "sub/dir/evil.csv",
])
def test_upload_names_cannot_escape_the_data_dir(tmp_path, name):
    data = tmp_path / "data"
    path = save_upload(data, name, b"x")
    assert path.resolve().is_relative_to(data.resolve())
    assert path.name == "evil.csv" and path.read_bytes() == b"x"


@pytest.mark.parametrize("name", ["", "  ", "..", "payments.csv", "MEMBERS_CLEAN.CSV",
                                  "../payments.csv"])
def test_unusable_or_sidecar_named_uploads_are_refused(tmp_path, name):
    with pytest.raises(ValueError):
        save_upload(tmp_path / "data", name, b"x")
    assert not (tmp_path / "data").exists() or not any((tmp_path / "data").rglob("*.csv"))


def test_identical_upload_is_untouched_and_a_changed_one_is_replaced(tmp_path):
    data = tmp_path / "data"
    first = save_upload(data, "Book1.csv", b"a,b\n")
    stamp = os.stat(first).st_mtime_ns
    assert save_upload(data, "Book1.csv", b"a,b\n") == first
    assert os.stat(first).st_mtime_ns == stamp
    second = save_upload(data, "Book1.csv", b"a,b,c\n")
    assert second == first and first.read_bytes() == b"a,b,c\n"
    assert sorted(p.name for p in first.parent.iterdir()) == ["Book1.csv"]  # no .tmp


def test_different_sheets_get_different_folders(tmp_path):
    data = tmp_path / "data"
    a = save_upload(data, "Book1.csv", b"1")
    b = save_upload(data, "Book1.xlsx", b"2")
    c = save_upload(data, "Other.csv", b"3")
    assert len({a.parent, b.parent, c.parent}) == 3
