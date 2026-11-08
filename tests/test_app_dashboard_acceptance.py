"""Independent acceptance tests for ticket 11 (dashboard render) and the ticket 10
leftovers, written by the tester. AppTest in path mode on copies in tmp_path,
today pinned to 2026-11-08.
"""

import os
import re
import shutil
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src.assemble import build_dataset
from src.balances import all_statuses
from src.ledger import append_payment
from src.models import Payment
from src.sheet import read_rows
from src.sidecar import (
    check_sheet, clean_members_path, discard_corrections, payments_path, save_upload,
)
from src.views import ROW_COLUMNS, receivables_rows

ROOT = Path(__file__).resolve().parent.parent
FILES = ROOT / "src" / "files"
APP = str(ROOT / "app.py")
TODAY = date(2026, 11, 8)


@pytest.fixture(autouse=True)
def pinned(monkeypatch):
    monkeypatch.setenv("GYM_TODAY", "2026-11-08")


@pytest.fixture
def sheet(tmp_path):
    path = tmp_path / "gym" / "Book1.csv"
    path.parent.mkdir()
    shutil.copy(FILES / "Book1.csv", path)
    return path


def run(monkeypatch, path):
    monkeypatch.setenv("GYM_SHEET", str(path))
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def table(at):
    [t] = [d for d in at.dataframe if "Next Due Date" in d.value.columns]
    return t


def styled_cells(t):
    """(row, column-name) pairs carrying a background colour."""
    cols = list(t.value.columns)
    cells = set()
    for selectors, body in re.findall(r"([^{}]+)\{([^}]*)\}", t.proto.arrow_data.styler.styles):
        if "background" in body:
            cells |= {(int(r), cols[int(c)]) for r, c in re.findall(r"_row(\d+)_col(\d+)", selectors)}
    return cells


def expected_display(path, show_paid=False):
    statuses = all_statuses(build_dataset(read_rows(path)[0]), TODAY)
    return [list(r["display"].values()) for r in receivables_rows(statuses, show_paid)]


# --- Ticket 11 -----------------------------------------------------------------------

def test_tiles(monkeypatch, sheet):
    at = run(monkeypatch, sheet)
    assert [(m.label, m.value) for m in at.metric] == [
        ("Total Members", "24"), ("Total Membership Value", "₹2,35,400"),
        ("Total Receivable", "₹97,300"), ("Overdue", "₹60,950")]


def test_table_is_exactly_what_views_returned(monkeypatch, sheet):
    before = (sheet.read_bytes(), os.stat(sheet).st_mtime_ns)
    df = table(run(monkeypatch, sheet)).value
    assert list(df.columns) == list(ROW_COLUMNS)
    assert len(df) == 19
    assert df.values.tolist() == expected_display(sheet)
    assert (df.iloc[0]["Member Name"], df.iloc[0]["Membership ID"]) == ("Pooja Shetty", "MS-020")
    assert (df.iloc[-1]["Member Name"], df.iloc[-1]["Membership ID"]) == ("Ritu Malhotra", "MS-022")
    assert (df["Status"] == "DUE").sum() == 11
    assert (sheet.read_bytes(), os.stat(sheet).st_mtime_ns) == before


def test_red_only_on_the_status_cell_of_due_rows(monkeypatch, sheet):
    t = table(run(monkeypatch, sheet))
    due = {i for i, s in enumerate(t.value["Status"]) if s == "DUE"}
    assert len(due) == 11
    assert styled_cells(t) == {(i, "Status") for i in due}


def test_toggle_defaults_off_and_adds_seven_settled_rows(monkeypatch, sheet):
    at = run(monkeypatch, sheet)
    assert at.toggle(key="show_fully_paid").value is False
    at.toggle(key="show_fully_paid").set_value(True)
    at.run()
    t = table(at)
    df = t.value
    assert len(df) == 26
    assert df.values.tolist() == expected_display(sheet, True)
    assert list(df["Status"].iloc[19:]) == ["Paid"] * 7
    assert list(df["Next Due Date"].iloc[19:]) == ["—"] * 7
    assert list(df["Outstanding"].iloc[19:]) == ["₹0"] * 7
    due = {i for i, s in enumerate(df["Status"]) if s == "DUE"}
    assert styled_cells(t) == {(i, "Status") for i in due}
    at.toggle(key="show_fully_paid").set_value(False)
    at.run()
    assert len(table(at).value) == 19


def test_no_stray_warnings_on_a_clean_sheet(monkeypatch, sheet):
    at = run(monkeypatch, sheet)
    assert not at.warning and not at.error and not at.info


def test_everyone_paid_renders_an_empty_table(monkeypatch, tmp_path):
    path = tmp_path / "gym" / "paid.csv"
    path.parent.mkdir()
    path.write_text(
        "Member ID,Member Name,Membership ID,Membership Type,Date Joined,Membership Amount,"
        "Installments,Paid Amount,Last Payment Date\n"
        "M1,A,MS-1,Yearly,2026-01-01,1000,1,1000,2026-01-01\n", encoding="utf-8")
    at = run(monkeypatch, path)
    assert len(table(at).value) == 0
    assert {m.label: m.value for m in at.metric}["Total Receivable"] == "₹0"
    at.toggle(key="show_fully_paid").set_value(True)
    at.run()
    assert table(at).value["Status"].tolist() == ["Paid"]


def test_ledger_payment_moves_tiles_and_rows(monkeypatch, sheet):
    append_payment(payments_path(sheet), Payment(
        "P-0001", "MS-020", Decimal("4500"), TODAY, "recorded", datetime(2026, 11, 8, 9)))
    append_payment(payments_path(sheet), Payment(
        "P-0002", "MS-999", Decimal("100"), TODAY, "recorded", datetime(2026, 11, 8, 9)))
    at = run(monkeypatch, sheet)
    tiles = {m.label: m.value for m in at.metric}
    assert tiles["Total Receivable"] == "₹92,800" and tiles["Overdue"] == "₹56,450"
    df = table(at).value
    assert len(df) == 18 and "MS-020" not in set(df["Membership ID"])
    assert "MS-999" in " ".join(w.value for w in at.warning)


# --- Ticket 10 leftovers --------------------------------------------------------------------

def test_a_folder_path_is_explained_not_blamed_on_excel(monkeypatch, tmp_path):
    at = run(monkeypatch, tmp_path)
    text = " ".join(e.value for e in at.error)
    assert "folder, not a sheet" in text and "Excel. Close it" not in text
    with pytest.raises(ValueError):
        check_sheet(tmp_path)
    with pytest.raises(FileNotFoundError):
        check_sheet(tmp_path / "missing.csv")


def test_a_path_with_invalid_characters_is_a_message(monkeypatch, tmp_path):
    at = run(monkeypatch, str(tmp_path / "bad<name>.csv"))
    assert at.error and not at.metric


@pytest.mark.parametrize("name", [
    "con.csv", "CON.CSV", "nul", "Nul.xlsx", "com1.csv", "LPT9.csv", "aux.tar.csv", "con .csv",
    "Book1.csv:evil", "a<b>.csv", 'a"b.csv', "a|b.csv", "a?b.csv", "a*b.csv", "tab\there.csv",
    "Book1.csv.", "Book1.csv ",
])
def test_windows_unstorable_upload_names_are_refused_before_writing(tmp_path, name):
    data = tmp_path / "data"
    with pytest.raises(ValueError):
        save_upload(data, name, b"x")
    assert not data.exists()


@pytest.mark.parametrize("name", ["console.csv", "Conan.csv", "com10.csv", "my con.csv",
                                  "Book 1 (copy).csv", "Ünal members.xlsx"])
def test_ordinary_names_still_upload(tmp_path, name):
    assert save_upload(tmp_path / "data", name, b"x").read_bytes() == b"x"


def test_discards_never_overwrite_an_earlier_backup(tmp_path):
    sheet = tmp_path / "s.csv"
    sheet.write_bytes(b"x")
    clean = clean_members_path(sheet)
    stamp = datetime(2026, 11, 8, 22, 0, 0)
    backups = []
    for content in (b"first", b"second", b"third"):
        clean.write_bytes(content)
        backups.append(discard_corrections(sheet, stamp))  # same second each time
    assert len(set(backups)) == 3
    assert [b.read_bytes() for b in backups] == [b"first", b"second", b"third"]
    assert not clean.exists()
    assert discard_corrections(sheet, stamp) is None
    assert sheet.read_bytes() == b"x"
