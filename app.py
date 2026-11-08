"""Gym payment visibility: the Streamlit shell (ADR 0001).

This file only loads files, calls `src/`, renders what comes back and
collects the owner's answers. It holds no arithmetic, no date comparison and
no business rule; when one seems needed, it belongs in `src/`.

Run:  streamlit run app.py
      Opens on the upload screen, the owner's way in. The uploaded sheet is
      kept as a working copy under the data folder (data/<stem>_<ext>/<name>),
      with payments.csv and members_clean.csv beside it; earlier uploads are
      offered for reopening, most recently used first.
Dev:  streamlit run app.py -- path/to/sheet.csv
      Opens that sheet directly, skipping the upload screen (developers, tests).
Env:  GYM_SHEET     sheet path, as the CLI argument does (developers, tests)
      GYM_DATA_DIR  folder for upload working copies, instead of ./data (tests)
      GYM_TODAY     pin today's date, e.g. 2026-11-08 (tests, demos)
"""

import os
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from src import recording, views
from src.assemble import build_dataset, with_ledger
from src.balances import all_statuses
from src.ledger import append_payment, read_payments
from src.money import format_money
from src.sidecar import (
    check_sheet,
    clean_members_path,
    corrections_stale,
    discard_corrections,
    keep_corrections,
    payments_path,
    receive_upload,
    resolve_input,
    working_copies,
    write_clean_members,
)
from src.validation import apply_fixes, fix_for, preview_fix, validate

DATA_DIR = Path(__file__).resolve().parent.joinpath("data")  # upload working copies (git-ignored)
OPEN_SHEET = "open_sheet"  # session key: the working copy the owner uploaded or reopened
UPLOAD_NOTICE = "upload_notice"  # session key: shown once after opening it
MANUAL = "enter_manually"
# Presentation only: whether a row is Overdue is decided in src (row["is_overdue"]).
DUE_STYLE = "background-color: #d93025; color: white; font-weight: bold"

# How each fix option reads on screen. Which options an issue offers is
# decided in src/validation.py; this is wording only.
OPTION_LABELS = {
    "infer_current_year": "Use this year",
    "enter_manually": "Type the correct value",
    "use_date_joined": "Use the Date Joined",
    "same_person": "Same person (a renewal)",
    "different_people": "Different people who share a name",
}


def configured_today(now: datetime) -> date:
    """Today for the whole run: GYM_TODAY pins it (shell configuration), else `now`'s date."""
    pinned = os.environ.get("GYM_TODAY")
    return date.fromisoformat(pinned) if pinned else now.date()


def locked_message(exc: PermissionError) -> str:
    return (f"{Path(exc.filename or 'A file').name} is open in another program, probably "
            "Excel. Close it there, then press R to retry.")


def data_dir() -> Path:
    return Path(os.environ.get("GYM_DATA_DIR") or DATA_DIR)


def developer_sheet() -> str:
    """GYM_SHEET, else the first CLI argument after `--`; empty for the owner's route."""
    given = os.environ.get("GYM_SHEET") or next(iter(sys.argv[1:]), "")
    return given.strip().strip('"')


def choose_sheet() -> Path:
    """The developer's path if one was given, else the sheet the owner opened, else upload."""
    given = developer_sheet()
    if given:
        return check_sheet(given)
    if OPEN_SHEET in st.session_state:
        return opened_sheet(st.session_state[OPEN_SHEET])
    upload_screen()


def upload_screen():
    st.subheader("Upload your members sheet")
    st.write("Choose the members sheet your gym keeps, saved as CSV or Excel (.csv or .xlsx).")
    # No `type=` filter: Streamlit would refuse other files with a traceback the
    # app cannot catch; receive_upload refuses them with a sentence instead.
    upload = st.file_uploader("Members sheet", key="upload")
    st.caption("Your original file is never changed. The tool works on a copy it keeps "
               "in its data folder, with your payments and corrections beside it.")
    if upload is not None:
        try:
            saved = receive_upload(data_dir(), upload.name, upload.getvalue())
        except ValueError as exc:
            st.error(str(exc))
        else:
            open_sheet(saved.path, upload_notice(saved))
    earlier_uploads()
    st.stop()


def upload_notice(saved) -> str | None:
    if not saved.kept_payments:
        return None
    if saved.changed:
        return (f"{saved.path.name} replaces the copy uploaded before. The payments already "
                "recorded for it were kept.")
    return (f"{saved.path.name} is the same as the copy uploaded before. The payments already "
            "recorded for it were kept.")


def earlier_uploads() -> None:
    copies = working_copies(data_dir())
    if not copies:
        return
    st.subheader("Or reopen an earlier upload")
    chosen = st.selectbox("Earlier uploads, most recently used first", copies,
                          format_func=lambda p: p.name, key="earlier_upload")
    if st.button("Open", key="open_working_copy"):
        open_sheet(chosen, None)


def open_sheet(path: Path, notice: str | None) -> None:
    st.session_state[OPEN_SHEET] = path
    st.session_state[UPLOAD_NOTICE] = notice
    st.rerun()


def opened_sheet(path: Path) -> Path:
    notice = st.session_state.pop(UPLOAD_NOTICE, None)
    if notice:
        st.success(notice)
    st.caption(f"Working copy: {path}. Corrections and payments are saved beside it; "
               "your original file is never changed.")
    if st.button("Open a different sheet", key="choose_another_sheet"):
        del st.session_state[OPEN_SHEET]
        st.rerun()
    return path


def ask_about_stale_corrections(sheet: Path, now: datetime) -> None:
    st.warning(
        f"{sheet.name} has changed since your corrections were saved in members_clean.csv. "
        "Using the corrections would hide anything new in the sheet.")
    keep, discard = st.columns(2)
    if discard.button("Discard my corrections and use the sheet", key="discard_corrections"):
        backup = discard_corrections(sheet, now)
        st.toast(f"Corrections moved aside to {backup}.")
        st.rerun()
    if keep.button("Keep my corrections", key="keep_corrections"):
        keep_corrections(sheet)
        st.rerun()
    st.stop()


def answer_widgets(issue, rows, today):
    """The controls for one Issue, built only from its fix_options. Returns the Fix or None."""
    key = f"{issue.code}:{issue.row_number}:{issue.column}"
    st.markdown(f"**{issue.message}**")
    if not issue.fix_options:
        st.caption("This can only be corrected in the sheet itself.")
        return None
    choices = [o for o in issue.fix_options if o != MANUAL]
    option = (st.radio("Answer", issue.fix_options, index=None, key=f"{key}:option",
                       format_func=lambda o: OPTION_LABELS.get(o, o), horizontal=True)
              if choices else MANUAL)
    typed = (st.text_input("Correct value", key=f"{key}:value")
             if MANUAL in issue.fix_options else None)
    preview = preview_fix(rows, issue, option, today=today)
    if preview:
        (st.warning if preview.warning else st.caption)(preview.message)
    return fix_for(issue, option, typed)


def show_issues(report, rows, sheet: Path, today: date) -> None:
    st.error(f"The sheet has {len(report.issues)} problem(s). Nothing is totalled until "
             "they are fixed, because a dashboard on half-valid rows shows wrong figures.")
    st.dataframe([r["display"] for r in views.issue_rows(report.issues, rows)], hide_index=True)
    if report.is_fatal:
        st.error("These can only be fixed in the sheet itself: add or rename the column(s) "
                 "named above, save the sheet and reload.")
        st.stop()
    st.subheader("Fix them here")
    fixes = [answer_widgets(issue, rows, today) for issue in report.issues]
    chosen = [f for f in fixes if f is not None]
    if st.button("Apply fixes", key="apply_fixes", type="primary", disabled=not chosen):
        corrected = apply_fixes(rows, chosen, current_year=today.year)
        write_clean_members(clean_members_path(sheet), corrected)
        st.rerun()
    st.stop()


def show_dashboard(merge, today: date) -> None:
    for warning in views.ledger_warnings(merge):
        st.warning(warning)
    statuses = all_statuses(merge.dataset, today)
    figures = views.tiles(statuses)["display"]
    for column, (label, value) in zip(st.columns(len(figures)), figures.items()):
        column.metric(label, value)
    show_paid = st.toggle("Show fully paid", value=False, key="show_fully_paid")
    rows = views.receivables_rows(statuses, show_fully_paid=show_paid)
    st.dataframe(receivables_table(rows), hide_index=True, width="stretch")


def receivables_table(rows):
    """The rows exactly as views ordered and formatted them, with the DUE tag styled red."""
    table = pd.DataFrame([r["display"] for r in rows], columns=views.ROW_COLUMNS)
    overdue = [r["is_overdue"] for r in rows]
    return table.style.apply(lambda _: [DUE_STYLE if o else "" for o in overdue],
                             subset=["Status"], axis=0)


def payment_form(dataset, sheet: Path, today: date, now: datetime) -> None:
    """Member -> (Membership, only when recording says to ask) -> amount -> date -> record.

    Warnings (a future date, a date before joining) show under the date as soon
    as it is picked, so the owner sees them before pressing Record, and they do
    not stop the payment. Errors show under the amount after Record is pressed,
    and nothing is written. Every rule comes from src/recording.py.
    """
    st.subheader("Record a payment")
    receipt = st.session_state.pop("payment_receipt", None)
    if receipt:
        st.success(receipt["message"])
        for warning in receipt["warnings"]:
            st.warning(warning)
    members = recording.member_options(dataset)
    member_label = st.selectbox("Member", list(members), key="payment_member")
    member_id = members[member_label]
    membership = choose_membership(dataset, member_id, today)
    # A fresh key after each recorded payment empties the amount, so a second
    # click cannot record the same money twice.
    form = st.session_state.get("payment_form", "")
    amount_text = st.text_input("Amount (₹)", key=f"payment_amount:{form}", placeholder="6000")
    beside_amount = st.container()
    paid_on = st.date_input("Paid on", value=today, key=f"payment_date:{form}",
                            format="YYYY-MM-DD")
    beside_date = st.container()
    check = recording.check_payment(dataset, membership, amount_text, paid_on, today)
    for warning in check.warnings:
        beside_date.warning(warning.message)
    if not st.button("Record payment", type="primary", key="record_payment"):
        return
    for error in check.errors:
        {"amount": beside_amount, "paid_on": beside_date}[error.column].error(error.message)
    if check.accepted:
        record_payment(sheet, membership, check, paid_on, now, member_label, beside_amount)


def choose_membership(dataset, member_id: str, today: date):
    default = recording.default_membership(dataset, member_id, today)
    labels = recording.membership_options(dataset, member_id)
    if not recording.attribution_required(dataset, member_id):
        st.caption(f"For {labels[default.membership_id]}")
        return default
    options = recording.memberships_of(dataset, member_id)
    return st.selectbox("Membership", options, index=options.index(default),
                        format_func=lambda m: labels[m.membership_id],
                        key=f"payment_membership:{member_id}")


def record_payment(sheet: Path, membership, check, paid_on: date, now: datetime,
                   member_label: str, beside_amount) -> None:
    ledger_path = payments_path(sheet)
    try:
        payment = recording.build_payment(membership, check.amount, paid_on,
                                          ledger=read_payments(ledger_path), recorded_at=now)
        append_payment(ledger_path, payment)
    except PermissionError as exc:
        beside_amount.error(f"Nothing was recorded. {locked_message(exc)}")
        return
    except ValueError as exc:
        beside_amount.error(f"Nothing was recorded. {exc}")
        return
    st.session_state["payment_receipt"] = {
        "message": (f"Recorded {format_money(payment.amount)} for {member_label} / "
                    f"{payment.membership_id} on {payment.paid_on.isoformat()} "
                    f"({payment.payment_id})."),
        "warnings": [w.message for w in check.warnings],
    }
    st.session_state["payment_form"] = payment.payment_id
    st.rerun()


def main() -> None:
    st.set_page_config(page_title="Gym payments", layout="wide")
    st.title("Gym payments")
    now = datetime.now()  # the one clock read: today, the .bak stamp and recorded_at
    today = configured_today(now)
    sheet = choose_sheet()
    if corrections_stale(sheet):
        ask_about_stale_corrections(sheet, now)
    resolved = resolve_input(sheet)
    if resolved.used_clean_sidecar:
        st.info(f"Showing corrected data from {clean_members_path(sheet)}, "
                f"not {sheet.name} itself (which is never changed).")
    report = validate(resolved.rows, resolved.columns)
    if not report.is_clean:
        show_issues(report, resolved.rows, sheet, today)
    merge = with_ledger(build_dataset(resolved.rows), read_payments(payments_path(sheet)))
    show_dashboard(merge, today)
    payment_form(merge.dataset, sheet, today, now)


try:
    main()
except PermissionError as exc:
    st.error(locked_message(exc))
except FileNotFoundError as exc:
    st.error(f"There is no file at {exc.filename}. Check the path and try again.")
except OSError as exc:
    st.error(f"Could not use {exc.filename or 'a file'}: {exc.strerror or exc}. "
             "Check the path and that no other program is using it.")
except UnicodeDecodeError:
    st.error("The sheet is not a UTF-8 CSV. In Excel, save it as 'CSV UTF-8' or as .xlsx.")
except (ValueError, ImportError) as exc:
    st.error(str(exc))
