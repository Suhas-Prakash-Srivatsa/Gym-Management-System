"""The built-in sheets: the downloadable sample and the demo gym (src/samples.py)."""

import io
from datetime import date

import pytest

from src.assemble import build_dataset
from src.sheet import read_rows
from src.samples import (
    DEMO_ANCHOR,
    DEMO_SOURCE,
    SAMPLE_FILE_NAME,
    column_guide,
    demo_sheet_csv,
    sample_preview,
    sample_sheet_csv,
)
from src.validation import COLUMN_LABELS, REQUIRED_COLUMNS, validate


def read_back(data: bytes, name: str = "sheet.csv"):
    upload = io.BytesIO(data)
    upload.name = name
    return read_rows(upload)


# --- The sample sheet -----------------------------------------------------------------

def test_the_sample_round_trips_through_the_tool_with_zero_issues():
    rows, columns = read_back(sample_sheet_csv(), SAMPLE_FILE_NAME)
    report = validate(rows, columns)
    assert report.issues == ()
    dataset = build_dataset(rows)
    assert len(dataset.memberships) == len(sample_preview()) == 4
    assert len(dataset.members) == 3  # Asha's renewal shares her Member ID


def test_the_sample_uses_the_tool_s_own_column_names_in_order():
    header = sample_sheet_csv().decode("utf-8-sig").splitlines()[0]
    assert header.split(",") == list(COLUMN_LABELS.values())
    assert header.startswith("Member ID,Member Name,Membership ID,Membership Type")


def test_the_sample_opens_in_excel_with_names_intact():
    assert sample_sheet_csv().startswith(b"\xef\xbb\xbf")  # UTF-8 BOM


def test_the_preview_shows_exactly_what_the_download_holds():
    rows, _ = read_back(sample_sheet_csv())
    preview = sample_preview()
    assert [list(p) for p in preview] == [list(COLUMN_LABELS.values())] * len(preview)
    assert [[p[COLUMN_LABELS[c]] for c in COLUMN_LABELS] for p in preview] == [
        [r[c] for c in COLUMN_LABELS] for r in rows]


def test_the_column_guide_marks_required_columns_and_lists_aliases():
    guide = {g["Column"]: g for g in column_guide()}
    assert list(guide) == list(COLUMN_LABELS.values())
    required = {g["Column"] for g in guide.values() if g["Required"] == "Yes"}
    assert required == {COLUMN_LABELS[c] for c in REQUIRED_COLUMNS}
    assert guide["Member Name"]["Also accepted as"] == "name, member"
    assert guide["Membership ID"]["Also accepted as"] == ""
    assert all(g["What goes in it"] for g in guide.values())


# --- The demo gym ------------------------------------------------------------------------

def test_on_its_anchor_day_the_demo_is_its_source_file():
    demo, _ = read_back(demo_sheet_csv(DEMO_ANCHOR))
    source, _ = read_rows(DEMO_SOURCE)
    assert demo == source


@pytest.mark.parametrize("today", [date(2026, 11, 8), date(2027, 3, 1), date(2030, 2, 28)])
def test_the_demo_is_a_clean_sheet_on_any_day(today):
    rows, columns = read_back(demo_sheet_csv(today))
    assert validate(rows, columns).issues == ()


def test_the_demo_s_dates_move_with_today():
    later, _ = read_back(demo_sheet_csv(date(2026, 11, 18)))  # ten days after the anchor
    assert later[0]["date_joined"] == "2026-03-11"
    assert later[0]["last_payment_date"] == "2026-07-11"
    assert later[1]["last_payment_date"] == ""  # nothing paid: stays empty
    assert later[0]["membership_amount"] == "15000"  # only dates move


def test_the_demo_is_not_book1():
    demo, _ = read_back(demo_sheet_csv(DEMO_ANCHOR))
    book1, _ = read_rows(DEMO_SOURCE.parent / "Book1.csv")
    assert not {r["member_name"] for r in demo} & {r["member_name"] for r in book1}
