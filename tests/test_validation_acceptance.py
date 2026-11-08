"""Acceptance pins for ticket 05 not covered by the coder's tests."""

import copy
from pathlib import Path

from src.sheet import read_rows
from src.validation import validate

ROOT = Path(__file__).resolve().parent.parent
FILES = ROOT / "src" / "files"


def test_validation_has_no_clock_file_or_ui_access():
    source = (ROOT / "src" / "validation.py").read_text(encoding="utf-8")
    for forbidden in ("import datetime", "from datetime", "open(", "streamlit", "print(", "float"):
        assert forbidden not in source


def test_validate_does_not_mutate_rows():
    rows, columns = read_rows(FILES / "Book1_errors.csv")
    before = copy.deepcopy(rows)
    validate(rows, columns)
    assert rows == before


def test_owner_only_questions_are_explicit_choices_not_defaults():
    report = validate(*read_rows(FILES / "Book1_errors.csv"))
    owner_only = [i for i in report.issues if i.code in ("date_missing_year", "duplicate_name")]
    assert {i.code for i in owner_only} == {"date_missing_year", "duplicate_name"}
    assert all(len(i.fix_options) >= 2 for i in owner_only)


def test_error_fixture_yields_exactly_nine_issues():
    report = validate(*read_rows(FILES / "Book1_errors.csv"))
    assert len(report.issues) == 9
