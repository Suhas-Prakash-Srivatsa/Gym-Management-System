"""The Payment Ledger on disk (shell): `payments.csv`, append-only.

Payments are only ever appended: the file is opened in mode "a", which
cannot touch bytes already written, so a crash mid-write can at worst leave
one partial last row, never lose history. Nothing here rewrites the file.
"""

import csv
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from src.identity import next_payment_id
from src.models import Payment

# next_payment_id lives in identity.py (pure core, beside the other ID rules);
# re-exported so `from src.ledger import next_payment_id` keeps working.
__all__ = ["COLUMNS", "read_payments", "append_payment", "check_appendable", "next_payment_id"]

COLUMNS = ("payment_id", "membership_id", "amount", "paid_on", "source", "recorded_at")


def read_payments(path) -> list[Payment]:
    """Every Payment in the ledger, in file order; [] when the file does not exist yet.

    Accepts both sources (`opening`, `recorded`). Columns are matched by name,
    so a reordered file still reads. Amounts are parsed straight to Decimal
    from their text, never via float, and must be plain positive rupees
    (see `_amount`). A row that cannot be read raises ValueError naming its line: the ledger is the tool's own file, so
    a bad row means it was edited by hand and must not be guessed at.
    """
    path = Path(path)
    if not path.exists():
        return []
    # utf-8-sig: Excel adds a BOM when it re-saves the file.
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        missing = set(COLUMNS) - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"{path.name}: missing column(s) {', '.join(sorted(missing))}.")
        return [_payment(record, path, reader.line_num) for record in reader
                if any((v or "").strip() for v in record.values())]


def _payment(record: dict, path: Path, line: int) -> Payment:
    try:
        source = record["source"]
        if source not in ("opening", "recorded"):
            raise ValueError(f"unknown source {source!r}")
        return Payment(
            payment_id=record["payment_id"],
            membership_id=record["membership_id"],
            amount=_amount(record["amount"]),
            paid_on=date.fromisoformat(record["paid_on"]),
            source=source,
            recorded_at=datetime.fromisoformat(record["recorded_at"]),
        )
    except (ValueError, TypeError, InvalidOperation) as exc:
        raise ValueError(f"{path.name} line {line}: unreadable payment ({exc}).") from exc


# Digits, optionally a point and one or two more: what a rupee amount looks like.
# Rules out NaN, Infinity, signs, exponents and sub-paisa fractions in one go.
_AMOUNT = re.compile(r"[0-9]+(\.[0-9]{1,2})?")


def _amount(text: str) -> Decimal:
    """A Payment amount: money that actually arrived, so finite, above 0, at most 2 dp.

    A negative amount would silently raise an Outstanding Balance, a zero one
    would restart the grace clock for nothing, and NaN/Infinity break every
    comparison downstream.
    """
    if not _AMOUNT.fullmatch(text) or Decimal(text) <= 0:
        raise ValueError(f"amount {text!r} is not a positive rupee amount with at most 2 decimals")
    return Decimal(text)


def append_payment(path, payment: Payment) -> None:
    """Append one Payment as one row, creating the file with its header when absent.

    Refuses (ValueError, nothing written) an amount `read_payments` would
    reject, and a file whose header is not exactly COLUMNS: if the owner
    reordered the columns in Excel, a row written in COLUMNS order would read
    back with its fields swapped. If the last row lacks a line ending (a hand
    edit or a crash), one is appended first so the new row cannot fuse onto
    it; existing bytes are never altered.
    """
    path = Path(path)
    _amount(str(payment.amount))
    new = check_appendable(path)
    unterminated = not new and not _ends_with_newline(path)
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if new:
            writer.writerow(COLUMNS)
        elif unterminated:
            f.write("\r\n")
        writer.writerow([
            payment.payment_id,
            payment.membership_id,
            str(payment.amount),
            payment.paid_on.isoformat(),
            payment.source,
            payment.recorded_at.isoformat(),
        ])


def check_appendable(path) -> bool:
    """Raise when a Payment could not be appended to the ledger at `path` right now.

    ValueError for a header that is not exactly COLUMNS; PermissionError
    when the file cannot be opened for appending (open in Excel). Lets a
    caller that saves something else first (adding a member with money paid
    at sign-up) find out before writing anything; the disk can of course
    still fail in between. Writes nothing. Returns True when the file does
    not exist yet (or is empty), so the next append creates it.
    """
    path = Path(path)
    if not path.exists() or path.stat().st_size == 0:
        return True
    header = _header(path)
    if header != list(COLUMNS):
        raise ValueError(_header_problem(path, header))
    with path.open("ab"):  # raises PermissionError while Excel holds it
        pass
    return False


def _header_problem(path: Path, header: list[str]) -> str:
    """Why `header` cannot be appended to, in terms of what the owner changed."""
    expected = ", ".join(COLUMNS)
    added = [c for c in header if c not in COLUMNS]
    missing = [c for c in COLUMNS if c not in header]
    if added or missing:
        changes = "; ".join(part for part in (
            f"added column(s) {', '.join(added)}" if added else "",
            f"missing column(s) {', '.join(missing)}" if missing else "") if part)
        return (f"{path.name} has {changes}. It must have exactly the columns {expected}: "
                "remove or restore them, save it, then record the payment again.")
    return (f"{path.name} has its columns in the order {', '.join(header)}; expected "
            f"{expected}. Restore that column order before recording payments.")


def _header(path: Path) -> list[str]:
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        return next(csv.reader(f), [])


def _ends_with_newline(path: Path) -> bool:
    with path.open("rb") as f:
        f.seek(-1, 2)
        return f.read(1) in (b"\n", b"\r")
