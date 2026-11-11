"""Demo mode, the sample sheet and Add a new member, driven through Streamlit's AppTest.

The upload route uses a tmp data folder (GYM_DATA_DIR) and no GYM_SHEET; the
add-member cases use a COPY of Book1.csv in path mode. Today is pinned to
2026-11-08, the demo's anchor day, so its figures are the hand-derived ones.
"""

import os
from datetime import date
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src.assemble import build_dataset
from src.balances import all_statuses
from src.samples import SAMPLE_FILE_NAME, demo_sheet_csv, sample_sheet_csv
from src.sheet import read_rows
from src.sidecar import demo_path, write_clean_members
from src.views import tiles as tile_figures

ROOT = Path(__file__).resolve().parent.parent
FILES = ROOT / "src" / "files"
APP = str(ROOT / "app.py")
BOOK1 = (FILES / "Book1.csv").read_bytes()
DEMO_TILES = {"Total Members": "14", "Total Membership Value": "₹1,51,000",
              "Total Receivable": "₹70,500", "Overdue": "₹29,500"}
BOOK1_TILES = {"Total Members": "24", "Total Membership Value": "₹2,35,400",
               "Total Receivable": "₹97,300", "Overdue": "₹60,950"}


@pytest.fixture(autouse=True)
def pinned(monkeypatch):
    monkeypatch.setenv("GYM_TODAY", "2026-11-08")


@pytest.fixture
def data(tmp_path, monkeypatch):
    monkeypatch.delenv("GYM_SHEET", raising=False)
    monkeypatch.setattr("sys.argv", ["app.py"])
    folder = tmp_path / "data"
    monkeypatch.setenv("GYM_DATA_DIR", str(folder))
    return folder


@pytest.fixture
def sheet(tmp_path, monkeypatch):
    path = tmp_path / "gym" / "Book1.csv"
    path.parent.mkdir()
    path.write_bytes(BOOK1)
    monkeypatch.setenv("GYM_SHEET", str(path))
    return path


def ok(at):
    assert not at.exception, [e.value for e in at.exception]
    return at


def open_app():
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    return ok(at)


def click(at, key):
    at.button(key=key).click()
    at.run()
    return ok(at)


def tiles(at):
    return {m.label: m.value for m in at.metric}


def texts(elements):
    return " ".join(str(e.value) for e in elements)


def by_label(widgets, label):
    [widget] = [w for w in widgets if w.label == label]
    return widget


def open_demo():
    return click(open_app(), "open_demo")


# --- The upload screen -------------------------------------------------------------------

def test_the_upload_screen_offers_the_sample_and_the_demo(data):
    at = open_app()
    [download] = at.get("download_button")
    assert download.proto.label == "Download sample sheet (CSV)"
    [guide, preview] = at.dataframe
    assert "Required" in guide.value.columns and len(guide.value) == 9
    assert list(preview.value.columns)[:2] == ["Member ID", "Member Name"]
    assert at.button(key="open_demo").label == "Skip to dashboard with dummy data"
    assert not data.exists()  # looking writes nothing


def test_the_downloaded_sample_uploads_straight_to_a_dashboard(data):
    at = open_app()
    at.file_uploader(key="upload").set_value((SAMPLE_FILE_NAME, sample_sheet_csv(), "text/csv"))
    at.run()
    assert tiles(ok(at))["Total Members"] == "3"
    assert not at.error and not [d for d in at.dataframe if "Problem" in d.value.columns]


# --- Demo mode ---------------------------------------------------------------------------

def test_the_demo_opens_a_dashboard_with_a_banner_and_its_own_figures(data):
    at = open_demo()
    assert tiles(at) == DEMO_TILES
    assert "Demo data" in texts(at.info)
    assert at.button(key="reset_demo") and at.button(key="choose_another_sheet")
    assert demo_path(data).exists()


def test_the_demo_and_a_real_upload_show_different_figures(data):
    at = open_app()
    at.file_uploader(key="upload").set_value(("Book1.csv", BOOK1, "text/csv"))
    at.run()
    assert tiles(ok(at)) == BOOK1_TILES
    assert "Demo data" not in texts(at.info)
    click(at, "choose_another_sheet")
    assert tiles(click(at, "open_demo")) == DEMO_TILES


def test_a_payment_in_the_demo_stays_in_the_demo(data):
    at = open_app()
    at.file_uploader(key="upload").set_value(("Book1.csv", BOOK1, "text/csv"))
    at.run()
    click(ok(at), "choose_another_sheet")
    click(at, "open_demo")
    at.selectbox(key="payment_member").select("Aarav Sharma")
    at.run()
    by_label(at.text_input, "Amount (₹)").input("5000")
    at.run()
    click(at, "record_payment")
    assert tiles(at)["Total Receivable"] == "₹65,500"
    assert (demo_path(data).parent / "payments.csv").exists()
    assert not (data / "Book1_csv" / "payments.csv").exists()
    assert (data / "Book1_csv" / "Book1.csv").read_bytes() == BOOK1
    click(at, "choose_another_sheet")
    assert at.selectbox(key="earlier_upload").options == ["Book1.csv"]  # the demo is not listed


def test_reset_and_re_entering_both_start_the_demo_afresh(data):
    at = open_demo()
    at.selectbox(key="payment_member").select("Aarav Sharma")
    at.run()
    by_label(at.text_input, "Amount (₹)").input("5000")
    at.run()
    click(at, "record_payment")
    assert tiles(at)["Total Receivable"] == "₹65,500"
    assert tiles(click(at, "reset_demo")) == DEMO_TILES
    assert not (demo_path(data).parent / "payments.csv").exists()
    by_label(at.text_input, "Amount (₹)").input("5000")
    at.run()
    click(at, "record_payment")
    assert tiles(at)["Total Receivable"] == "₹65,500"
    click(at, "choose_another_sheet")
    assert tiles(click(at, "open_demo")) == DEMO_TILES
    assert not (demo_path(data).parent / "payments.csv").exists()


def test_resetting_the_demo_empties_both_forms_and_a_second_click_adds_nothing(data):
    at = open_demo()
    at.selectbox(key="payment_member").select("Aarav Sharma")
    at.run()
    by_label(at.text_input, "Amount (₹)").input("5000")
    at.run()
    click(at, "record_payment")
    click(fill_member(at), "add_member")
    assert tiles(at)["Total Members"] == "15"
    click(at, "reset_demo")
    assert tiles(at) == DEMO_TILES
    assert by_label(at.text_input, "Amount (₹)").value == ""
    assert by_label(at.text_input, "Member name").value == ""
    assert by_label(at.selectbox, "Membership type").value is None
    # The same steps again reach the same IDs (DM-016, P-0001): the forms still clear.
    by_label(at.text_input, "Amount (₹)").input("5000")
    at.run()
    click(at, "record_payment")
    assert by_label(at.text_input, "Amount (₹)").value == ""
    click(at, "record_payment")  # nothing typed now: nothing recorded
    click(fill_member(at), "add_member")
    assert by_label(at.text_input, "Member name").value == ""
    click(at, "add_member")  # an empty form: refused, nothing added
    assert tiles(at)["Total Members"] == "15"
    ledger = (demo_path(data).parent / "payments.csv").read_text(encoding="utf-8").splitlines()
    assert len(ledger) == 2


def test_a_locked_demo_file_is_explained_on_open_and_on_reset(data, monkeypatch):
    at = open_demo()

    def locked(data_dir, content):
        raise PermissionError(13, "Permission denied",
                              str(demo_path(data_dir).parent / "payments.csv"))

    monkeypatch.setattr("src.sidecar.reset_demo", locked)
    click(at, "reset_demo")
    assert "could not be reset" in texts(at.error) and "payments.csv" in texts(at.error)
    assert tiles(at) == DEMO_TILES  # still on the demo dashboard
    click(at, "choose_another_sheet")
    click(at, "open_demo")
    assert "could not be started" in texts(at.error) and "Excel" in texts(at.error)
    assert at.file_uploader and not at.metric


def test_the_demo_shows_its_banner_not_the_corrected_data_notice(data):
    at = click(fill_member(open_demo()), "add_member")
    assert "Demo data" in texts(at.info)
    assert "corrected data" not in texts(at.info)


@pytest.mark.parametrize("today", ["2026-11-18", "2027-06-01"])
def test_on_another_day_the_demo_shows_figures_computed_from_its_shifted_sheet(
        data, monkeypatch, today):
    monkeypatch.setenv("GYM_TODAY", today)
    at = open_demo()
    day = date.fromisoformat(today)
    rows, _ = read_rows(demo_path(data))
    assert tiles(at) == tile_figures(all_statuses(build_dataset(rows), day))["display"]
    assert demo_path(data).read_bytes() == demo_sheet_csv(day)
    if today == "2026-11-18":  # ten days on, every member is exactly as late as on the anchor
        assert tiles(at) == DEMO_TILES


# --- Add a new member --------------------------------------------------------------------

def fill_member(at, name="Kiran Rao", amount="12000", instalments="2", paid=None,
                kind="Yearly"):
    by_label(at.text_input, "Member name").input(name)
    by_label(at.text_input, "Membership amount (₹)").input(amount)
    by_label(at.text_input, "Installments").input(instalments)
    if paid is not None:
        by_label(at.text_input, "Paid at sign-up (₹, optional)").input(paid)
    if kind is not None:
        by_label(at.selectbox, "Membership type").select(kind)
    at.run()
    return ok(at)


def test_the_membership_type_must_be_chosen(sheet):
    at = open_app()
    assert by_label(at.selectbox, "Membership type").value is None
    click(fill_member(at, kind=None), "add_member")
    assert "membership type" in texts(at.error)
    assert not (sheet.parent / "members_clean.csv").exists()


def test_adding_a_member_updates_the_dashboard_and_the_payment_dropdown(sheet):
    at = fill_member(open_app())
    click(at, "add_member")
    assert tiles(at) == {**BOOK1_TILES, "Total Members": "25",
                         "Total Membership Value": "₹2,47,400", "Total Receivable": "₹1,09,300"}
    assert "Kiran Rao" in at.selectbox(key="payment_member").options
    assert "M025" in texts(at.success) and "MS-027" in texts(at.success)
    assert "members_clean.csv" in texts(at.info)
    assert not at.warning and not at.error  # no stale-corrections question, no ledger warning
    assert sheet.read_bytes() == BOOK1
    assert by_label(at.text_input, "Member name").value == ""  # emptied for the next one


def test_money_paid_at_sign_up_is_recorded_once_in_the_ledger(sheet):
    at = fill_member(open_app(), paid="6000")
    click(at, "add_member")
    assert tiles(at)["Total Receivable"] == "₹1,03,300"  # 97,300 + 12,000 - 6,000
    lines = (sheet.parent / "payments.csv").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2 and lines[1].startswith("P-0001,MS-027,6000.00,2026-11-08,recorded,")
    assert not at.warning
    at = open_app()  # a fresh session: everything comes back from the files
    assert tiles(at)["Total Receivable"] == "₹1,03,300" and not at.warning


def test_a_new_member_can_then_pay_through_record_a_payment(sheet):
    at = click(fill_member(open_app()), "add_member")
    at.selectbox(key="payment_member").select("Kiran Rao")
    at.run()
    by_label(at.text_input, "Amount (₹)").input("12000")
    at.run()
    click(at, "record_payment")
    assert tiles(at)["Total Receivable"] == "₹97,300"


def test_errors_show_after_pressing_add_and_nothing_is_written(sheet):
    at = fill_member(open_app(), name="", amount="abc", instalments="0")
    assert not at.error  # not before pressing
    click(at, "add_member")
    assert "name" in texts(at.error) and "abc" in texts(at.error)
    assert "Installments" in texts(at.error)
    assert not (sheet.parent / "members_clean.csv").exists()
    assert tiles(at) == BOOK1_TILES


def test_a_duplicate_name_warns_before_adding(sheet):
    at = fill_member(open_app(), name="Suhas Prakash")
    assert "already a member named Suhas Prakash" in texts(at.warning)
    click(at, "add_member")
    assert tiles(at)["Total Members"] == "25"


def test_adding_in_the_demo_saves_into_the_demo_folder(data):
    at = fill_member(open_demo(), kind="Monthly", amount="2500", instalments="1")
    click(at, "add_member")
    assert tiles(at)["Total Members"] == "15"
    assert "D015" in texts(at.success) and "DM-016" in texts(at.success)
    assert (demo_path(data).parent / "members_clean.csv").exists()
    assert demo_path(data).parent.name == "Demo"


def test_a_members_file_locked_by_excel_is_explained(sheet, monkeypatch):
    def locked(path, rows):
        raise PermissionError(13, "Permission denied", str(path))

    monkeypatch.setattr("src.sidecar.write_clean_members", locked)
    at = click(fill_member(open_app()), "add_member")
    assert "members_clean.csv" in texts(at.error) and "Excel" in texts(at.error)
    assert tiles(at) == BOOK1_TILES
    assert by_label(at.text_input, "Member name").value == "Kiran Rao"  # kept for the retry


def test_a_locked_ledger_still_adds_the_member_and_says_the_money_was_not_recorded(
        sheet, monkeypatch):
    def locked(path, payment):
        raise PermissionError(13, "Permission denied", str(path))

    monkeypatch.setattr("src.ledger.append_payment", locked)
    at = click(fill_member(open_app(), paid="6000"), "add_member")
    assert tiles(at)["Total Members"] == "25"
    assert "not recorded" in texts(at.error) and "payments.csv" in texts(at.error)


def test_a_ledger_that_cannot_take_the_payment_stops_the_add_before_anything_is_written(sheet):
    ledger = sheet.parent / "payments.csv"
    content = b"payment_id,membership_id,amount,paid_on,source,recorded_at,Notes\r\n"
    ledger.write_bytes(content)
    at = click(fill_member(open_app(), paid="6000"), "add_member")
    assert "Nothing was saved" in texts(at.error) and "Notes" in texts(at.error)
    assert not (sheet.parent / "members_clean.csv").exists()
    assert ledger.read_bytes() == content
    assert tiles(at) == BOOK1_TILES


def test_adding_a_member_while_corrections_are_in_use_asks_nothing(sheet):
    clean = sheet.parent / "members_clean.csv"
    write_clean_members(clean, read_rows(sheet)[0])  # corrections saved after the sheet
    at = click(fill_member(open_app()), "add_member")
    assert tiles(at)["Total Members"] == "25"
    assert not at.warning
    assert os.stat(clean).st_mtime_ns > os.stat(sheet).st_mtime_ns
    assert tiles(open_app())["Total Members"] == "25"


def test_discarding_names_the_added_member_and_their_payment_becomes_a_warning(sheet):
    click(fill_member(open_app(), paid="6000"), "add_member")
    later = os.stat(sheet.parent / "members_clean.csv").st_mtime_ns + 60_000_000_000
    os.utime(sheet, ns=(later, later))  # the owner saved the sheet again afterwards
    at = open_app()
    assert "changed since your corrections" in texts(at.warning)
    assert "1 membership(s)" in texts(at.warning) and "Kiran Rao" in texts(at.warning)
    assert "not in your sheet" in at.button(key="discard_corrections").label
    assert "including members added here" in texts(at.warning)
    click(at, "discard_corrections")
    assert tiles(at) == BOOK1_TILES
    assert "P-0001" in texts(at.warning) and "MS-027" in texts(at.warning)
    assert len(list(sheet.parent.glob("members_clean.csv.*.bak"))) == 1


# --- Empty sheets: a brand-new gym starts from headers only ------------------------------

HEADERS = ("Member Name,Membership Type,Date Joined,Membership Amount,Installments,"
           "Paid Amount\n")


@pytest.mark.parametrize("content", [HEADERS, HEADERS + ",,,,,\n,,,,,\n"],
                         ids=["headers-only", "blank-rows"])
def test_an_empty_sheet_opens_an_empty_dashboard_where_the_first_member_can_be_added(
        tmp_path, monkeypatch, content):
    sheet = tmp_path / "gym" / "New.csv"
    sheet.parent.mkdir()
    sheet.write_text(content, encoding="utf-8")
    monkeypatch.setenv("GYM_SHEET", str(sheet))
    at = open_app()
    assert tiles(at)["Total Members"] == "0" and tiles(at)["Total Receivable"] == "₹0"
    assert "no members yet" in texts(at.caption)
    assert not [s for s in at.selectbox if s.key == "payment_member"]
    click(fill_member(at, paid="2000"), "add_member")
    assert tiles(at)["Total Members"] == "1" and tiles(at)["Total Receivable"] == "₹10,000"
    assert "M001" in texts(at.success) and "MS-001" in texts(at.success)
    assert at.selectbox(key="payment_member").options == ["Kiran Rao"]
    assert sheet.read_text(encoding="utf-8") == content


@pytest.mark.parametrize("kind", ["csv", "xlsx"])
def test_columns_the_tool_does_not_know_are_kept_when_a_member_is_added(
        tmp_path, monkeypatch, kind):
    import openpyxl

    lines = [line.split(",") for line in BOOK1.decode("utf-8-sig").splitlines()]
    lines = [[*line, "Phone" if n == 0 else f"98450{n:05d}"] for n, line in enumerate(lines)]
    sheet = tmp_path / "gym" / f"Extras.{kind}"
    sheet.parent.mkdir()
    if kind == "csv":
        sheet.write_text("\n".join(",".join(line) for line in lines) + "\n", encoding="utf-8")
    else:
        workbook = openpyxl.Workbook()
        for line in lines:
            workbook.active.append(line)
        workbook.save(sheet)
    monkeypatch.setenv("GYM_SHEET", str(sheet))
    click(fill_member(open_app()), "add_member")
    rows, columns = read_rows(sheet.parent / "members_clean.csv")
    assert "Phone" in columns
    assert rows[0]["Phone"] == "9845000001" and rows[-1]["Phone"] == ""
    assert rows[-1]["member_name"] == "Kiran Rao"


# --- Fix round 2: leaving a sheet from any page, and which forms clear ---------------------

def upload_file(at, name, content):
    [uploader] = at.file_uploader  # its key changes once a sheet has been left
    uploader.set_value((name, content, "text/csv"))
    at.run()
    return ok(at)


def assert_on_upload_screen_and_staying(at):
    assert at.file_uploader and not at.metric and at.get("download_button")
    assert not [b for b in at.button if b.key == "choose_another_sheet"]
    at.run()  # any later rerun must not reopen the sheet just left
    assert ok(at).file_uploader and not at.metric
    assert not [b for b in at.button if b.key == "choose_another_sheet"]


FULL_NAME = BOOK1.decode("utf-8-sig").replace("Member Name", "Full Name", 1).encode()


@pytest.mark.parametrize("name, content, page", [
    ("FullName.csv", FULL_NAME, "fatal"),
    ("Errors.csv", (FILES / "Book1_errors.csv").read_bytes(), "fixable"),
], ids=["fatal-issues", "fixable-issues"])
def test_open_a_different_sheet_leaves_a_problems_page(data, name, content, page):
    at = upload_file(open_app(), name, content)
    assert [d for d in at.dataframe if "Problem" in d.value.columns]
    assert bool([b for b in at.button if b.key == "apply_fixes"]) == (page == "fixable")
    click(at, "choose_another_sheet")
    assert_on_upload_screen_and_staying(at)


def test_open_a_different_sheet_leaves_the_stale_corrections_prompt(data):
    at = upload_file(open_app(), "Book1.csv", BOOK1)
    click(fill_member(at), "add_member")
    copy = data / "Book1_csv" / "Book1.csv"
    later = os.stat(copy.parent / "members_clean.csv").st_mtime_ns + 60_000_000_000
    os.utime(copy, ns=(later, later))
    click(at, "choose_another_sheet")
    upload_file(at, "Book1.csv", BOOK1)
    assert "changed since your corrections" in texts(at.warning)
    click(at, "choose_another_sheet")
    assert_on_upload_screen_and_staying(at)


def test_recording_a_payment_leaves_a_half_typed_new_member_alone(sheet):
    at = open_app()
    by_label(at.text_input, "Member name").input("Kiran Rao")
    by_label(at.text_input, "Amount (₹)").input("1000")
    at.run()
    click(at, "record_payment")
    assert by_label(at.text_input, "Amount (₹)").value == ""
    assert by_label(at.text_input, "Member name").value == "Kiran Rao"


def test_adding_a_member_leaves_a_half_typed_payment_alone(sheet):
    at = open_app()
    by_label(at.text_input, "Amount (₹)").input("1000")
    at.run()
    click(fill_member(at), "add_member")
    assert by_label(at.text_input, "Member name").value == ""
    assert by_label(at.text_input, "Amount (₹)").value == "1000"


def test_switching_sheets_empties_both_forms(data):
    at = upload_file(open_app(), "Book1.csv", BOOK1)
    by_label(at.text_input, "Amount (₹)").input("1000")
    by_label(at.text_input, "Member name").input("Kiran Rao")
    at.run()
    click(at, "choose_another_sheet")
    click(at, "open_working_copy")
    assert by_label(at.text_input, "Amount (₹)").value == ""
    assert by_label(at.text_input, "Member name").value == ""


def test_a_demo_file_open_in_excel_stops_the_demo_starting_with_nothing_changed(
        data, monkeypatch):
    from src.sidecar import DemoResetIncomplete

    def incomplete(data_dir, content):
        raise DemoResetIncomplete(13, "Permission denied", str(demo_path(data_dir)))

    monkeypatch.setattr("src.sidecar.reset_demo", incomplete)
    at = click(open_app(), "open_demo")
    assert "demo_gym.csv" in texts(at.error) and "already cleared" in texts(at.error)
    assert ".tmp" not in texts(at.error)
