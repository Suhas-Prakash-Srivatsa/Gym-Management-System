"""Reading the owner's sheet (shell): file -> RawRows of untouched strings.

This module only reads. It never parses dates or money and never defaults a
value; that happens once, at the validation/assembly boundary.
"""

import csv
import io
from datetime import date, datetime
from pathlib import Path

from src.models import RawRow

HEADER_ALIASES: dict[str, str] = {
    "member id": "member_id",
    "id": "member_id",
    "member name": "member_name",
    "name": "member_name",
    "member": "member_name",
    "membership id": "membership_id",
    "membership type": "membership_type",
    "type": "membership_type",
    "plan": "membership_type",
    "date joined": "date_joined",
    "joined": "date_joined",
    "join date": "date_joined",
    "joining date": "date_joined",
    "membership amount": "membership_amount",
    "amount": "membership_amount",
    "contract amount": "membership_amount",
    "installments": "instalments",
    "instalments": "instalments",
    "paid amount": "paid_amount",
    "paid": "paid_amount",
    "amount paid": "paid_amount",
    "last payment date": "last_payment_date",
    "last paid": "last_payment_date",
    "date of payment": "last_payment_date",
}


def normalise_header(raw: str) -> str | None:
    """Lowercase, strip, collapse spaces, then look up; None if unrecognised.

    A UTF-8 BOM is dropped and `_`/`-` count as spaces, so `﻿Member Name`,
    `member_name` and `Member-Name` all match.
    """
    cleaned = raw.replace("﻿", "").replace("_", " ").replace("-", " ")
    key = " ".join(cleaned.lower().split())
    return HEADER_ALIASES.get(key)


def read_rows(file) -> tuple[list[RawRow], list[str]]:
    """Read a sheet into RawRows keyed by canonical column names.

    `file` is a path, or a binary file object with a `.name` (an upload).
    Returns the rows plus the columns found, in sheet order. A recognised
    header becomes its canonical name; an unrecognised one is kept under its
    original (BOM- and whitespace-stripped) spelling; `unrecognised_columns`
    lists those for reporting.
    """
    name, data = _read_bytes(file)
    records = _xlsx_records(data) if name.lower().endswith(".xlsx") else _csv_records(data)
    header = next(records, [])
    columns = [_column_name(h) for h in header]
    rows = [dict(zip(columns, record)) for record in records if record]
    return rows, columns


def unrecognised_columns(columns: list[str]) -> list[str]:
    """Columns read_rows kept but could not map to a canonical name, in order."""
    canonical = set(HEADER_ALIASES.values())
    return [c for c in columns if c not in canonical]


def _read_bytes(file) -> tuple[str, bytes]:
    if hasattr(file, "read"):
        return getattr(file, "name", ""), file.read()
    path = Path(file)
    return path.name, path.read_bytes()


def _csv_records(data: bytes):
    return csv.reader(io.StringIO(data.decode("utf-8-sig"), newline=""))


def _xlsx_records(data: bytes):
    """First worksheet of an .xlsx, each cell rendered as the string the owner sees.

    Excel stores dates as dates, not text; they are rendered ISO (`2026-06-01`)
    so the single parsing boundary still receives a string.
    """
    try:
        import openpyxl
    except ImportError as exc:
        raise ImportError(
            "Reading .xlsx sheets needs the openpyxl package: pip install openpyxl "
            "(or save the sheet as CSV)."
        ) from exc
    workbook = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    try:
        for cells in workbook.worksheets[0].iter_rows(values_only=True):
            if all(c is None for c in cells):
                yield []
            else:
                yield [_cell_text(c) for c in cells]
    finally:
        workbook.close()


def _cell_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat() if value.time() == datetime.min.time() else value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _column_name(raw: str) -> str:
    return normalise_header(raw) or raw.replace("﻿", "").strip()
