"""Acceptance pins for ticket 04 not covered by the coder's tests."""

from pathlib import Path

import pytest

from src.sheet import read_rows

ROOT = Path(__file__).resolve().parent.parent
FILES = ROOT / "src" / "files"


def test_sheet_reader_does_no_parsing():
    source = (ROOT / "src" / "sheet.py").read_text(encoding="utf-8")
    for forbidden in ("src.money", "src.dates", "parse_money", "parse_date", "Decimal", "float("):
        assert forbidden not in source


@pytest.mark.parametrize("fixture", ["Book1.csv", "Book1_errors.csv"])
def test_every_value_arrives_as_a_string(fixture):
    rows, _ = read_rows(FILES / fixture)
    assert rows and all(isinstance(v, str) for row in rows for v in row.values())


def test_duplicate_canonical_headers_stay_visible_in_columns(tmp_path):
    # Two headers mapping to one key: the row dict can hold only one, so the
    # duplicate must at least remain in `columns` for validation to report.
    path = tmp_path / "dup.csv"
    path.write_text("Name,Member Name\nA,B\n", encoding="utf-8")
    _, columns = read_rows(path)
    assert columns.count("member_name") == 2
