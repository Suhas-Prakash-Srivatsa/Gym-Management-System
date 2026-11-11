"""The demo gym's working copy (src/sidecar.py): isolated, and reset on demand."""

from datetime import date
from pathlib import Path

import pytest

from src.assemble import build_dataset, with_ledger
from src.balances import all_statuses
from src.ledger import read_payments
from src.samples import FILES, demo_sheet_csv
from src.sheet import read_rows
from src.sidecar import (
    DemoResetIncomplete,
    DEMO_FOLDER,
    clean_members_path,
    demo_path,
    is_demo,
    payments_path,
    reset_demo,
    resolve_input,
    rows_only_in_corrections,
    save_upload,
    working_copies,
    write_clean_members,
)
from src.validation import validate
from src.views import tiles

TODAY = date(2026, 11, 8)
BOOK1 = FILES / "Book1.csv"


def test_the_demo_lives_in_its_own_folder_and_is_never_listed_as_an_upload(tmp_path):
    data = tmp_path / "data"
    upload = save_upload(data, "Book1.csv", b"a\n")
    demo = reset_demo(data, demo_sheet_csv(TODAY))
    assert demo == demo_path(data) and demo.parent.name == DEMO_FOLDER
    assert working_copies(data) == [upload]
    assert is_demo(data, demo) and not is_demo(data, upload)


def test_no_upload_can_land_in_the_demo_folder(tmp_path):
    data = tmp_path / "data"
    for name in ("Sample.csv", "sample.xlsx", "demo_gym.csv"):
        assert save_upload(data, name, b"a\n").parent != demo_path(data).parent


def test_resetting_clears_payments_and_added_members_and_leaves_uploads_alone(tmp_path):
    data = tmp_path / "data"
    upload = save_upload(data, "Book1.csv", b"a\n")
    payments_path(upload).write_text("theirs", encoding="utf-8")
    demo = reset_demo(data, demo_sheet_csv(TODAY))
    payments_path(demo).write_text("demo payments", encoding="utf-8")
    clean_members_path(demo).write_text("demo members", encoding="utf-8")
    (demo.parent / "members_clean.csv.20261108-120000.bak").write_text("x", encoding="utf-8")
    again = reset_demo(data, demo_sheet_csv(TODAY))
    assert again == demo
    assert sorted(p.name for p in demo.parent.iterdir()) == [demo.name]
    assert demo.read_bytes() == demo_sheet_csv(TODAY)
    assert payments_path(upload).read_text(encoding="utf-8") == "theirs"


def test_the_demo_figures_are_computed_from_its_sheet(tmp_path):
    # Hand-derived from src/files/demo_members.csv on its anchor day, 2026-11-08:
    # 15 memberships of 14 members worth ₹1,51,000; 12 still owe ₹70,500;
    # DM-001, -003, -005, -006, -011 and -015 are overdue, ₹29,500 between them.
    demo = reset_demo(tmp_path / "data", demo_sheet_csv(TODAY))
    resolved = resolve_input(demo)
    assert validate(resolved.rows, resolved.columns).is_clean
    merge = with_ledger(build_dataset(resolved.rows), read_payments(payments_path(demo)))
    figures = tiles(all_statuses(merge.dataset, TODAY))
    assert figures["display"] == {
        "Total Members": "14",
        "Total Membership Value": "₹1,51,000",
        "Total Receivable": "₹70,500",
        "Overdue": "₹29,500",
    }
    assert figures["overdue_count"] == 6


# --- Fix round 1: locked files ---------------------------------------------------------------

def _excel_holds(monkeypatch, name):
    """Make `name` impossible to open for writing or delete, as while Excel has it open."""
    real_open, real_unlink = Path.open, Path.unlink

    def opened(self, mode="r", *args, **kwargs):
        if self.name == name and any(c in mode for c in "wa+"):
            raise PermissionError(13, "Permission denied", str(self))
        return real_open(self, mode, *args, **kwargs)

    def unlink(self, missing_ok=False):
        if self.name == name:
            raise PermissionError(13, "Permission denied", str(self))
        return real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "open", opened)
    monkeypatch.setattr(Path, "unlink", unlink)


@pytest.fixture
def used_demo(tmp_path):
    data = tmp_path / "data"
    demo = reset_demo(data, demo_sheet_csv(TODAY))
    payments_path(demo).write_text("demo payments", encoding="utf-8")
    clean_members_path(demo).write_text("demo members", encoding="utf-8")
    return data, demo


def _unchanged(demo):
    return (payments_path(demo).read_text(encoding="utf-8") == "demo payments"
            and clean_members_path(demo).read_text(encoding="utf-8") == "demo members"
            and demo.read_bytes() == demo_sheet_csv(TODAY))


@pytest.mark.parametrize("locked", ["payments.csv", "members_clean.csv", "demo_gym.csv"])
def test_any_file_open_in_excel_stops_the_reset_before_anything_is_deleted(
        used_demo, monkeypatch, locked):
    data, demo = used_demo
    _excel_holds(monkeypatch, locked)
    with pytest.raises(PermissionError) as raised:
        reset_demo(data, demo_sheet_csv(date(2027, 1, 1)))
    assert Path(raised.value.filename).name == locked
    assert _unchanged(demo)


def test_a_delete_failing_anyway_never_leaves_an_added_member_without_payments(
        used_demo, monkeypatch):
    data, demo = used_demo
    real_unlink = Path.unlink

    def unlink(self, missing_ok=False):  # passes the open check, then fails
        if self.name == "members_clean.csv":
            raise PermissionError(13, "Permission denied", str(self))
        return real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", unlink)
    with pytest.raises(PermissionError):
        reset_demo(data, demo_sheet_csv(TODAY))
    assert _unchanged(demo)  # members_clean.csv goes first, so nothing went


def test_a_sheet_that_cannot_be_replaced_names_the_sheet_and_says_the_rest_was_cleared(
        used_demo, monkeypatch):
    data, demo = used_demo

    def locked(source, destination):
        raise PermissionError(13, "Permission denied", str(source))

    monkeypatch.setattr("src.sidecar.os.replace", locked)
    with pytest.raises(DemoResetIncomplete) as raised:
        reset_demo(data, demo_sheet_csv(TODAY))
    assert Path(raised.value.filename).name == "demo_gym.csv"
    assert sorted(p.name for p in demo.parent.iterdir()) == ["demo_gym.csv"]  # no .tmp


def test_a_locked_members_clean_is_named_and_leaves_no_temporary_file(tmp_path, monkeypatch):
    target = tmp_path / "members_clean.csv"
    target.write_text("old", encoding="utf-8")

    def locked(source, destination):
        raise PermissionError(13, "Permission denied", str(source))

    monkeypatch.setattr("src.sidecar.os.replace", locked)
    with pytest.raises(PermissionError) as raised:
        write_clean_members(target, [{"member_name": "A"}])
    assert Path(raised.value.filename).name == "members_clean.csv"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["members_clean.csv"]
    assert target.read_text(encoding="utf-8") == "old"


# --- Fix round 1: what discarding would set aside ------------------------------------------

def test_rows_only_in_corrections_are_the_added_members(tmp_path):
    sheet = tmp_path / "Book1.csv"
    sheet.write_bytes(BOOK1.read_bytes())
    assert rows_only_in_corrections(sheet) == []
    rows, _ = read_rows(sheet)
    added = {**rows[0], "member_id": "M025", "member_name": "Kiran Rao", "membership_id": "MS-027"}
    write_clean_members(clean_members_path(sheet), [*rows, added])
    assert [r["member_name"] for r in rows_only_in_corrections(sheet)] == ["Kiran Rao"]


def test_corrected_rows_without_a_typed_membership_id_are_not_counted(tmp_path):
    sheet = tmp_path / "s.csv"
    sheet.write_text("Member Name,Membership Type,Date Joined,Membership Amount,Installments,"
                     "Paid Amount\nAsha,Monthly,1 Nov,2000,1,0\n", encoding="utf-8")
    write_clean_members(clean_members_path(sheet), [
        {"member_name": "Asha", "membership_type": "Monthly", "date_joined": "2026-11-01",
         "membership_amount": "2000", "instalments": "1", "paid_amount": "0"}])
    assert rows_only_in_corrections(sheet) == []
