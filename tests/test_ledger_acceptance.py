"""Independent acceptance tests for ticket 07 (ledger and sidecars), written by the tester.

Every case works in a real temp directory with a copy of Book1.csv, so the
owner's fixture is never at risk.
"""

import hashlib
import os
import shutil
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from src.assemble import build_dataset, with_ledger
from src.balances import all_statuses
from src.ledger import COLUMNS, append_payment, next_payment_id, read_payments
from src.models import Payment
from src.sheet import read_rows
from src.sidecar import clean_members_path, payments_path, resolve_input, write_clean_members
from src.validation import validate

BOOK1 = Path(__file__).resolve().parent.parent / "src" / "files" / "Book1.csv"
TODAY = date(2026, 11, 8)
HEADER = b"payment_id,membership_id,amount,paid_on,source,recorded_at\r\n"


def pay(pid, amount="1000", membership_id="MS-001", paid_on=TODAY):
    return Payment(pid, membership_id, Decimal(amount), paid_on, "recorded",
                   datetime(2026, 11, 8, 10, 30))


@pytest.fixture
def sheet(tmp_path):
    path = tmp_path / "Book1.csv"
    shutil.copy(BOOK1, path)
    return path


def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest(), os.stat(path).st_mtime_ns


def totals(dataset):
    owing = [s for s in all_statuses(dataset, TODAY) if s.outstanding > 0]
    return len(owing), sum(s.outstanding for s in owing)


# --- Ledger file ------------------------------------------------------------

def test_header_is_exactly_the_ticket_columns(tmp_path):
    p = tmp_path / "payments.csv"
    append_payment(p, pay("P-0001"))
    assert COLUMNS == ("payment_id", "membership_id", "amount", "paid_on", "source", "recorded_at")
    assert p.read_bytes().startswith(HEADER)


@pytest.mark.parametrize("amount", ["0.10", "0.01", "12000.50", "6250", "99999999.99"])
def test_decimal_amounts_round_trip_exactly(tmp_path, amount):
    p = tmp_path / "payments.csv"
    append_payment(p, pay("P-0001", amount))
    [back] = read_payments(p)
    assert type(back.amount) is Decimal
    assert back.amount == Decimal(amount) and str(back.amount) == amount
    assert back == pay("P-0001", amount)


def test_existing_bytes_are_a_prefix_after_each_append(tmp_path):
    p = tmp_path / "payments.csv"
    for n in range(1, 4):
        append_payment(p, pay(f"P-{n:04d}"))
    before = p.read_bytes()
    append_payment(p, pay("P-0004", "0.10"))
    assert p.read_bytes().startswith(before)
    assert [x.payment_id for x in read_payments(p)] == ["P-0001", "P-0002", "P-0003", "P-0004"]


def test_append_after_a_crash_truncated_last_line_keeps_it_separate_and_flags_it(tmp_path):
    p = tmp_path / "payments.csv"
    append_payment(p, pay("P-0001"))
    truncated = p.read_bytes() + b"P-0002,MS-001,60"  # crash mid-row: amount cut short
    p.write_bytes(truncated)
    append_payment(p, pay("P-0003"))
    data = p.read_bytes()
    assert data.startswith(truncated)
    assert data.endswith(b"\r\nP-0003,MS-001,1000,2026-11-08,recorded,2026-11-08T10:30:00\r\n")
    # The partial row must never be counted as a ₹60 payment.
    with pytest.raises(ValueError, match="line 3"):
        read_payments(p)


def test_append_after_a_complete_but_unterminated_last_line(tmp_path):
    p = tmp_path / "payments.csv"
    p.write_bytes(HEADER + b"P-0001,MS-001,1000,2026-11-08,recorded,2026-11-08T10:30:00")
    append_payment(p, pay("P-0002"))
    assert [x.payment_id for x in read_payments(p)] == ["P-0001", "P-0002"]


def test_header_only_and_empty_files(tmp_path):
    p = tmp_path / "payments.csv"
    p.write_bytes(HEADER)
    assert read_payments(p) == []
    p.write_bytes(b"")
    append_payment(p, pay("P-0001"))
    assert p.read_bytes().count(b"payment_id") == 1
    assert len(read_payments(p)) == 1


def test_unicode_survives_the_ledger(tmp_path):
    p = tmp_path / "payments.csv"
    append_payment(p, pay("P-0001", membership_id="MS-Ünal-01"))
    assert read_payments(p)[0].membership_id == "MS-Ünal-01"


@pytest.mark.parametrize("amount", ["NaN", "Infinity", "-500", "0"])
def test_ledger_rejects_amounts_that_are_not_money_that_arrived(tmp_path, amount):
    p = tmp_path / "payments.csv"
    p.write_bytes(HEADER + f"P-0001,MS-001,{amount},2026-11-08,recorded,2026-11-08T10:30:00\r\n"
                  .encode())
    with pytest.raises(ValueError):
        read_payments(p)


def test_ledger_resaved_with_a_bom_still_reads(tmp_path):
    p = tmp_path / "payments.csv"
    append_payment(p, pay("P-0001"))
    p.write_bytes(b"\xef\xbb\xbf" + p.read_bytes())
    assert len(read_payments(p)) == 1


# --- next_payment_id --------------------------------------------------------

def test_next_id_from_the_raw_ledger_skips_orphans_too(tmp_path):
    p = tmp_path / "payments.csv"
    append_payment(p, pay("P-0001"))
    append_payment(p, pay("P-0007", membership_id="MS-999"))  # an orphan
    assert next_payment_id(read_payments(p)) == "P-0008"


# --- Ledger merged into the sheet -------------------------------------------

def test_recorded_payment_reduces_the_receivable_exactly(sheet):
    ds = build_dataset(resolve_input(sheet).rows)
    ledger = payments_path(sheet)
    append_payment(ledger, pay("P-0001", "1000.10"))
    merge = with_ledger(ds, read_payments(ledger))
    assert totals(ds) == (19, Decimal("97300"))
    assert totals(merge.dataset) == (19, Decimal("96299.90"))


def test_payments_for_unknown_memberships_are_reported_not_counted(sheet):
    ds = build_dataset(resolve_input(sheet).rows)
    ledger = payments_path(sheet)
    append_payment(ledger, pay("P-0001", membership_id="MS-999"))
    append_payment(ledger, pay("P-0002", membership_id="ms-001"))  # case differs: no match
    merge = with_ledger(ds, read_payments(ledger))
    assert [p.payment_id for p in merge.orphaned] == ["P-0001", "P-0002"]
    assert totals(merge.dataset) == (19, Decimal("97300"))
    msids = {m.membership_id for m in merge.dataset.memberships}
    assert all(p.membership_id in msids for p in merge.dataset.payments)


# --- Input sheet is read-only, sidecars beside it ---------------------------

def test_full_cycle_leaves_the_input_sheet_byte_identical_with_its_mtime(sheet):
    before = fingerprint(sheet)
    resolved = resolve_input(sheet)
    assert not resolved.used_clean_sidecar
    rows = resolved.rows
    write_clean_members(clean_members_path(sheet), rows)
    append_payment(payments_path(sheet), pay("P-0001"))
    rows = resolve_input(sheet).rows
    with_ledger(build_dataset(rows), read_payments(payments_path(sheet)))
    write_clean_members(clean_members_path(sheet), rows)  # second snapshot, via os.replace
    assert fingerprint(sheet) == before
    assert sorted(p.name for p in sheet.parent.iterdir()) == [
        "Book1.csv", "members_clean.csv", "payments.csv"]  # no stray .tmp


def test_sidecars_land_beside_the_input_not_in_the_cwd(sheet, tmp_path, monkeypatch):
    elsewhere = tmp_path / "cwd"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    assert payments_path(sheet) == sheet.resolve().parent / "payments.csv"
    assert clean_members_path(sheet) == sheet.resolve().parent / "members_clean.csv"


def test_sidecar_wins_on_a_later_run_and_validates_clean(sheet):
    rows, _ = read_rows(sheet)
    corrected = [dict(r) for r in rows]
    corrected[0]["member_name"] = "Suhas Prakash Srivatsa"
    write_clean_members(clean_members_path(sheet), corrected)

    resolved = resolve_input(sheet)
    rows = resolved.rows
    assert resolved.used_clean_sidecar is True
    assert rows[0]["member_name"] == "Suhas Prakash Srivatsa"
    assert rows == corrected  # canonical headers read back to the same keys
    assert validate(rows, resolved.columns).is_clean
    assert totals(build_dataset(rows)) == (19, Decimal("97300"))


def test_sidecar_preserves_fix_added_member_ids_on_some_rows_only(sheet):
    rows, _ = read_rows(sheet)
    no_ids = [{**r, "member_id": ""} for r in rows]
    no_ids[0]["member_id"] = "GEN-001"
    write_clean_members(clean_members_path(sheet), no_ids)
    back = resolve_input(sheet).rows
    assert back[0]["member_id"] == "GEN-001" and back[1]["member_id"] == ""


# --- Rework checks ------------------------------------------------------------

def test_append_refuses_a_reordered_header_and_leaves_the_file_untouched(tmp_path):
    p = tmp_path / "payments.csv"
    p.write_bytes(b"membership_id,payment_id,amount,paid_on,source,recorded_at\r\n"
                  b"MS-001,P-0001,100,2026-11-01,recorded,2026-11-08T00:00:00\r\n")
    before = fingerprint(p)
    with pytest.raises(ValueError):
        append_payment(p, pay("P-0002"))
    assert fingerprint(p) == before


@pytest.mark.parametrize("amount", ["6E+3", "1000.000", "0.001", "-1", "0"])
def test_append_refuses_amounts_it_could_not_read_back_and_writes_nothing(tmp_path, amount):
    p = tmp_path / "payments.csv"
    with pytest.raises(ValueError):
        append_payment(p, pay("P-0001", amount))
    assert not p.exists()
    append_payment(p, pay("P-0001"))
    before = fingerprint(p)
    with pytest.raises(ValueError):
        append_payment(p, pay("P-0002", amount))
    assert fingerprint(p) == before


def test_append_to_a_bom_ledger_keeps_it_readable(tmp_path):
    p = tmp_path / "payments.csv"
    append_payment(p, pay("P-0001"))
    p.write_bytes(b"\xef\xbb\xbf" + p.read_bytes())
    append_payment(p, pay("P-0002"))
    assert [x.payment_id for x in read_payments(p)] == ["P-0001", "P-0002"]


def test_resolve_input_keeps_duplicate_and_header_only_columns(tmp_path):
    sheet = tmp_path / "sheet.csv"
    sheet.write_bytes(b"Member Name,Paid Amount,Paid\r\n")
    resolved = resolve_input(sheet)
    assert resolved.rows == [] and resolved.columns == ["member_name", "paid_amount", "paid_amount"]
    report = validate(resolved.rows, resolved.columns)
    assert report.is_fatal and "ambiguous_column" in {i.code for i in report.issues}


def test_resolve_input_columns_come_from_the_file_actually_used(sheet):
    rows, _ = read_rows(sheet)
    write_clean_members(clean_members_path(sheet), [{k: v for k, v in r.items() if k != "member_id"}
                                                    for r in rows])
    sheet.write_bytes(b"Member Name,Notes\r\n")  # a copy in tmp_path, never the fixture
    resolved = resolve_input(sheet)
    assert resolved.used_clean_sidecar
    assert resolved.columns[0] == "member_id" and "notes" not in [c.casefold() for c in resolved.columns]
