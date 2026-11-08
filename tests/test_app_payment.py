"""The record-a-payment section of app.py (ticket 12), driven through Streamlit's AppTest.

Book1.csv is copied into tmp_path and today pinned to 2026-11-08 via GYM_TODAY,
so payments.csv is created beside the copy, never beside the fixture.
"""

import shutil
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
FILES = ROOT / "src" / "files"
APP = str(ROOT / "app.py")
HEADER = "payment_id,membership_id,amount,paid_on,source,recorded_at"


@pytest.fixture
def sheet(tmp_path, monkeypatch):
    path = tmp_path / "gym" / "Book1.csv"
    path.parent.mkdir()
    shutil.copy(FILES / "Book1.csv", path)
    monkeypatch.setenv("GYM_TODAY", "2026-11-08")
    monkeypatch.setenv("GYM_SHEET", str(path))
    return path


@pytest.fixture
def ledger(sheet):
    return sheet.parent / "payments.csv"


@pytest.fixture
def at(sheet):
    app = AppTest.from_file(APP, default_timeout=30)
    app.run()
    assert not app.exception, [e.value for e in app.exception]
    return app


def tiles(at):
    return {m.label: m.value for m in at.metric}


def table_ids(at):
    [table] = [d for d in at.dataframe if "Next Due Date" in d.value.columns]
    return list(table.value["Membership ID"])


def texts(elements):
    return " ".join(e.value for e in elements)


def by_label(widgets, label):
    [widget] = [w for w in widgets if w.label == label]
    return widget


def membership_selectors(at):
    return [s for s in at.selectbox if s.label == "Membership"]


def choose_member(at, name):
    member = at.selectbox(key="payment_member")
    member.select(name)
    at.run()
    assert not at.exception, [e.value for e in at.exception]


def record(at, amount, paid_on=None):
    by_label(at.text_input, "Amount (₹)").input(amount)
    if paid_on is not None:
        by_label(at.date_input, "Paid on").set_value(paid_on)
    at.run()
    at.button(key="record_payment").click()
    at.run()
    assert not at.exception, [e.value for e in at.exception]


def lines(path):
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


# --- the form ---


def test_members_are_listed_by_name_never_by_key(at):
    options = at.selectbox(key="payment_member").options
    assert len(options) == 24
    assert options[0] == "Suhas Prakash" and "Priya Nair" in options
    assert not [o for o in options if o.startswith("M0")]


def test_amount_starts_empty_and_the_date_defaults_to_today(at):
    from datetime import date

    assert by_label(at.text_input, "Amount (₹)").value == ""
    assert by_label(at.date_input, "Paid on").value == date(2026, 11, 8)


def test_22_of_the_24_members_never_see_the_membership_selector(at):
    shown = []
    for name in at.selectbox(key="payment_member").options:
        choose_member(at, name)
        if membership_selectors(at):
            shown.append(name)
    assert shown == ["Suhas Prakash", "Manoj Verma"]


def test_suhas_is_asked_which_membership_with_ms_001_preselected(at):
    choose_member(at, "Suhas Prakash")
    [selector] = membership_selectors(at)
    assert [o.split(" ")[0] for o in selector.options] == ["MS-001", "MS-025"]
    assert selector.value.membership_id == "MS-001"


# --- the ticket's manual tests ---


def test_6000_against_suhas_lowers_the_receivable_by_exactly_that(at, ledger):
    assert tiles(at)["Total Receivable"] == "₹97,300"
    assert "MS-001" in table_ids(at)
    choose_member(at, "Suhas Prakash")
    record(at, "6000")
    assert tiles(at)["Total Receivable"] == "₹91,300"
    assert "MS-001" not in table_ids(at)
    assert "₹6,000" in texts(at.success) and "MS-001" in texts(at.success)
    [header, row] = lines(ledger)
    assert header == HEADER
    assert row.startswith("P-0001,MS-001,6000.00,2026-11-08,recorded,")


def test_6001_against_ms_001_is_refused_naming_the_ceiling_and_nothing_is_written(at, ledger):
    choose_member(at, "Suhas Prakash")
    record(at, "6001")
    assert "₹6,000" in texts(at.error)
    assert tiles(at)["Total Receivable"] == "₹97,300"
    assert not ledger.exists()


def test_priya_nair_gets_no_selector_and_any_amount_is_refused(at, ledger):
    choose_member(at, "Priya Nair")
    assert not membership_selectors(at)
    for amount in ("1", "0.01", "2000"):
        record(at, amount)
        assert "Priya Nair / MS-004 has nothing outstanding." in texts(at.error)
    assert not ledger.exists()


def test_each_payment_adds_exactly_one_row_and_leaves_prior_bytes_untouched(at, ledger):
    choose_member(at, "Suhas Prakash")
    record(at, "1000")
    first = ledger.read_bytes()
    choose_member(at, "Vandana Rao")
    record(at, "₹2,500")
    second = ledger.read_bytes()
    assert second.startswith(first)
    assert len(lines(ledger)) == 3
    assert lines(ledger)[2].startswith("P-0002,MS-002,2500.00,2026-11-08,recorded,")
    assert tiles(at)["Total Receivable"] == "₹93,800"


def test_the_amount_is_cleared_after_a_payment_so_it_cannot_be_recorded_twice(at, ledger):
    choose_member(at, "Suhas Prakash")
    record(at, "1000")
    assert by_label(at.text_input, "Amount (₹)").value == ""
    at.button(key="record_payment").click()
    at.run()
    assert len(lines(ledger)) == 2  # the second click had no amount


def test_text_that_is_not_an_amount_is_explained(at, ledger):
    choose_member(at, "Suhas Prakash")
    record(at, "six thousand")
    assert "not an amount" in texts(at.error)
    assert not ledger.exists()


# --- warnings show, then the payment goes through ---


def test_a_future_date_warns_before_submitting_and_still_records(at, ledger):
    from datetime import date

    choose_member(at, "Vandana Rao")
    by_label(at.date_input, "Paid on").set_value(date(2026, 11, 20))
    at.run()
    assert "in the future" in texts(at.warning)  # seen before pressing Record
    record(at, "1000")
    assert len(lines(ledger)) == 2
    assert ",2026-11-20,recorded," in lines(ledger)[1]
    assert "in the future" in texts(at.warning)  # repeated with the receipt


# --- file trouble is a message, never a traceback ---


def test_a_ledger_with_an_added_notes_column_is_explained_and_left_alone(at, ledger):
    content = (HEADER + ",Notes\r\n"
               "P-0001,MS-002,500,2026-11-01,recorded,2026-11-01T10:00:00,cash\r\n").encode()
    ledger.write_bytes(content)
    at.run()
    choose_member(at, "Vandana Rao")
    record(at, "1000")
    assert "Notes" in texts(at.error)
    assert ledger.read_bytes() == content


def test_a_ledger_locked_by_excel_is_explained(at, ledger, monkeypatch):
    def locked(path, payment):
        raise PermissionError(13, "Permission denied", str(path))

    monkeypatch.setattr("src.ledger.append_payment", locked)
    choose_member(at, "Suhas Prakash")
    record(at, "1000")
    assert "payments.csv" in texts(at.error) and "Excel" in texts(at.error)
    assert tiles(at)["Total Receivable"] == "₹97,300"
    assert by_label(at.text_input, "Amount (₹)").value == "1000"  # kept for the retry
