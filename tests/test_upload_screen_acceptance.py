"""Independent acceptance tests for ticket 14 (upload screen), by the tester.

The owner's route throughout: no GYM_SHEET, no CLI argument, GYM_DATA_DIR in
tmp_path, GYM_TODAY pinned. Uploads are driven through AppTest's file_uploader.
"""

import os
import shutil
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src.sidecar import payments_path, receive_upload, save_upload, working_copies

ROOT = Path(__file__).resolve().parent.parent
APP = str(ROOT / "app.py")
FILES = ROOT / "src" / "files"
BOOK1 = (FILES / "Book1.csv").read_bytes()
LEDGER_HEADER = "payment_id,membership_id,amount,paid_on,source,recorded_at\n"


@pytest.fixture
def data(tmp_path, monkeypatch):
    monkeypatch.setenv("GYM_TODAY", "2026-11-08")
    monkeypatch.delenv("GYM_SHEET", raising=False)
    monkeypatch.setattr("sys.argv", ["app.py"])
    folder = tmp_path / "data"
    monkeypatch.setenv("GYM_DATA_DIR", str(folder))
    return folder


def ok(at):
    assert not at.exception, [e.value for e in at.exception]
    return at


def open_app():
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    return ok(at)


def upload(at, name, content, mime="text/csv"):
    at.file_uploader(key="upload").set_value((name, content, mime))
    at.run()
    return ok(at)


def texts(elements):
    return " ".join(str(e.value) for e in elements)


def receivable(at):
    return {m.label: m.value for m in at.metric}.get("Total Receivable")


def files_under(folder: Path):
    return sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file())


def set_mtime(path, seconds):
    os.utime(path, ns=(seconds * 1_000_000_000, seconds * 1_000_000_000))


def record_6000_for_suhas(at):
    at.selectbox(key="payment_member").set_value("Suhas Prakash").run()
    membership = at.selectbox(key="payment_membership:M001")
    membership.set_value(next(o for o in membership.options if o.startswith("MS-001"))).run()
    at.text_input(key="payment_amount:").input("6000").run()
    at.button(key="record_payment").click().run()
    return ok(at)


# --- The whole owner session --------------------------------------------------------

def test_upload_record_switch_and_reopen_keeps_the_payment(data):
    at = upload(open_app(), "Book1.csv", BOOK1)
    assert receivable(at) == "₹97,300"
    record_6000_for_suhas(at)
    assert receivable(at) == "₹91,300"
    at.button(key="choose_another_sheet").click().run()
    assert ok(at).file_uploader and not at.metric
    at.button(key="open_working_copy").click().run()
    assert receivable(ok(at)) == "₹91,300"
    rows = payments_path(data / "Book1_csv" / "Book1.csv").read_text(encoding="utf-8").splitlines()
    assert len(rows) == 2 and rows[1].startswith("P-0001,MS-001,6000")


def test_a_later_session_re_uploading_the_same_sheet_still_shows_the_payment(data):
    record_6000_for_suhas(upload(open_app(), "Book1.csv", BOOK1))
    again = upload(open_app(), "Book1.csv", BOOK1)  # a fresh browser session
    assert receivable(again) == "₹91,300"
    assert "were kept" in texts(again.success)


def test_the_kept_notice_is_absent_on_a_first_upload(data):
    at = upload(open_app(), "Book1.csv", BOOK1)
    assert "kept" not in texts(at.success)


def test_the_kept_notice_shows_once_not_on_every_rerun(data):
    copy = save_upload(data, "Book1.csv", BOOK1)
    payments_path(copy).write_text(LEDGER_HEADER, encoding="utf-8")
    at = upload(open_app(), "Book1.csv", BOOK1)
    assert "were kept" in texts(at.success)
    at.run()
    assert "were kept" not in texts(ok(at).success)


# --- Re-upload and stale corrections ---------------------------------------------------

def test_an_identical_re_upload_with_corrections_does_not_ask_discard_or_keep(data):
    copy = save_upload(data, "Book1.csv", BOOK1)
    clean = copy.parent / "members_clean.csv"
    shutil.copy(FILES / "Book1.csv", clean)
    payments_path(copy).write_text(LEDGER_HEADER, encoding="utf-8")
    set_mtime(copy, 1_000)
    set_mtime(clean, 2_000)
    sidecars = (clean.read_bytes(), payments_path(copy).read_bytes())
    at = upload(open_app(), "Book1.csv", BOOK1)
    assert not [b for b in at.button if b.key in ("discard_corrections", "keep_corrections")]
    assert os.stat(copy).st_mtime_ns == 1_000 * 1_000_000_000
    assert (clean.read_bytes(), payments_path(copy).read_bytes()) == sidecars
    assert at.metric


def test_a_changed_re_upload_keeps_both_sidecars_byte_for_byte(data):
    copy = save_upload(data, "Book1.csv", BOOK1)
    clean = copy.parent / "members_clean.csv"
    shutil.copy(FILES / "Book1.csv", clean)
    payments_path(copy).write_text(LEDGER_HEADER, encoding="utf-8")
    sidecars = (clean.read_bytes(), payments_path(copy).read_bytes())
    at = upload(open_app(), "Book1.csv", BOOK1 + b"\n")
    assert copy.read_bytes() == BOOK1 + b"\n"
    assert (clean.read_bytes(), payments_path(copy).read_bytes()) == sidecars
    assert "replaces the copy" in texts(at.success) and "were kept" in texts(at.success)


# --- The picker -------------------------------------------------------------------------

def test_recording_a_payment_moves_that_sheet_to_the_top_of_the_picker(data):
    older = save_upload(data, "Book1.csv", BOOK1)
    newer = save_upload(data, "Other.csv", BOOK1)
    set_mtime(older, 1_000)
    set_mtime(newer, 2_000)
    assert [p.name for p in working_copies(data)] == ["Other.csv", "Book1.csv"]
    at = open_app()
    at.selectbox(key="earlier_upload").set_value(older).run()
    at.button(key="open_working_copy").click().run()
    record_6000_for_suhas(ok(at))
    at.button(key="choose_another_sheet").click().run()
    assert ok(at).selectbox(key="earlier_upload").options == ["Book1.csv", "Other.csv"]


def test_unicode_and_uppercase_names_are_listed_by_their_original_name(data):
    upload(open_app(), "Ünïcødé सदस्य.csv", BOOK1)
    upload(open_app(), "Members.CSV", BOOK1)
    assert set(open_app().selectbox(key="earlier_upload").options) == {
        "Ünïcødé सदस्य.csv", "Members.CSV"}


# --- The developer route ------------------------------------------------------------------

def test_gym_sheet_skips_the_upload_screen_even_with_earlier_uploads(data, tmp_path, monkeypatch):
    save_upload(data, "Old.csv", BOOK1)
    sheet = tmp_path / "Book1.csv"
    shutil.copy(FILES / "Book1.csv", sheet)
    monkeypatch.setenv("GYM_SHEET", str(sheet))
    at = open_app()
    assert not at.file_uploader
    assert not [s for s in at.selectbox if s.key == "earlier_upload"]
    assert receivable(at) == "₹97,300"


# --- Unsafe and unusable uploads -------------------------------------------------------

@pytest.mark.parametrize("name", ["..\\x.csv", "../x.csv", "/etc/x.csv", "C:\\x.csv",
                                  "..\\..\\..\\x.csv"])
def test_a_path_in_the_name_is_reduced_to_its_base_name_inside_the_data_folder(
        data, tmp_path, name):
    at = upload(open_app(), name, BOOK1)
    assert receivable(at) == "₹97,300"
    assert files_under(tmp_path) == ["data/x_csv/x.csv"]


@pytest.mark.parametrize("name, says", [
    ("C:x.csv", "character"),
    ("CON.csv", "reserved"),
    ("nul.xlsx", "reserved"),
    ("Payments.CSV", "sidecar"),
    ("members_clean.csv", "sidecar"),
    ("members.xls", "CSV (.csv) or Excel (.xlsx)"),
    ("members.csv.", "dot or a space"),
    ("..", "no usable name"),
    ("a" * 250 + ".csv", "too long"),  # rework item 3: said "Could not use" (an OSError)
], ids=["drive-relative", "CON", "nul", "payments", "members_clean", "xls", "trailing-dot",
        "dotdot", "very-long"])
def test_an_unusable_name_is_a_sentence_and_writes_nothing(data, tmp_path, name, says):
    at = upload(open_app(), name, BOOK1)
    assert says in texts(at.error)
    assert at.file_uploader and not at.metric
    assert files_under(tmp_path) == []


def test_a_zero_byte_upload_is_refused_and_writes_nothing(data, tmp_path):
    at = upload(open_app(), "Book1.csv", b"")
    assert "empty" in texts(at.error)
    assert files_under(tmp_path) == []


def test_an_empty_re_upload_leaves_the_existing_copy_alone(data):
    copy = save_upload(data, "Book1.csv", BOOK1)
    with pytest.raises(ValueError, match="empty"):
        receive_upload(data, "Book1.csv", b"")
    assert copy.read_bytes() == BOOK1


def test_a_corrupt_xlsx_is_a_sentence_not_a_traceback(data):
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    at.file_uploader(key="upload").set_value(("members.xlsx", b"not a zip", "application/zip"))
    at.run()
    assert not at.exception
    assert texts(at.error)


def test_an_unreadable_upload_is_not_offered_for_reopening(data):
    upload(open_app(), "binary.csv", bytes(range(256)) * 10)
    assert working_copies(data) == []
