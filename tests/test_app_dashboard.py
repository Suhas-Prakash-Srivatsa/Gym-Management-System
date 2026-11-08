"""The dashboard section of app.py (ticket 11), driven through Streamlit's AppTest.

Book1.csv is copied into tmp_path and today pinned to 2026-11-08 via GYM_TODAY.
"""

import re
import shutil
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src.views import ROW_COLUMNS

ROOT = Path(__file__).resolve().parent.parent
FILES = ROOT / "src" / "files"
APP = str(ROOT / "app.py")


@pytest.fixture
def at(tmp_path, monkeypatch):
    sheet = tmp_path / "gym" / "Book1.csv"
    sheet.parent.mkdir()
    shutil.copy(FILES / "Book1.csv", sheet)
    monkeypatch.setenv("GYM_TODAY", "2026-11-08")
    monkeypatch.setenv("GYM_SHEET", str(sheet))
    app = AppTest.from_file(APP, default_timeout=30)
    app.run()
    assert not app.exception, [e.value for e in app.exception]
    return app


def receivables(at):
    [table] = [d for d in at.dataframe if "Next Due Date" in d.value.columns]
    return table


def styled_rows(table, column):
    """Row indexes whose `column` cell carries a CSS rule setting a red colour."""
    col = list(table.value.columns).index(column)
    styled = set()
    # pandas groups identical rules: "#T_x_row0_col9, #T_x_row4_col9 { background-color: ... }"
    for selectors, body in re.findall(r"([^{}]+)\{([^}]*)\}", table.proto.arrow_data.styler.styles):
        if "background-color" in body:
            styled |= {int(r) for r in re.findall(rf"_row(\d+)_col{col}\b", selectors)}
    return styled


def test_four_tiles_from_views(at):
    assert {m.label: m.value for m in at.metric} == {
        "Total Members": "24",
        "Total Membership Value": "₹2,35,400",
        "Total Receivable": "₹97,300",
        "Overdue": "₹60,950",
    }


def test_the_table_has_exactly_the_dashboard_columns(at):
    assert list(receivables(at).value.columns) == list(ROW_COLUMNS)


def test_nineteen_rows_worst_first_with_eleven_due(at):
    table = receivables(at).value
    assert len(table) == 19
    assert table.iloc[0]["Member Name"] == "Pooja Shetty"
    assert table.iloc[0]["Next Due Date"] == "2026-04-20"
    assert table.iloc[-1]["Member Name"] == "Ritu Malhotra"
    assert (table["Status"] == "DUE").sum() == 11


def test_due_rows_and_only_due_rows_are_styled_red(at):
    table = receivables(at)
    due = {i for i, s in enumerate(table.value["Status"]) if s == "DUE"}
    assert len(due) == 11
    assert styled_rows(table, "Status") == due


def test_show_fully_paid_is_off_by_default_and_adds_the_seven_settled_rows(at):
    toggle = at.toggle(key="show_fully_paid")
    assert toggle.value is False
    toggle.set_value(True)
    at.run()
    table = receivables(at).value
    assert len(table) == 26
    assert list(table["Status"][19:]) == ["Paid"] * 7
    assert set(table["Next Due Date"][19:]) == {"—"}
    assert styled_rows(receivables(at), "Status") == {
        i for i, s in enumerate(table["Status"]) if s == "DUE"}


def test_the_app_does_not_sort_or_compute_the_table():
    source = Path(APP).read_text(encoding="utf-8")
    for forbidden in ("sort", "sorted(", "groupby", ".sum(", "receivables_rows(rows"):
        assert forbidden not in source
    assert "views.receivables_rows(" in source
