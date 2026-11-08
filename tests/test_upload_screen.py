"""Ticket 14: the upload screen as the owner's way in.

Helpers in src/sidecar.py are tested directly; the screen itself through
Streamlit's AppTest, which in 1.67 can drive st.file_uploader. Every case
uses a tmp data folder (GYM_DATA_DIR) and no GYM_SHEET / CLI argument.
"""

import os
import shutil
from pathlib import Path

import pytest

from src.sidecar import payments_path, receive_upload, save_upload, working_copies

ROOT = Path(__file__).resolve().parent.parent
FILES = ROOT / "src" / "files"


def set_mtime(path, seconds):
    os.utime(path, ns=(seconds * 1_000_000_000, seconds * 1_000_000_000))


# --- working_copies -------------------------------------------------------------

def test_no_data_folder_means_no_working_copies(tmp_path):
    assert working_copies(tmp_path / "data") == []


def test_working_copies_are_listed_most_recently_used_first(tmp_path):
    data = tmp_path / "data"
    old = save_upload(data, "Old.csv", b"a\n")
    new = save_upload(data, "New.xlsx", b"b")
    middle = save_upload(data, "Middle.csv", b"c\n")
    set_mtime(old, 1_000)
    set_mtime(middle, 2_000)
    set_mtime(new, 3_000)
    assert working_copies(data) == [new, middle, old]


def test_a_payment_recorded_later_counts_as_use(tmp_path):
    data = tmp_path / "data"
    first = save_upload(data, "First.csv", b"a\n")
    second = save_upload(data, "Second.csv", b"b\n")
    set_mtime(first, 1_000)
    set_mtime(second, 2_000)
    ledger = payments_path(first)
    ledger.write_text("payment_id\n", encoding="utf-8")
    set_mtime(ledger, 3_000)  # a payment recorded against First after Second was uploaded
    assert working_copies(data) == [first, second]


def test_stray_files_and_folders_are_not_working_copies(tmp_path):
    data = tmp_path / "data"
    real = save_upload(data, "Book1.csv", b"a\n")
    (data / "loose.csv").write_text("x", encoding="utf-8")  # not in a sheet folder
    (data / "empty_csv").mkdir()  # a folder without its sheet
    (data / "notes_txt").mkdir()
    (data / "notes_txt" / "notes.txt").write_text("x", encoding="utf-8")
    (real.parent / "members_clean.csv").write_text("x", encoding="utf-8")
    assert working_copies(data) == [real]


# --- receive_upload: saving what the owner uploaded ---------------------------------

@pytest.mark.parametrize("name", ["members.txt", "members.xls", "members.pdf", "members"])
def test_a_file_that_is_not_csv_or_xlsx_is_refused_naming_what_is_accepted(tmp_path, name):
    with pytest.raises(ValueError, match=r"CSV \(\.csv\) or Excel \(\.xlsx\)"):
        receive_upload(tmp_path / "data", name, b"a,b\n")
    assert not (tmp_path / "data").exists()


def test_the_type_check_ignores_case(tmp_path):
    assert receive_upload(tmp_path / "data", "Members.CSV", b"a\n").path.name == "Members.CSV"


def test_an_empty_file_is_refused(tmp_path):
    with pytest.raises(ValueError, match="empty"):
        receive_upload(tmp_path / "data", "Book1.csv", b"")
    assert not (tmp_path / "data").exists()


def test_a_first_upload_is_new_and_has_no_payments_to_keep(tmp_path):
    data = (FILES / "Book1.csv").read_bytes()
    saved = receive_upload(tmp_path / "data", "Book1.csv", data)
    assert saved.path == (tmp_path / "data" / "Book1_csv" / "Book1.csv").resolve()
    assert saved.path.read_bytes() == data
    assert saved.changed is True and saved.kept_payments is False


def test_an_identical_re_upload_keeps_payments_and_leaves_the_copy_alone(tmp_path):
    data = (FILES / "Book1.csv").read_bytes()
    first = receive_upload(tmp_path / "data", "Book1.csv", data).path
    ledger = payments_path(first)
    ledger.write_bytes(b"payment_id,membership_id,amount,paid_on,source,recorded_at\n")
    set_mtime(first, 1_000)
    before = (first.read_bytes(), os.stat(first).st_mtime_ns, ledger.read_bytes())
    again = receive_upload(tmp_path / "data", "Book1.csv", data)
    assert again.path == first
    assert again.changed is False and again.kept_payments is True
    assert (first.read_bytes(), os.stat(first).st_mtime_ns, ledger.read_bytes()) == before


def test_a_changed_re_upload_replaces_the_copy_but_keeps_payments_and_corrections(tmp_path):
    first = receive_upload(tmp_path / "data", "Book1.csv", b"old\n").path
    ledger = payments_path(first)
    ledger.write_bytes(b"ledger")
    clean = first.parent / "members_clean.csv"
    clean.write_bytes(b"clean")
    again = receive_upload(tmp_path / "data", "Book1.csv", b"new\n")
    assert again.path == first and first.read_bytes() == b"new\n"
    assert again.changed is True and again.kept_payments is True
    assert ledger.read_bytes() == b"ledger" and clean.read_bytes() == b"clean"


# --- The screen, through AppTest --------------------------------------------------------

from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(ROOT / "app.py")
BOOK1 = (FILES / "Book1.csv").read_bytes()
BOOK1_RECEIVABLE = "₹97,300"


@pytest.fixture
def data(tmp_path, monkeypatch):
    """The owner's route: no GYM_SHEET, no CLI argument, data/ in a tmp folder."""
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


def everything(at):
    return texts([*at.error, *at.warning, *at.info, *at.success, *at.caption, *at.markdown])


def receivable(at):
    return {m.label: m.value for m in at.metric}.get("Total Receivable")


def test_the_owner_sees_an_upload_screen_with_no_path_box(data):
    at = open_app()
    assert len(at.file_uploader) == 1
    assert not at.radio and not at.text_input
    assert "CSV or Excel" in everything(at)
    assert "never changed" in everything(at)
    assert not at.metric
    assert not at.selectbox  # nothing uploaded before: no picker


def test_uploading_book1_opens_its_dashboard_from_a_working_copy(data):
    at = upload(open_app(), "Book1.csv", BOOK1)
    assert receivable(at) == BOOK1_RECEIVABLE
    copy = data / "Book1_csv" / "Book1.csv"
    assert copy.read_bytes() == BOOK1
    assert not at.file_uploader  # the dashboard replaces the upload screen


@pytest.mark.parametrize("name, content, says", [
    ("members.txt", b"a,b\n", "CSV (.csv) or Excel (.xlsx)"),
    ("Book1.csv", b"", "empty"),
    ("payments.csv", BOOK1, "rename"),
    ("CON.csv", BOOK1, "reserved"),
], ids=["wrong-type", "empty", "sidecar-name", "reserved-name"])
def test_a_rejected_upload_is_a_message_on_the_upload_screen(data, name, content, says):
    at = upload(open_app(), name, content)
    assert says in texts(at.error)
    assert at.file_uploader and not at.metric
    assert not data.exists() or not any(data.rglob("*.*"))


def test_earlier_uploads_are_offered_most_recently_used_first(data):
    old = save_upload(data, "Old.csv", BOOK1)
    new = save_upload(data, "Book1.csv", BOOK1)
    set_mtime(old, 1_000)
    set_mtime(new, 2_000)
    at = open_app()
    [picker] = at.selectbox
    assert picker.options == ["Book1.csv", "Old.csv"]
    assert picker.value == new  # the most recent is preselected


def test_reopening_an_earlier_upload_shows_its_dashboard_with_its_payments(data):
    copy = save_upload(data, "Book1.csv", BOOK1)
    payments_path(copy).write_text(
        "payment_id,membership_id,amount,paid_on,source,recorded_at\n"
        "P-0001,MS-001,6000,2026-11-08,recorded,2026-11-08T10:00:00\n", encoding="utf-8")
    at = open_app()
    at.button(key="open_working_copy").click()
    at.run()
    assert receivable(ok(at)) == "₹91,300"


def test_re_uploading_the_same_file_keeps_its_payments_and_asks_nothing(data):
    copy = save_upload(data, "Book1.csv", BOOK1)
    payments_path(copy).write_text(
        "payment_id,membership_id,amount,paid_on,source,recorded_at\n"
        "P-0001,MS-001,6000,2026-11-08,recorded,2026-11-08T10:00:00\n", encoding="utf-8")
    set_mtime(copy, 1_000)
    at = upload(open_app(), "Book1.csv", BOOK1)
    assert receivable(at) == "₹91,300"
    assert "payments" in texts(at.success) and "kept" in texts(at.success)
    assert os.stat(copy).st_mtime_ns == 1_000 * 1_000_000_000  # unchanged bytes, not rewritten
    assert "changed since your corrections" not in texts(at.warning)


def test_a_changed_re_upload_with_corrections_asks_discard_or_keep(data):
    copy = save_upload(data, "Book1.csv", BOOK1)
    shutil.copy(FILES / "Book1.csv", copy.parent / "members_clean.csv")
    set_mtime(copy, 1_000)
    set_mtime(copy.parent / "members_clean.csv", 2_000)
    at = upload(open_app(), "Book1.csv", (FILES / "Book1_errors.csv").read_bytes())
    assert "changed since your corrections" in texts(at.warning)
    assert at.button(key="discard_corrections") and at.button(key="keep_corrections")


def test_the_owner_can_go_back_to_upload_another_sheet(data):
    at = upload(open_app(), "Book1.csv", BOOK1)
    at.button(key="choose_another_sheet").click()
    at.run()
    assert ok(at).file_uploader and not at.metric
    assert at.selectbox[0].options == ["Book1.csv"]  # and the first one is offered back


# --- Rework: unreadable uploads, long names, the one-time notice -----------------------

NOT_UTF8 = bytes(range(256)) * 10


@pytest.mark.parametrize("name, content, says", [
    ("binary.csv", NOT_UTF8, "UTF-8"),
    ("members.xlsx", b"not a zip", "not a readable Excel file"),
], ids=["non-utf8-csv", "corrupt-xlsx"])
def test_an_unreadable_first_upload_is_refused_and_nothing_is_kept(tmp_path, name, content, says):
    data = tmp_path / "data"
    with pytest.raises(ValueError, match=says):
        receive_upload(data, name, content)
    assert not data.exists() or not any(data.iterdir())
    assert working_copies(data) == []


def test_an_unreadable_re_upload_leaves_the_good_copy_and_its_sidecars_alone(tmp_path):
    data = tmp_path / "data"
    good = receive_upload(data, "Book1.csv", BOOK1).path
    payments_path(good).write_bytes(b"ledger")
    (good.parent / "members_clean.csv").write_bytes(b"clean")
    before = {p.name: (p.read_bytes(), os.stat(p).st_mtime_ns) for p in good.parent.iterdir()}
    with pytest.raises(ValueError, match="UTF-8"):
        receive_upload(data, "Book1.csv", NOT_UTF8)
    after = {p.name: (p.read_bytes(), os.stat(p).st_mtime_ns) for p in good.parent.iterdir()}
    assert after == before
    assert working_copies(data) == [good]


def test_a_corrupt_xlsx_named_by_path_is_a_sentence(tmp_path):
    from src.sheet import read_rows
    sheet = tmp_path / "members.xlsx"
    sheet.write_bytes(b"not a zip")
    with pytest.raises(ValueError, match="members.xlsx is not a readable Excel file"):
        read_rows(sheet)


def test_a_very_long_name_is_refused_before_any_folder_is_made(tmp_path):
    data = tmp_path / "data"
    with pytest.raises(ValueError, match="too long"):
        receive_upload(data, "a" * 250 + ".csv", b"x\n")
    assert not data.exists()


def test_a_name_at_the_length_limit_still_uploads(tmp_path):
    name = "a" * 76 + ".csv"  # 80 characters
    assert receive_upload(tmp_path / "data", name, b"x\n").path.name == name


def test_the_payments_kept_notice_is_shown_once_not_on_every_rerun(data):
    copy = save_upload(data, "Book1.csv", BOOK1)
    payments_path(copy).write_text(
        "payment_id,membership_id,amount,paid_on,source,recorded_at\n"
        "P-0001,MS-001,6000,2026-11-08,recorded,2026-11-08T10:00:00\n", encoding="utf-8")
    at = upload(open_app(), "Book1.csv", BOOK1)
    assert "kept" in texts(at.success)
    at.toggle(key="show_fully_paid").set_value(True)
    at.run()  # any later interaction reruns the script
    assert "kept" not in texts(ok(at).success)
    assert at.metric  # still on the dashboard


# --- Second rework: every way a sheet can be unreadable is a sentence ------------------

import io  # noqa: E402
import zipfile  # noqa: E402

UNREADABLE_XLSX = "not a readable Excel file"


def zipped(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def book1_xlsx():
    import openpyxl
    workbook = openpyxl.Workbook()
    for line in BOOK1.decode("utf-8-sig").splitlines():
        workbook.active.append(line.split(","))
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def with_truncated_sheet_xml(xlsx):
    source = zipfile.ZipFile(io.BytesIO(xlsx))
    return zipped({n: (source.read(n)[: len(source.read(n)) // 2]
                       if n == "xl/worksheets/sheet1.xml" else source.read(n))
                   for n in source.namelist()})


DOCX_LIKE = zipped({
    "[Content_Types].xml": (
        '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/'
        'content-types"><Override PartName="/word/document.xml" ContentType="application/'
        'vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>'),
    "word/document.xml": "<w/>",
})
UNREADABLE = {
    "truncated-sheet-xml": with_truncated_sheet_xml(book1_xlsx()),
    "docx-renamed": DOCX_LIKE,
    "zip-of-hello-txt": zipped({"hello.txt": "hello"}),
}


def test_a_real_xlsx_still_uploads(tmp_path):
    assert receive_upload(tmp_path / "data", "Book1.xlsx", book1_xlsx()).changed


@pytest.mark.parametrize("content", UNREADABLE.values(), ids=UNREADABLE.keys())
def test_a_broken_workbook_is_one_sentence_and_nothing_is_kept(tmp_path, content):
    data = tmp_path / "data"
    with pytest.raises(ValueError, match=f"members.xlsx is {UNREADABLE_XLSX}"):
        receive_upload(data, "members.xlsx", content)
    assert not data.exists()


@pytest.mark.parametrize("content", UNREADABLE.values(), ids=UNREADABLE.keys())
def test_a_broken_workbook_upload_shows_a_sentence_on_screen(data, content):
    at = upload(open_app(), "members.xlsx", content)
    assert UNREADABLE_XLSX in texts(at.error)
    assert at.file_uploader and not at.metric


def test_a_broken_workbook_by_path_is_the_same_sentence(tmp_path, monkeypatch):
    from src.sheet import read_rows
    sheet = tmp_path / "badxml.xlsx"
    sheet.write_bytes(UNREADABLE["truncated-sheet-xml"])
    with pytest.raises(ValueError, match=UNREADABLE_XLSX):
        read_rows(sheet)


def test_a_csv_cell_too_long_to_read_is_a_sentence(data):
    huge = BOOK1 + b"M099,Huge,MS-099,Yearly,2026-01-01,1000,1,0," + b"x" * 140_000 + b"\n"
    with pytest.raises(ValueError, match="cannot be read as CSV"):
        receive_upload(data, "huge.csv", huge)
    at = upload(open_app(), "huge.csv", huge)
    assert "cannot be read as CSV" in texts(at.error)
    assert working_copies(data) == []


def test_a_locked_xlsx_on_the_developer_route_still_says_it_is_open_elsewhere(tmp_path,
                                                                             monkeypatch):
    # Only openpyxl's parsing errors become "not readable": a real file lock keeps its message.
    sheet = tmp_path / "gym" / "Book1.xlsx"
    sheet.parent.mkdir()
    sheet.write_bytes(book1_xlsx())

    def locked(self):
        raise PermissionError(13, "Permission denied", str(self))

    monkeypatch.setenv("GYM_TODAY", "2026-11-08")
    monkeypatch.setenv("GYM_SHEET", str(sheet))
    monkeypatch.setattr(Path, "read_bytes", locked)
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    assert "open in another program" in texts(ok(at).error)
    assert UNREADABLE_XLSX not in texts(at.error)
