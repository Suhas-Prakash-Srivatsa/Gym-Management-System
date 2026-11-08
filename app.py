"""Gym payment visibility: the Streamlit shell (ADR 0001).

This file only loads files, calls `src/`, renders what comes back and
collects the owner's answers. It holds no arithmetic, no date comparison and
no business rule; when one seems needed, it belongs in `src/`.

Run:  streamlit run app.py -- path/to/sheet.csv
Env:  GYM_SHEET  default sheet path (instead of the CLI argument)
      GYM_TODAY  pin today's date, e.g. 2026-11-08 (tests, demos)
"""

import os
import sys
from datetime import date
from pathlib import Path

import streamlit as st

from src import views
from src.assemble import build_dataset, with_ledger
from src.balances import all_statuses
from src.ledger import read_payments
from src.sidecar import (
    clean_members_path,
    corrections_stale,
    discard_corrections,
    keep_corrections,
    payments_path,
    resolve_input,
    save_upload,
    write_clean_members,
)
from src.validation import apply_fixes, fix_for, preview_fix, validate

DATA_DIR = Path(__file__).resolve().parent.joinpath("data")  # upload working copies (git-ignored)
PATH_MODE = "A file on this computer"
UPLOAD_MODE = "Upload a file"
MANUAL = "enter_manually"

# How each fix option reads on screen. Which options an issue offers is
# decided in src/validation.py; this is wording only.
OPTION_LABELS = {
    "infer_current_year": "Use this year",
    "enter_manually": "Type the correct value",
    "use_date_joined": "Use the Date Joined",
    "same_person": "Same person (a renewal)",
    "different_people": "Different people who share a name",
}


def configured_today() -> date:
    """Today, read once for the whole run; GYM_TODAY pins it (shell configuration)."""
    pinned = os.environ.get("GYM_TODAY")
    return date.fromisoformat(pinned) if pinned else date.today()


def default_sheet_path() -> str:
    return os.environ.get("GYM_SHEET") or next(iter(sys.argv[1:]), "")


def choose_sheet() -> Path:
    mode = st.radio("Where is the sheet?", (PATH_MODE, UPLOAD_MODE), horizontal=True, key="mode")
    if mode == UPLOAD_MODE:
        return uploaded_sheet()
    typed = st.text_input("Sheet path", value=default_sheet_path(), key="sheet_path")
    cleaned = typed.strip().strip('"')
    if not cleaned:
        st.info("Enter the path of the members sheet (CSV or Excel) to begin.")
        st.stop()
    return Path(cleaned)


def uploaded_sheet() -> Path:
    upload = st.file_uploader("Members sheet", type=["csv", "xlsx"], key="upload")
    if upload is None:
        st.info("Upload the members sheet (CSV or Excel) to begin.")
        st.stop()
    path = save_upload(DATA_DIR, upload.name, upload.getvalue())
    st.caption(f"Working copy: {path}. Corrections and payments are saved beside it; "
               "your original file is never changed.")
    return path


def ask_about_stale_corrections(sheet: Path) -> None:
    st.warning(
        f"{sheet.name} has changed since your corrections were saved in members_clean.csv. "
        "Using the corrections would hide anything new in the sheet.")
    keep, discard = st.columns(2)
    if discard.button("Discard my corrections and use the sheet", key="discard_corrections"):
        discard_corrections(sheet)
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
                       format_func=OPTION_LABELS.get, horizontal=True)
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
                 "named above, save, and load it again.")
        st.stop()
    st.subheader("Fix them here")
    fixes = [answer_widgets(issue, rows, today) for issue in report.issues]
    chosen = [f for f in fixes if f is not None]
    if st.button("Apply fixes", key="apply_fixes", type="primary", disabled=not chosen):
        corrected = apply_fixes(rows, chosen, current_year=today.year)
        write_clean_members(clean_members_path(sheet), corrected)
        st.rerun()
    st.stop()


def show_dashboard(rows, sheet: Path, today: date) -> None:
    merge = with_ledger(build_dataset(rows), read_payments(payments_path(sheet)))
    for warning in views.ledger_warnings(merge):
        st.warning(warning)
    figures = views.tiles(all_statuses(merge.dataset, today))["display"]
    for column, (label, value) in zip(st.columns(len(figures)), figures.items()):
        column.metric(label, value)


def main() -> None:
    st.set_page_config(page_title="Gym payments", layout="wide")
    st.title("Gym payments")
    today = configured_today()
    sheet = choose_sheet()
    if corrections_stale(sheet):
        ask_about_stale_corrections(sheet)
    resolved = resolve_input(sheet)
    if resolved.used_clean_sidecar:
        st.info(f"Showing corrected data from {clean_members_path(sheet)}, "
                f"not {sheet.name} itself (which is never changed).")
    report = validate(resolved.rows, resolved.columns)
    if not report.is_clean:
        show_issues(report, resolved.rows, sheet, today)
    show_dashboard(resolved.rows, sheet, today)


try:
    main()
except PermissionError as exc:
    st.error(f"{Path(exc.filename or 'A file').name} is open in another program, probably "
             "Excel. Close it there, then press R to retry.")
except FileNotFoundError as exc:
    st.error(f"There is no file at {exc.filename}. Check the path and try again.")
except UnicodeDecodeError:
    st.error("The sheet is not a UTF-8 CSV. In Excel, save it as 'CSV UTF-8' or as .xlsx.")
except (ValueError, ImportError) as exc:
    st.error(str(exc))
