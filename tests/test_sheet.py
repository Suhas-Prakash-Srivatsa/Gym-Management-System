import io
import sys
from pathlib import Path

import pytest

from src.sheet import normalise_header, read_rows, unrecognised_columns


@pytest.mark.parametrize(
    "raw, canonical",
    [
        ("Name", "member_name"),
        ("Member", "member_name"),
        ("Member Name", "member_name"),
        ("Joined", "date_joined"),
        ("Amount", "membership_amount"),
        ("Installments", "instalments"),
        ("Last Payment Date", "last_payment_date"),
    ],
)
def test_normalise_header_maps_aliases_to_canonical_keys(raw, canonical):
    assert normalise_header(raw) == canonical


@pytest.mark.parametrize("raw", ["﻿Member Name", "  MEMBER   name ", "member_name", "Member-Name"])
def test_normalise_header_tolerates_bom_case_spacing_and_separators(raw):
    assert normalise_header(raw) == "member_name"


@pytest.mark.parametrize("raw", ["Pending Amount", "Notes", ""])
def test_normalise_header_returns_none_for_unrecognised(raw):
    assert normalise_header(raw) is None


def write_csv(tmp_path, text, name="sheet.csv", encoding="utf-8"):
    path = tmp_path / name
    path.write_bytes(text.encode(encoding))
    return path


def test_read_rows_normalises_alias_headers_and_keeps_values_untouched(tmp_path):
    path = write_csv(
        tmp_path,
        "name,joined,amount,type,installments,paid,last paid\n"
        'Suhas, 2026-06-01 ,"₹12,000",Yearly,2,0,\n',
    )
    rows, columns = read_rows(path)
    assert columns == [
        "member_name", "date_joined", "membership_amount", "membership_type",
        "instalments", "paid_amount", "last_payment_date",
    ]
    assert rows == [{
        "member_name": "Suhas",
        "date_joined": " 2026-06-01 ",
        "membership_amount": "₹12,000",
        "membership_type": "Yearly",
        "instalments": "2",
        "paid_amount": "0",
        "last_payment_date": "",
    }]


def test_read_rows_preserves_and_reports_unrecognised_columns(tmp_path):
    path = write_csv(tmp_path, "Name,Pending Amount, Notes \nSuhas,0,pays late\n")
    rows, columns = read_rows(path)
    assert columns == ["member_name", "Pending Amount", "Notes"]
    assert unrecognised_columns(columns) == ["Pending Amount", "Notes"]
    assert rows == [{"member_name": "Suhas", "Pending Amount": "0", "Notes": "pays late"}]


def test_bom_prefixed_header_still_matches(tmp_path):
    path = write_csv(tmp_path, "﻿Member Name,Joined\nSuhas,2026-06-01\n")
    rows, columns = read_rows(path)
    assert columns == ["member_name", "date_joined"]
    assert rows[0]["member_name"] == "Suhas"


FILES = Path(__file__).resolve().parent.parent / "src" / "files"


def test_error_fixture_reaches_caller_without_raising():
    rows, columns = read_rows(FILES / "Book1_errors.csv")
    assert len(rows) == 6
    assert "Quarterly" in [r["membership_type"] for r in rows]
    assert rows[0]["date_joined"] == "1st June"
    assert rows[1]["last_payment_date"] == ""


def test_book1_fixture_reads_every_membership_row_with_canonical_columns():
    rows, columns = read_rows(FILES / "Book1.csv")
    assert len(rows) == 26
    assert columns == [
        "member_id", "member_name", "membership_id", "membership_type", "date_joined",
        "membership_amount", "instalments", "paid_amount", "last_payment_date",
    ]
    assert rows[0]["member_id"] == "M001"
    assert rows[-1] == {
        "member_id": "M009", "member_name": "Manoj Verma", "membership_id": "MS-026",
        "membership_type": "Yearly", "date_joined": "2026-11-01",
        "membership_amount": "12000", "instalments": "2", "paid_amount": "6000",
        "last_payment_date": "2026-11-01",
    }


def test_blank_lines_are_not_rows(tmp_path):
    path = write_csv(tmp_path, "Name,Joined\nSuhas,2026-06-01\n\n\nVandana,2026-08-05\n\n")
    rows, _ = read_rows(path)
    assert [r["member_name"] for r in rows] == ["Suhas", "Vandana"]


class Upload(io.BytesIO):
    """Stands in for an uploaded file: binary, with a name, not on disk."""

    def __init__(self, data: bytes, name: str):
        super().__init__(data)
        self.name = name


def test_read_rows_accepts_an_uploaded_file_object():
    upload = Upload("﻿Name,Amount\nSuhas,12000\n".encode("utf-8"), "Book1.csv")
    rows, columns = read_rows(upload)
    assert columns == ["member_name", "membership_amount"]
    assert rows == [{"member_name": "Suhas", "membership_amount": "12000"}]


def test_xlsx_without_openpyxl_fails_with_an_install_hint(monkeypatch):
    monkeypatch.setitem(sys.modules, "openpyxl", None)  # makes `import openpyxl` fail
    with pytest.raises(ImportError, match="pip install openpyxl"):
        read_rows(Upload(b"PK\x03\x04", "members.xlsx"))


def test_xlsx_sheet_reads_like_csv(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    from datetime import datetime

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["Name", "Joined", "Amount", "Last Payment Date"])
    sheet.append(["Suhas", datetime(2026, 6, 1), 12000, None])
    sheet.append([None, None, None, None])
    sheet.append(["Vandana", "1st June", "₹24,000", "2026-08-05"])
    path = tmp_path / "members.xlsx"
    workbook.save(path)

    rows, columns = read_rows(path)
    assert columns == ["member_name", "date_joined", "membership_amount", "last_payment_date"]
    assert rows == [
        {"member_name": "Suhas", "date_joined": "2026-06-01",
         "membership_amount": "12000", "last_payment_date": ""},
        {"member_name": "Vandana", "date_joined": "1st June",
         "membership_amount": "₹24,000", "last_payment_date": "2026-08-05"},
    ]


def test_unrecognised_columns_is_empty_for_a_fully_canonical_sheet():
    _, columns = read_rows(FILES / "Book1.csv")
    assert unrecognised_columns(columns) == []


def test_raw_row_type_lives_in_the_core_vocabulary():
    import src.models
    import src.sheet

    assert src.sheet.RawRow is src.models.RawRow
