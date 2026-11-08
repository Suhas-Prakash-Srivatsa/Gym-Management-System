"""Where derived files live (shell): sidecars beside the owner's sheet (ADR 0002).

The input sheet is read, never written. Recorded payments go to
`payments.csv` and in-dashboard corrections to `members_clean.csv`, both in
the input's folder; on later runs the cleaned sidecar takes precedence, and
`resolve_input` says when it did so the owner knows they see corrected data.
"""

import csv
import os
from dataclasses import dataclass
from pathlib import Path

from src.models import RawRow
from src.sheet import HEADER_ALIASES, read_rows

PAYMENTS_NAME = "payments.csv"
CLEAN_MEMBERS_NAME = "members_clean.csv"

# Canonical columns in sheet order (member_id, member_name, membership_id, ...).
_CANONICAL = tuple(dict.fromkeys(HEADER_ALIASES.values()))


def _beside(input_path, name: str) -> Path:
    path = Path(input_path)
    if path.name.casefold() in (PAYMENTS_NAME, CLEAN_MEMBERS_NAME):
        raise ValueError(
            f"The input sheet is named {path.name!r}, the name of a sidecar file the tool "
            "writes; rename the sheet so it cannot be overwritten.")
    return path.resolve().parent / name


def payments_path(input_path) -> Path:
    """The Payment Ledger beside the input sheet."""
    return _beside(input_path, PAYMENTS_NAME)


def clean_members_path(input_path) -> Path:
    """The cleaned members sidecar beside the input sheet."""
    return _beside(input_path, CLEAN_MEMBERS_NAME)


def read_clean_members(path) -> list[RawRow] | None:
    """The cleaned rows, or None when no cleaned sidecar exists yet."""
    path = Path(path)
    if not path.exists():
        return None
    rows, _ = read_rows(path)
    return rows


def write_clean_members(path, rows: list[RawRow]) -> None:
    """Write the corrected rows as a fresh snapshot, readable by `sheet.read_rows`.

    Headers are canonical keys (`member_id`, `member_name`, ...), in sheet
    order, then any unrecognised columns in first-seen order. `member_id` is
    always written, because apply_fixes may have added it to only some rows,
    and dropping it would undo the owner's duplicate-name answer.

    Written to a temporary file then swapped in with `os.replace`, so a crash
    leaves the previous snapshot intact rather than a truncated one. UTF-8
    with BOM, so Excel shows names like "Ünal" correctly if the owner opens it.
    """
    path = Path(path)
    present = dict.fromkeys(k for r in rows for k in r)
    columns = ["member_id", *(c for c in _CANONICAL if c in present and c != "member_id"),
               *(c for c in present if c not in _CANONICAL)]
    temp = path.with_name(path.name + ".tmp")
    with temp.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        for row in rows:
            writer.writerow([row.get(c) or "" for c in columns])
    os.replace(temp, path)


@dataclass(frozen=True)
class ResolvedInput:
    """What to validate and assemble, and where it came from.

    `columns` is exactly what `sheet.read_rows` found, duplicates and
    unrecognised headers included, because `validate(rows, columns)` needs
    them: a header-only sheet has no rows to infer columns from, and a column
    given twice is invisible in the row dicts.
    """

    rows: list[RawRow]
    columns: list[str]
    used_clean_sidecar: bool  # tell the owner they are seeing corrected data


def resolve_input(input_path) -> ResolvedInput:
    """Prefer `members_clean.csv` beside the input; otherwise read the sheet itself."""
    clean_path = clean_members_path(input_path)
    if clean_path.exists():
        return ResolvedInput(*read_rows(clean_path), used_clean_sidecar=True)
    return ResolvedInput(*read_rows(input_path), used_clean_sidecar=False)
