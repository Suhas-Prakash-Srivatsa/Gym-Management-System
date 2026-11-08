import os
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from src.identity import next_payment_id
from src.ledger import COLUMNS, append_payment, read_payments
from src.models import Payment
from src.sheet import read_rows
from src.sidecar import (
    clean_members_path,
    corrections_stale,
    discard_corrections,
    keep_corrections,
    payments_path,
    ResolvedInput,
    read_clean_members,
    resolve_input,
    save_upload,
    write_clean_members,
)
from src.validation import Fix, apply_fixes, validate

FILES = Path(__file__).resolve().parent.parent / "src" / "files"


def payment(payment_id="P-0001", membership_id="MS-001", amount="1500.50",
            paid_on=date(2026, 11, 8), source="recorded",
            recorded_at=datetime(2026, 11, 8, 14, 30, 5, 123456)):
    return Payment(payment_id, membership_id, Decimal(amount), paid_on, source, recorded_at)


# --- Ledger ---


def test_append_creates_the_ledger_with_a_header_and_round_trips_exactly(tmp_path):
    ledger = tmp_path / "payments.csv"
    p = payment()
    append_payment(ledger, p)
    assert ledger.read_text(encoding="utf-8").splitlines()[0] == (
        "payment_id,membership_id,amount,paid_on,source,recorded_at")
    [back] = read_payments(ledger)
    assert back == p
    assert isinstance(back.amount, Decimal) and back.amount == Decimal("1500.50")
    assert type(back.recorded_at) is datetime and type(back.paid_on) is date


THREE_ROWS = (
    "payment_id,membership_id,amount,paid_on,source,recorded_at\n"
    "OPEN-MS-001,MS-001,6000,2026-06-01,opening,2026-06-01T00:00:00\n"
    "P-0001,MS-002,2000.00,2026-09-01,recorded,2026-09-01T10:00:00\n"
    "P-0002,MS-003,0.10,2026-10-01,recorded,2026-10-01T18:45:12.500000\n"
).encode("utf-8")


def test_reading_accepts_both_sources_with_exact_decimals(tmp_path):
    ledger = tmp_path / "payments.csv"
    ledger.write_bytes(THREE_ROWS)
    payments = read_payments(ledger)
    assert [(p.payment_id, p.source, p.amount) for p in payments] == [
        ("OPEN-MS-001", "opening", Decimal("6000")),
        ("P-0001", "recorded", Decimal("2000.00")),
        ("P-0002", "recorded", Decimal("0.10")),
    ]
    assert payments[2].recorded_at == datetime(2026, 10, 1, 18, 45, 12, 500000)


def test_appending_to_three_rows_yields_four_with_the_originals_byte_identical(tmp_path):
    ledger = tmp_path / "payments.csv"
    ledger.write_bytes(THREE_ROWS)
    append_payment(ledger, payment(payment_id="P-0003"))
    data = ledger.read_bytes()
    assert data.startswith(THREE_ROWS)
    assert len(read_payments(ledger)) == 4
    assert read_payments(ledger)[3] == payment(payment_id="P-0003")


def test_appending_after_a_last_row_without_newline_does_not_merge_rows(tmp_path):
    ledger = tmp_path / "payments.csv"
    ledger.write_bytes(THREE_ROWS.rstrip(b"\n"))
    append_payment(ledger, payment(payment_id="P-0003"))
    assert ledger.read_bytes().startswith(THREE_ROWS.rstrip(b"\n"))
    assert [p.payment_id for p in read_payments(ledger)] == [
        "OPEN-MS-001", "P-0001", "P-0002", "P-0003"]


def test_append_opens_the_file_in_append_mode_only(tmp_path, monkeypatch):
    modes = []
    real_open = Path.open

    def spy(self, mode="r", *args, **kwargs):
        modes.append(mode)
        return real_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", spy)
    ledger = tmp_path / "payments.csv"
    append_payment(ledger, payment())
    append_payment(ledger, payment(payment_id="P-0002"))
    assert not any(m.startswith(("w", "r+", "x")) or "+" in m for m in modes)
    assert "a" in modes


def test_two_appends_both_survive(tmp_path):
    ledger = tmp_path / "payments.csv"
    append_payment(ledger, payment(payment_id="P-0001"))
    append_payment(ledger, payment(payment_id="P-0002", amount="99.99"))
    assert [(p.payment_id, p.amount) for p in read_payments(ledger)] == [
        ("P-0001", Decimal("1500.50")), ("P-0002", Decimal("99.99"))]
    assert ledger.read_text(encoding="utf-8").count("payment_id") == 1


def test_missing_ledger_reads_as_empty(tmp_path):
    assert read_payments(tmp_path / "payments.csv") == []


@pytest.mark.parametrize("bad", [
    "P-1,MS-1,12.5.0,2026-01-01,recorded,2026-01-01T00:00:00",
    "P-1,MS-1,12,1st June,recorded,2026-01-01T00:00:00",
    "P-1,MS-1,12,2026-01-01,refund,2026-01-01T00:00:00",
])
def test_unreadable_ledger_row_raises_naming_the_line(tmp_path, bad):
    ledger = tmp_path / "payments.csv"
    ledger.write_text(",".join(COLUMNS) + "\n" + bad + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="line 2"):
        read_payments(ledger)


def _ids(*ids):
    return [payment(payment_id=i) for i in ids]


def test_ledger_still_exports_next_payment_id():
    import src.ledger

    assert src.ledger.next_payment_id is next_payment_id


def test_first_payment_id():
    assert next_payment_id([]) == "P-0001"


def test_next_payment_id_follows_the_highest_p_number_not_the_count():
    assert next_payment_id(_ids("P-0002", "OPEN-MS-001", "P-0010", "P-0003")) == "P-0011"


def test_next_payment_id_ignores_opening_and_foreign_ids():
    existing = _ids("OPEN-MS-001", "OPEN-P-0005", "P-abc", "X-0099", "P-0007-old")
    assert next_payment_id(existing) == "P-0001"


@pytest.mark.parametrize("existing", [
    [],
    ["P-0001"],
    ["P-9999"],
    ["P-0001", "P-0001"],
    ["OPEN-MS-1", "P-0042", "P-7"],
])
def test_next_payment_id_never_collides_and_is_never_an_opening_id(existing):
    new = next_payment_id(_ids(*existing))
    assert new not in existing
    assert not new.startswith("OPEN-")
    assert new.startswith("P-")


def test_next_payment_id_grows_past_four_digits():
    assert next_payment_id(_ids("P-9999")) == "P-10000"


def test_next_payment_id_after_appends_on_disk(tmp_path):
    ledger = tmp_path / "payments.csv"
    for _ in range(3):
        append_payment(ledger, payment(payment_id=next_payment_id(read_payments(ledger))))
    assert [p.payment_id for p in read_payments(ledger)] == ["P-0001", "P-0002", "P-0003"]


# --- Sidecar files ---


@pytest.fixture
def sheet(tmp_path):
    """A copy of Book1.csv in its own folder, so sidecars land beside it."""
    folder = tmp_path / "gym"
    folder.mkdir()
    path = folder / "Book1.csv"
    path.write_bytes((FILES / "Book1.csv").read_bytes())
    return path


def test_sidecar_paths_sit_next_to_the_input_not_the_working_directory(sheet, tmp_path, monkeypatch):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    relative = Path("..") / "gym" / "Book1.csv"
    for given in (sheet, relative, str(relative)):
        assert payments_path(given).resolve() == sheet.parent / "payments.csv"
        assert clean_members_path(given).resolve() == sheet.parent / "members_clean.csv"


@pytest.mark.parametrize("name", ["payments.csv", "members_clean.csv", "PAYMENTS.CSV"])
def test_an_input_named_like_a_sidecar_is_refused_rather_than_overwritten(tmp_path, name):
    with pytest.raises(ValueError, match="sidecar"):
        payments_path(tmp_path / name)
    with pytest.raises(ValueError, match="sidecar"):
        clean_members_path(tmp_path / name)


def test_resolve_input_uses_the_raw_sheet_when_there_is_no_clean_sidecar(sheet):
    rows, columns = read_rows(sheet)
    assert resolve_input(sheet) == ResolvedInput(rows, columns, used_clean_sidecar=False)
    assert read_clean_members(clean_members_path(sheet)) is None


def test_resolve_input_prefers_the_clean_sidecar_and_says_so(sheet):
    raw, _ = read_rows(sheet)
    cleaned = [dict(r) for r in raw[:2]]
    cleaned[0]["member_name"] = "Suhas P."
    write_clean_members(clean_members_path(sheet), cleaned)
    resolved = resolve_input(sheet)
    assert resolved.used_clean_sidecar is True
    assert resolved.rows == cleaned
    assert resolved.columns == read_rows(sheet)[1]


def test_clean_members_keep_the_member_id_apply_fixes_added(tmp_path):
    rows, columns = read_rows(FILES / "Book1_errors.csv")
    # The errors fixture has a Member ID column; drop it, as a sheet without one would.
    rows = [{k: v for k, v in r.items() if k != "member_id"} for r in rows]
    columns = [c for c in columns if c != "member_id"]
    issue = next(i for i in validate(rows, columns).issues if i.code == "duplicate_name")
    fixed = apply_fixes(rows, [Fix(issue.row_number, issue.column, "same_person")])
    assert "member_id" in fixed[2] and "member_id" not in fixed[0]

    path = tmp_path / "members_clean.csv"
    write_clean_members(path, fixed)
    back, back_columns = read_rows(path)
    assert "member_id" in back_columns
    assert back[2]["member_id"] == back[3]["member_id"] == fixed[2]["member_id"]
    assert back[0]["member_id"] == ""
    assert set(back_columns) >= set(columns)


def test_clean_members_use_canonical_headers_and_round_trip_through_the_reader(tmp_path):
    rows, columns = read_rows(FILES / "Book1.csv")
    path = tmp_path / "members_clean.csv"
    write_clean_members(path, rows)
    header = path.read_text(encoding="utf-8-sig").splitlines()[0].split(",")
    assert header == columns  # Book1's columns, already in canonical order
    assert read_rows(path) == (rows, columns)
    assert read_clean_members(path) == rows


def test_clean_members_keep_unrecognised_columns_and_odd_values(tmp_path):
    rows = [{"member_name": "Rao, Vandana", "membership_type": "Yearly", "Notes": 'said "next week"'},
            {"member_name": "Ünal", "membership_type": "Monthly", "Notes": ""}]
    path = tmp_path / "members_clean.csv"
    write_clean_members(path, rows)
    back, columns = read_rows(path)
    assert columns == ["member_id", "member_name", "membership_type", "Notes"]
    assert [r["member_name"] for r in back] == ["Rao, Vandana", "Ünal"]
    assert back[0]["Notes"] == 'said "next week"'


def test_rewriting_clean_members_replaces_the_previous_snapshot(tmp_path):
    path = tmp_path / "members_clean.csv"
    rows, _ = read_rows(FILES / "Book1.csv")
    write_clean_members(path, rows)
    write_clean_members(path, rows[:1])
    assert read_clean_members(path) == rows[:1]
    assert [p.name for p in tmp_path.iterdir()] == ["members_clean.csv"]  # no temp left behind


def test_nothing_writes_to_the_input_sheet(sheet):
    before = (sheet.read_bytes(), os.stat(sheet).st_mtime_ns)
    rows = resolve_input(sheet).rows
    append_payment(payments_path(sheet), payment())
    write_clean_members(clean_members_path(sheet), rows)
    resolve_input(sheet)
    read_payments(payments_path(sheet))
    assert (sheet.read_bytes(), os.stat(sheet).st_mtime_ns) == before
    assert sorted(p.name for p in sheet.parent.iterdir()) == [
        "Book1.csv", "members_clean.csv", "payments.csv"]


# --- Rework: money safety and columns ---


@pytest.mark.parametrize("amount", ["12.345", "1E+3", "+5", "-0.01", "0.00", "sNaN", "", " 5"])
def test_ledger_rejects_amounts_that_are_not_plain_positive_rupees(tmp_path, amount):
    ledger = tmp_path / "payments.csv"
    ledger.write_text(",".join(COLUMNS) + "\n"
                      + f"P-1,MS-1,{amount},2026-01-01,recorded,2026-01-01T00:00:00\n",
                      encoding="utf-8")
    with pytest.raises(ValueError, match="line 2"):
        read_payments(ledger)


@pytest.mark.parametrize("amount", ["0", "-500", "12.345", "NaN", "Infinity"])
def test_append_refuses_an_amount_the_ledger_could_not_read_back(tmp_path, amount):
    ledger = tmp_path / "payments.csv"
    with pytest.raises(ValueError):
        append_payment(ledger, payment(amount=amount))
    assert not ledger.exists()


def test_append_refuses_a_ledger_whose_columns_were_reordered(tmp_path):
    ledger = tmp_path / "payments.csv"
    reordered = b"membership_id,payment_id,amount,paid_on,source,recorded_at\r\n"
    ledger.write_bytes(reordered)
    with pytest.raises(ValueError, match="columns"):
        append_payment(ledger, payment())
    assert ledger.read_bytes() == reordered


def test_reordered_ledger_still_reads_by_column_name(tmp_path):
    ledger = tmp_path / "payments.csv"
    ledger.write_text("membership_id,payment_id,amount,paid_on,source,recorded_at\n"
                      "MS-001,P-0001,1500.50,2026-11-08,recorded,2026-11-08T14:30:05.123456\n",
                      encoding="utf-8")
    assert read_payments(ledger) == [payment()]


def test_append_to_a_ledger_excel_resaved_with_a_bom(tmp_path):
    ledger = tmp_path / "payments.csv"
    ledger.write_bytes(b"\xef\xbb\xbf" + ",".join(COLUMNS).encode() + b"\r\n")
    append_payment(ledger, payment())
    assert read_payments(ledger) == [payment()]


def test_clean_members_are_written_with_a_utf8_bom(tmp_path):
    path = tmp_path / "members_clean.csv"
    write_clean_members(path, [{"member_name": "Ünal"}])
    assert path.read_bytes().startswith(b"\xef\xbb\xbfmember_id,member_name\r\n")


def test_resolve_input_keeps_the_columns_validation_needs(tmp_path):
    folder = tmp_path / "gym"
    folder.mkdir()
    sheet = folder / "Book1.csv"
    sheet.write_text("Name,Member,Membership Type,Notes\n", encoding="utf-8")  # headers, no rows
    resolved = resolve_input(sheet)
    assert resolved.rows == []
    assert resolved.columns == ["member_name", "member_name", "membership_type", "Notes"]
    codes = {i.code for i in validate(resolved.rows, resolved.columns).issues}
    assert "ambiguous_column" in codes and "missing_column" in codes


# --- Upload working copies and stale corrections (ticket 10) ---


def _age(path, seconds):
    """Make `path` look `seconds` older than now, so mtime order is unambiguous."""
    stamp = os.stat(path).st_mtime_ns - seconds * 1_000_000_000
    os.utime(path, ns=(stamp, stamp))


def test_an_upload_is_saved_as_a_working_copy_in_its_own_folder(tmp_path):
    data = (FILES / "Book1.csv").read_bytes()
    path = save_upload(tmp_path / "data", "Book1.csv", data)
    assert path == (tmp_path / "data" / "Book1_csv" / "Book1.csv").resolve()
    assert path.read_bytes() == data
    assert payments_path(path).parent == path.parent  # sidecars sit beside the copy
    other = save_upload(tmp_path / "data", "Book1.xlsx", b"x")
    assert other.parent != path.parent  # different sheets never share a ledger


def test_an_upload_name_cannot_escape_the_data_folder(tmp_path):
    path = save_upload(tmp_path / "data", "..\\..\\evil/Book1.csv", b"a,b\n")
    assert path.parent.parent == (tmp_path / "data").resolve()


@pytest.mark.parametrize("name", ["payments.csv", "members_clean.csv", "", "   "])
def test_an_upload_named_like_a_sidecar_or_nameless_is_refused(tmp_path, name):
    with pytest.raises(ValueError):
        save_upload(tmp_path / "data", name, b"a,b\n")
    assert not (tmp_path / "data").exists() or not any((tmp_path / "data").rglob("*.csv"))


def test_re_uploading_identical_bytes_does_not_touch_the_copy(tmp_path):
    data = (FILES / "Book1.csv").read_bytes()
    path = save_upload(tmp_path / "data", "Book1.csv", data)
    _age(path, 60)
    before = os.stat(path).st_mtime_ns
    save_upload(tmp_path / "data", "Book1.csv", data)
    assert os.stat(path).st_mtime_ns == before


def test_re_uploading_different_bytes_makes_old_corrections_stale(tmp_path):
    path = save_upload(tmp_path / "data", "Book1.csv", (FILES / "Book1.csv").read_bytes())
    rows, _ = read_rows(path)
    write_clean_members(clean_members_path(path), rows)
    _age(path, 120)
    _age(clean_members_path(path), 60)
    assert corrections_stale(path) is False
    save_upload(tmp_path / "data", "Book1.csv", (FILES / "Book1_errors.csv").read_bytes())
    assert corrections_stale(path) is True


def test_corrections_are_stale_when_the_sheet_is_newer(sheet):
    assert corrections_stale(sheet) is False  # no corrections at all
    write_clean_members(clean_members_path(sheet), read_rows(sheet)[0])
    _age(sheet, 60)
    assert corrections_stale(sheet) is False
    _age(clean_members_path(sheet), 120)
    assert corrections_stale(sheet) is True


def test_discarding_corrections_falls_back_to_the_sheet_and_keeps_a_backup(sheet):
    rows, _ = read_rows(sheet)
    write_clean_members(clean_members_path(sheet), rows[:1])
    discard_corrections(sheet)
    assert resolve_input(sheet).used_clean_sidecar is False
    backup = sheet.parent / "members_clean.csv.bak"
    assert read_rows(backup)[0] == rows[:1]
    discard_corrections(sheet)  # nothing left to discard: no error


def test_keeping_corrections_clears_the_stale_warning(sheet):
    write_clean_members(clean_members_path(sheet), read_rows(sheet)[0])
    _age(clean_members_path(sheet), 120)
    assert corrections_stale(sheet) is True
    keep_corrections(sheet)
    assert corrections_stale(sheet) is False
    assert resolve_input(sheet).used_clean_sidecar is True


def test_stale_checks_and_discards_never_write_the_input(sheet):
    before = (sheet.read_bytes(), os.stat(sheet).st_mtime_ns)
    write_clean_members(clean_members_path(sheet), read_rows(sheet)[0])
    corrections_stale(sheet)
    keep_corrections(sheet)
    discard_corrections(sheet)
    assert (sheet.read_bytes(), os.stat(sheet).st_mtime_ns) == before
