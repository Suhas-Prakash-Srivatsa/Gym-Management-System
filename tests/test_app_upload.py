"""The upload-and-fix section of app.py, driven through Streamlit's AppTest.

Every case works on a COPY of the fixtures in tmp_path, in path mode, with
today pinned through GYM_TODAY so results are deterministic.
"""

import ast
import os
import shutil
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
FILES = ROOT / "src" / "files"
APP = ROOT / "app.py"

# The ticket's fixes for Book1_errors.csv, by widget key: infer the year on
# rows 1-2, "two people" for Rakesh Sharma, then correct the rest.
CHOICES = {
    "date_missing_year:1:date_joined": "infer_current_year",
    "date_missing_year:1:last_payment_date": "infer_current_year",
    "date_missing_year:2:date_joined": "infer_current_year",
    "last_payment_date_missing:2:last_payment_date": "use_date_joined",
    "duplicate_name:3:member_name": "different_people",
    "last_payment_date_missing:3:last_payment_date": "use_date_joined",
}
TYPED = {
    "invalid_instalments:5:instalments": "1",
    "paid_exceeds_contract:5:paid_amount": "12000",
    "unknown_membership_type:6:membership_type": "Half-Yearly",
}
FIXED_TILES = {
    "Total Members": "6",
    "Total Membership Value": "₹65,000",
    "Total Receivable": "₹32,000",
    "Overdue": "₹32,000",
}
BOOK1_TILES = {
    "Total Members": "24",
    "Total Membership Value": "₹2,35,400",
    "Total Receivable": "₹97,300",
    "Overdue": "₹60,950",
}


@pytest.fixture(autouse=True)
def pinned_today(monkeypatch):
    monkeypatch.setenv("GYM_TODAY", "2026-11-08")


def copy_fixture(tmp_path, name):
    folder = tmp_path / "gym"
    folder.mkdir(exist_ok=True)
    path = folder / name
    shutil.copy(FILES / name, path)
    return path


def run_app(monkeypatch, sheet):
    monkeypatch.setenv("GYM_SHEET", str(sheet))
    at = AppTest.from_file(str(APP), default_timeout=30)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def issue_tables(at):
    """The validation-issues table(s): the dashboard also shows a table since ticket 11."""
    return [d for d in at.dataframe if "Problem" in d.value.columns]


def tiles_shown(at):
    return {m.label: m.value for m in at.metric}


def texts(elements):
    return " ".join(e.value for e in elements)


def fingerprint(path):
    return path.read_bytes(), os.stat(path).st_mtime_ns


def answer_everything(at):
    for key, option in CHOICES.items():
        at.radio(key=f"{key}:option").set_value(option)
    for key, value in TYPED.items():
        at.text_input(key=f"{key}:value").input(value)
    at.run()  # each widget change reruns the script in the browser too
    at.button(key="apply_fixes").click()
    at.run()
    assert not at.exception, [e.value for e in at.exception]


def test_the_error_sheet_shows_every_issue_and_no_dashboard(tmp_path, monkeypatch):
    at = run_app(monkeypatch, copy_fixture(tmp_path, "Book1_errors.csv"))
    [table] = at.dataframe
    assert len(table.value) == 9
    assert set(table.value["Row"]) == {"1", "2", "3", "5", "6"}  # row 4 is covered by row 3's question
    assert tiles_shown(at) == {}
    assert "9" in texts(at.error)


def test_owner_questions_are_never_pre_answered(tmp_path, monkeypatch):
    at = run_app(monkeypatch, copy_fixture(tmp_path, "Book1_errors.csv"))
    for key in CHOICES:
        assert at.radio(key=f"{key}:option").value is None
    assert at.button(key="apply_fixes").disabled  # nothing answered, nothing to apply
    assert not (tmp_path / "gym" / "members_clean.csv").exists()


def test_the_year_fix_previews_the_date_it_will_write(tmp_path, monkeypatch):
    at = run_app(monkeypatch, copy_fixture(tmp_path, "Book1_errors.csv"))
    at.radio(key="date_missing_year:1:date_joined:option").set_value("infer_current_year")
    at.run()
    assert "Becomes 2026-06-01." in texts(at.caption)


def test_applying_the_ticket_fixes_writes_the_sidecar_and_shows_the_dashboard(tmp_path, monkeypatch):
    sheet = copy_fixture(tmp_path, "Book1_errors.csv")
    before = fingerprint(sheet)
    at = run_app(monkeypatch, sheet)
    answer_everything(at)
    assert (sheet.parent / "members_clean.csv").exists()
    assert tiles_shown(at) == FIXED_TILES
    assert "corrected" in texts(at.info)
    assert fingerprint(sheet) == before


def test_a_rerun_uses_the_corrections_and_asks_nothing(tmp_path, monkeypatch):
    sheet = copy_fixture(tmp_path, "Book1_errors.csv")
    answer_everything(run_app(monkeypatch, sheet))
    before = fingerprint(sheet)
    at = run_app(monkeypatch, sheet)
    assert len(at.radio) == 1  # only the path/upload mode switch
    assert not issue_tables(at)
    assert tiles_shown(at) == FIXED_TILES
    assert "members_clean.csv" in texts(at.info)
    assert fingerprint(sheet) == before


def test_partial_answers_loop_until_the_sheet_is_clean(tmp_path, monkeypatch):
    sheet = copy_fixture(tmp_path, "Book1_errors.csv")
    at = run_app(monkeypatch, sheet)
    at.radio(key="duplicate_name:3:member_name:option").set_value("different_people")
    at.run()
    at.button(key="apply_fixes").click()
    at.run()
    assert len(at.dataframe[0].value) == 8  # the duplicate is answered; the rest remain
    assert tiles_shown(at) == {}
    answer_everything_left = {k: v for k, v in CHOICES.items() if not k.startswith("duplicate")}
    for key, option in answer_everything_left.items():
        at.radio(key=f"{key}:option").set_value(option)
    for key, value in TYPED.items():
        at.text_input(key=f"{key}:value").input(value)
    at.run()  # each widget change reruns the script in the browser too
    at.button(key="apply_fixes").click()
    at.run()
    assert tiles_shown(at) == FIXED_TILES


def test_book1_goes_straight_to_the_dashboard(tmp_path, monkeypatch):
    sheet = copy_fixture(tmp_path, "Book1.csv")
    before = fingerprint(sheet)
    at = run_app(monkeypatch, sheet)
    assert tiles_shown(at) == BOOK1_TILES
    assert not issue_tables(at) and not at.error
    assert not (sheet.parent / "members_clean.csv").exists()
    assert fingerprint(sheet) == before


def test_a_missing_column_is_fatal_and_says_what_to_add(tmp_path, monkeypatch):
    folder = tmp_path / "gym"
    folder.mkdir()
    sheet = folder / "NoType.csv"
    lines = (FILES / "Book1.csv").read_text(encoding="utf-8-sig").splitlines()
    sheet.write_text("\n".join(",".join(c for i, c in enumerate(line.split(",")) if i != 3)
                               for line in lines) + "\n", encoding="utf-8")
    at = run_app(monkeypatch, sheet)
    [table] = at.dataframe
    assert list(table.value["Problem"]) == [
        "The sheet has no Membership Type column. Add it to the sheet, save it and reload."]
    assert "column" in texts(at.error)
    assert tiles_shown(at) == {}
    assert not [b for b in at.button if b.key == "apply_fixes"]


def test_a_newer_sheet_than_its_corrections_asks_before_using_them(tmp_path, monkeypatch):
    sheet = copy_fixture(tmp_path, "Book1_errors.csv")
    answer_everything(run_app(monkeypatch, sheet))
    clean = sheet.parent / "members_clean.csv"
    old = os.stat(sheet).st_mtime_ns - 60_000_000_000
    os.utime(clean, ns=(old, old))  # the owner edited the sheet after correcting it
    at = run_app(monkeypatch, sheet)
    assert "changed" in texts(at.warning)
    assert tiles_shown(at) == {}
    at.button(key="discard_corrections").click()
    at.run()
    assert len(at.dataframe[0].value) == 9  # back to the sheet's own issues
    assert len(list(sheet.parent.glob("members_clean.csv.*.bak"))) == 1


def test_keeping_corrections_after_a_sheet_change(tmp_path, monkeypatch):
    sheet = copy_fixture(tmp_path, "Book1_errors.csv")
    answer_everything(run_app(monkeypatch, sheet))
    clean = sheet.parent / "members_clean.csv"
    old = os.stat(sheet).st_mtime_ns - 60_000_000_000
    os.utime(clean, ns=(old, old))
    at = run_app(monkeypatch, sheet)
    at.button(key="keep_corrections").click()
    at.run()
    assert tiles_shown(at) == FIXED_TILES


def test_a_bad_ledger_line_is_a_message_not_a_traceback(tmp_path, monkeypatch):
    sheet = copy_fixture(tmp_path, "Book1.csv")
    (sheet.parent / "payments.csv").write_text(
        "payment_id,membership_id,amount,paid_on,source,recorded_at\n"
        "P-0001,MS-001,-500,2026-11-01,recorded,2026-11-01T10:00:00\n", encoding="utf-8")
    at = run_app(monkeypatch, sheet)
    assert "line 2" in texts(at.error)
    assert tiles_shown(at) == {}


def test_ledger_rows_for_unknown_memberships_are_listed_and_not_counted(tmp_path, monkeypatch):
    sheet = copy_fixture(tmp_path, "Book1.csv")
    (sheet.parent / "payments.csv").write_text(
        "payment_id,membership_id,amount,paid_on,source,recorded_at\n"
        "P-0001,MS-999,500,2026-11-01,recorded,2026-11-01T10:00:00\n", encoding="utf-8")
    at = run_app(monkeypatch, sheet)
    assert "P-0001" in texts(at.warning) and "MS-999" in texts(at.warning)
    assert tiles_shown(at) == BOOK1_TILES


def test_a_file_locked_by_excel_is_a_message_not_a_traceback(tmp_path, monkeypatch):
    sheet = copy_fixture(tmp_path, "Book1.csv")

    def locked(path):
        raise PermissionError(13, "Permission denied", str(path))

    monkeypatch.setattr("src.ledger.read_payments", locked)
    at = run_app(monkeypatch, sheet)
    assert "payments.csv" in texts(at.error) and "Excel" in texts(at.error)


@pytest.mark.parametrize("given", ["", "C:/no/such/sheet.csv"])
def test_no_sheet_or_a_missing_one_is_explained(tmp_path, monkeypatch, given):
    at = run_app(monkeypatch, given)
    assert texts(at.info) or texts(at.error)
    assert tiles_shown(at) == {}


# --- ADR 0001: the shell holds no rules ---

ARITHMETIC = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow, ast.MatMult)
ORDERING = (ast.Lt, ast.LtE, ast.Gt, ast.GtE)


def test_app_has_no_arithmetic_or_ordering_comparisons():
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        assert not (isinstance(node, ast.BinOp) and isinstance(node.op, ARITHMETIC)), ast.unparse(node)
        assert not isinstance(node, ast.AugAssign), ast.unparse(node)
        assert not (isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub)), ast.unparse(node)
        if isinstance(node, ast.Compare):
            assert not any(isinstance(op, ORDERING) for op in node.ops), ast.unparse(node)


def test_app_reads_the_clock_exactly_once():
    source = APP.read_text(encoding="utf-8")
    assert source.count("date.today()") == 1
    # Timestamps (backup names, later recorded_at) come from one clock read, never dates.
    assert source.count("datetime.now()") <= 1


def test_the_clock_is_read_nowhere_in_src():
    for path in (ROOT / "src").glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "date.today()" not in source.replace("`date.today()`", ""), path.name


def test_the_sheet_path_can_come_from_the_command_line(tmp_path, monkeypatch):
    # streamlit run app.py -- path/to/sheet.csv puts the path in sys.argv[1].
    sheet = copy_fixture(tmp_path, "Book1.csv")
    monkeypatch.delenv("GYM_SHEET", raising=False)
    monkeypatch.setattr("sys.argv", ["app.py", str(sheet)])
    at = AppTest.from_file(str(APP), default_timeout=30)
    at.run()
    assert not at.exception
    assert at.text_input(key="sheet_path").value == str(sheet)
    assert tiles_shown(at) == BOOK1_TILES


def test_a_folder_path_is_called_a_folder_not_a_locked_file(tmp_path, monkeypatch):
    at = run_app(monkeypatch, tmp_path)
    assert "folder, not a sheet" in texts(at.error)
    assert "open in another program" not in texts(at.error)
    assert tiles_shown(at) == {}
