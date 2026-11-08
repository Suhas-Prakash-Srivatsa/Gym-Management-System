"""Where derived files live (shell): sidecars beside the owner's sheet (ADR 0002).

The input sheet is read, never written. Recorded payments go to
`payments.csv` and in-dashboard corrections to `members_clean.csv`, both in
the input's folder; on later runs the cleaned sidecar takes precedence, and
`resolve_input` says when it did so the owner knows they see corrected data.
"""

import csv
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.models import RawRow
from src.sheet import HEADER_ALIASES, read_rows

PAYMENTS_NAME = "payments.csv"
CLEAN_MEMBERS_NAME = "members_clean.csv"

# Canonical columns in sheet order (member_id, member_name, membership_id, ...).
_CANONICAL = tuple(dict.fromkeys(HEADER_ALIASES.values()))


def _refuse_sidecar_name(path: Path) -> None:
    if path.name.casefold() in (PAYMENTS_NAME, CLEAN_MEMBERS_NAME):
        raise ValueError(
            f"The input sheet is named {path.name!r}, the name of a sidecar file the tool "
            "writes; rename the sheet so it cannot be overwritten.")


def _beside(input_path, name: str) -> Path:
    path = Path(input_path)
    _refuse_sidecar_name(path)
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


def check_sheet(input_path) -> Path:
    """The sheet's path, if it names a file that exists.

    FileNotFoundError when nothing is there; ValueError for a folder, which
    Windows would otherwise report as a misleading "permission denied".
    """
    path = Path(input_path)
    if path.is_dir():
        raise ValueError(f"{path} is a folder, not a sheet. Enter the path of the CSV or "
                         "Excel file itself.")
    if not path.exists():
        raise FileNotFoundError(2, "No such file", str(path))
    return path


def resolve_input(input_path) -> ResolvedInput:
    """Prefer `members_clean.csv` beside the input; otherwise read the sheet itself."""
    check_sheet(input_path)
    clean_path = clean_members_path(input_path)
    if clean_path.exists():
        return ResolvedInput(*read_rows(clean_path), used_clean_sidecar=True)
    return ResolvedInput(*read_rows(input_path), used_clean_sidecar=False)


# --- Uploads and stale corrections ---

BACKUP_SUFFIX = ".bak"
_INVALID_NAME_CHARS = re.compile(r'[<>:"|?*\x00-\x1f]')
_RESERVED_STEMS = {"CON", "PRN", "AUX", "NUL",
                   *(f"COM{n}" for n in range(1, 10)), *(f"LPT{n}" for n in range(1, 10))}


def _check_upload_name(name: str) -> None:
    """Refuse a name Windows cannot store as a file, with a reason the owner can act on."""
    if name in ("", ".", "..") or not name.strip():
        raise ValueError("The uploaded file has no usable name.")
    if _INVALID_NAME_CHARS.search(name):
        raise ValueError(f"The file name {name!r} contains a character Windows does not allow "
                         '(< > : " | ? * or a control character). Rename it and upload again.')
    if name.split(".")[0].strip().upper() in _RESERVED_STEMS:
        raise ValueError(f"The file name {name!r} is reserved by Windows. Rename it and "
                         "upload again.")
    if name.endswith((".", " ")):
        raise ValueError(f"The file name {name!r} ends with a dot or a space, which Windows "
                         "does not allow. Rename it and upload again.")


def save_upload(data_dir, filename: str, data: bytes) -> Path:
    """Keep an uploaded sheet as a working copy, so its sidecars have a folder to live in.

    A browser upload has no path on disk, so the bytes are saved to
    `<data_dir>/<stem>_<ext>/<filename>`: one folder per sheet name, so two
    different sheets never share a Payment Ledger. Only the base name of
    `filename` is used, so it cannot escape `data_dir`. Identical bytes leave
    the copy untouched; different bytes replace it (atomically), which makes
    any earlier corrections stale (`corrections_stale`) rather than silently
    mixing them with the new sheet. The owner's own file is never involved.
    """
    name = re.split(r"[\\/]", filename)[-1]  # base name only, whichever separator
    _check_upload_name(name)
    _refuse_sidecar_name(Path(name))
    folder = Path(data_dir).resolve() / "_".join(filter(None, (Path(name).stem, Path(name).suffix[1:])))
    path = folder / name
    if path.exists() and path.read_bytes() == data:
        return path
    folder.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_bytes(data)
    os.replace(temp, path)
    return path


def corrections_stale(input_path) -> bool:
    """True when the sheet changed after its corrections were saved.

    The cleaned sidecar would then hide whatever the owner added or changed
    in the sheet since, so the shell must ask before using it.
    """
    clean = clean_members_path(input_path)
    return clean.exists() and os.stat(input_path).st_mtime_ns > os.stat(clean).st_mtime_ns


def discard_corrections(input_path, stamp: datetime) -> Path | None:
    """Stop using the cleaned sidecar. It is moved aside, never deleted.

    The backup is `members_clean.csv.<YYYYMMDD-HHMMSS>.bak`, from `stamp`
    (the shell's clock; nothing here reads it), with `-2`, `-3`, ... added if
    that name is taken, so a later discard never overwrites an earlier one.
    Returns the backup's path, or None when there was nothing to discard.
    """
    clean = clean_members_path(input_path)
    if not clean.exists():
        return None
    base = f"{clean.name}.{stamp:%Y%m%d-%H%M%S}"
    backup = clean.with_name(base + BACKUP_SUFFIX)
    n = 1
    while backup.exists():
        n += 1
        backup = clean.with_name(f"{base}-{n}{BACKUP_SUFFIX}")
    os.replace(clean, backup)
    return backup


def keep_corrections(input_path) -> None:
    """The owner chose to keep the corrections despite a newer sheet: mark them current."""
    clean = clean_members_path(input_path)
    sheet_time = os.stat(input_path).st_mtime_ns
    stamp = max(os.stat(clean).st_mtime_ns, sheet_time) + 1
    os.utime(clean, ns=(stamp, stamp))
