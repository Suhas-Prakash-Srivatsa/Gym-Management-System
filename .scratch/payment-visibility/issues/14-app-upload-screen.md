# App: upload screen as the owner's way in

Status: resolved
Blocked by: 10, 12

## Goal

A gym owner should never have to type a file path. The first thing they see is an upload screen; the sheet they upload becomes their working copy under `data/`, and they can come back to it later without re-uploading.

Decided by the user on 2026-11-08 ("create an upload screen within streamlit that gym owners can use to upload files"), replacing the path-first flow from ticket 10.

## Deliverables

The entry section of `app.py`, plus any pure helpers it needs in `src/sidecar.py` (the only module allowed to touch `data/`).

## Acceptance criteria

- With no `GYM_SHEET` and no CLI argument, the app opens on an **upload screen**: a title, one sentence on what to upload (CSV or Excel members sheet), the uploader, and a line saying the original file is never changed. There is no "Where is the sheet?" radio and no path text box.
- **Returning owner:** if `data/` already holds working copies from earlier uploads, the screen also offers them (by original file name, most recently used first) so the owner can reopen one, with its payments and corrections, without uploading again.
- **Re-upload of the same file name** lands at the same working copy, so the payment ledger and corrections beside it are kept. The owner is told the existing payments were kept. If the new upload's bytes differ from the working copy and a corrected copy exists, the existing stale-corrections prompt (Discard/Keep) still applies, so an unchanged re-upload does **not** trigger it.
- **Developer/test route:** `GYM_SHEET` or a CLI argument after `--` still opens that path directly, skipping the upload screen. This keeps the existing AppTest suites working; it is not shown to owners.
- Friendly on-screen errors for a rejected upload (wrong type, unsafe name, empty file), never a traceback.
- ADR 0001 holds: no business rules or arithmetic in `app.py`; listing and choosing working copies is a pure or `sidecar.py` function.

## Tests

- Unit tests for any new `sidecar.py` helper (listing working copies, ordering, an unchanged re-upload leaving mtime/bytes alone).
- AppTest for the upload screen with no env var: uploader present, no path box, previous-uploads picker shown when `data/` (a tmp dir) has copies, and reopening one renders the dashboard. If `AppTest` cannot drive `file_uploader` in Streamlit 1.67, test the reopen path through AppTest and the save path through the helper, and say so in the ticket comments.
- Manual: `streamlit run app.py`, upload `src/files/Book1.csv`, record a payment, re-upload the same file → payment still reflected.

## Comments

- 2026-11-09 (coder): Implementation notes.
  - **AppTest can drive `st.file_uploader` in Streamlit 1.67** (`at.file_uploader(key=...).set_value((name, bytes, mime))`), so the upload itself is tested end to end in `tests/test_upload_screen.py`: upload → dashboard, rejected uploads, re-upload keeping payments, changed re-upload → Discard/Keep, reopening an earlier upload, going back to upload another sheet.
  - **No `type=` on the uploader.** With `type=["csv", "xlsx"]`, Streamlit 1.67 checks the extension while deserialising the widget, before the script runs, and raises `StreamlitAPIException`, which the app cannot catch, so the owner would see a traceback. `save_upload` now refuses anything but `.csv`/`.xlsx` (case-insensitive) and empty files with a sentence. The cost: the browser's file picker no longer filters by type. The label and caption say CSV or Excel instead.
  - **"Most recently used"** (`sidecar.working_copies`) is the newest mtime of any file in the copy's folder (sheet, `payments.csv`, `members_clean.csv`, backups). So uploading, recording a payment or saving corrections count as use; just opening a copy does not, because opening writes nothing. Ties go by name.
  - **Re-upload**: `sidecar.receive_upload` returns `SavedUpload(path, changed, kept_payments)`. Same name → same folder, so sidecars are never touched. Identical bytes are not rewritten, so the mtime-based stale prompt does not fire. Different bytes replace the copy, and the existing Discard/Keep prompt applies when corrections exist. When a `payments.csv` was already there, the owner sees "The payments already recorded for it were kept."
  - **Flow**: the upload screen stores the opened working copy in session state and reruns, so the upload is processed once, not on every rerun. The dashboard shows the working-copy caption and an "Open a different sheet" button. `GYM_SHEET` / CLI argument still open a path directly; the path radio and text box are gone. `GYM_DATA_DIR` overrides `./data` (documented in the app.py docstring).
- 2026-11-09 (coder): Rework from the tester.
  1. **Corrupt .xlsx**: `sheet._xlsx_records` turns openpyxl's `BadZipFile` / `InvalidFileException` / `KeyError` into a `ValueError` ("<name> is not a readable Excel file. Save it again from Excel as .xlsx or as CSV, then try again."). This covers both the `GYM_SHEET` route and the upload route.
  2. **Unreadable uploads are not kept**: `receive_upload` reads the bytes as a sheet in memory before writing anything (`_check_readable`), so a non-UTF-8 CSV or a broken .xlsx leaves nothing in `data/` and never replaces a good copy or touches its sidecars. Wrong-type and empty checks still run first, so their messages win. The raw saver `save_upload` does not read the sheet; the app always goes through `receive_upload`.
  3. **Long names**: names over 80 characters (`MAX_UPLOAD_NAME`) are refused before any folder is made ("The file name is too long ..."). The name is used for both the folder and the file, and Windows paths stop at 260 characters by default. The tester's acceptance case for this name expected the old OSError wording ("Could not use") and now expects "too long".
  Also added a test that the "payments kept" notice shows once and is gone on the next rerun (kills mutant M6, `pop` → `get`).
- 2026-11-09 (coder): Second rework from the tester.
  - **Broken workbooks** are all "<name> is not a readable Excel file ..." (`sheet._xlsx_records`). The catch now covers both `load_workbook` and the lazy worksheet iteration (read-only mode parses the sheet XML there, so a truncated `sheet1.xml` raised `ParseError`). It catches `BadZipFile`, `InvalidFileException`, `KeyError` (a zip without `[Content_Types].xml`), `OSError` ("no valid workbook part", e.g. a renamed .docx), `ParseError` and `IndexError`. `OSError` is safe to catch there because the bytes are already in memory: a real lock or missing file is raised earlier by `_read_bytes` and keeps its own message (pinned by a test with a locked .xlsx on the `GYM_SHEET` route).
  - **`csv.Error`** (e.g. a cell over the 131,072-character field limit) becomes "<name> cannot be read as CSV (...)" in `read_rows`; on upload nothing is kept.
  - Tests for each case: by path, through `receive_upload` (nothing kept), and on screen. The hello.txt-in-a-zip case kills mutant N3.
- 2026-11-09 (coder): Third rework from the tester. In `sheet._xlsx_records` the catch now wraps only openpyxl's calls: `load_workbook` + `worksheets[0]` + `iter_rows` in one try, and each `next(rows)` in its own (StopIteration ends the loop). `_cell_text` and the blank-row check run outside any catch, so a bug of ours surfaces as itself (tests monkeypatch `_cell_text` to raise KeyError/IndexError/OSError). `workbook.close()` stays in a `finally`. A date cell written into an .xlsx reads as "2026-06-01". openpyxl 3.1.5 returns date cells as `datetime`, so the pure-`date` branch of `_cell_text` is only reachable by calling it directly, and is pinned that way (kills N5).
- 2026-11-09 (committer): Reviewed (standards + spec) and committed. Full suite green: 790 passed. Non-blocking follow-up: on Windows, re-uploading under a different letter case (Book1.csv then book1.csv) renames the file inside the existing folder, so `_is_working_copy` (case-sensitive folder/name match) drops it from the earlier-uploads list; re-uploading reaches it again and payments are kept.
- 2026-11-09 (coder, ticket 13): Fixed the letter-case follow-up. Two changes in `src/sidecar.py`, each test-first in `tests/test_upload_screen.py`:
  1. **No rename.** `_working_copy_path` now reuses the folder and file names already stored in `data/` when they match ignoring case (`_stored_as`). So `Book1.csv` then `book1.csv` reaches `data/Book1_csv/Book1.csv`: the bytes are replaced as usual, payments are kept, and the copy keeps the name it was first uploaded under. Before, `os.replace` on Windows renamed the file to `book1.csv` inside `Book1_csv`.
  2. **Listing.** `_is_working_copy` compares the folder name with the file name ignoring case, so a copy already renamed by the earlier code (`Book1_csv/book1.csv`) is listed again.
  On a case-sensitive file system this also folds `Book1.csv` and `book1.csv` into one working copy, which matches how the owner thinks of them.
