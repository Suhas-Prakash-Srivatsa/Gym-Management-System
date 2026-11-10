# Handover — payment-visibility (2026-11-08, session 2)

Read this first. Then the ticket you're on, TECHNICAL-PLAN.md, spec.md, GLOSSARY.md, docs/adr/.

## 1. State
- Branch `main`, no remote. HEAD `61c7e87`. Suite: **656 passed** (`python -m pytest -q`, ~40s; AppTest tests are the slow ones).
- Working tree: only `Plan.md` deleted (not by agents; still in git; user hasn't answered — keep it out of commits) and this file (untracked, never commit).
- Installed (system Python 3.14): openpyxl 3.1.5, streamlit 1.67.0 (brings pandas).
- Commits this session: b006384 T06 · 7c61730 T05 follow-up · 354a683 T07 · 7f27edc T08 · 5302204 T09 · 565460f T10 · 61c7e87 T11 (+T10 hardening).

## 2. Done (02–11 resolved; 01 = needs-info, not code)
- **identity.py** (new, core): single ID scheme — `is_blank_row`, `member_key`, `generate_membership_id`, `effective_membership_ids` (validation + assemble both use it), `next_payment_id` (`P-NNNN`, from max), `opening_payment_id` (`OPEN-<membership_id>`). ledger/assemble/validation re-export for old imports.
- **assemble.py**: `build_dataset` (one Member per key, renewals → many Memberships, ₹0 paid → no Payment, opening Payments `source=opening`, `recorded_at` = midnight of paid_on); `with_ledger(dataset, ledger) -> LedgerMerge(dataset, orphaned, conflicting)` — dedupes by payment_id, never counts orphans/conflicts.
- **validation.py**: + `check_duplicate_membership_ids` (effective IDs), instalments ASCII-only, `Issue.severity` ("error"/"warning") + `.blocking`, `Report.is_clean` = no blocking issue, `fix_for`, `preview_fix`/`FixPreview` (future-date warning for infer year).
- **ledger.py**: `read_payments` (utf-8-sig, by column name, amount must match `[0-9]+(\.[0-9]{1,2})?` and > 0, bad line → ValueError naming line), `append_payment` (mode "a" only, header if new/empty, repairs missing final newline, refuses bad amount or header ≠ COLUMNS).
- **sidecar.py**: paths beside input; `resolve_input -> ResolvedInput(rows, columns, used_clean_sidecar)`; `write_clean_members` (tmp + os.replace, BOM, keeps member_id); `check_sheet` (folder/missing); `save_upload` (→ `data/<stem>_<ext>/<name>`, refuses traversal, Windows-invalid/reserved names, sidecar names); `corrections_stale` (sheet mtime > sidecar); `discard_corrections(input, stamp)` → timestamped `.bak`, never overwrites; `keep_corrections`.
- **recording.py**: `attribution_required`, `default_membership` (earliest Next Due **among Outstanding > 0**, else earliest overall; ties sheet order), `validate_payment(dataset, membership, amount, paid_on, today) -> list[Issue]` (errors: invalid_amount incl. >2dp/NaN/huge, amount_not_positive, exceeds_outstanding "Suhas Prakash / MS-001 has ₹6,000 outstanding — enter ₹6,000 or less"; warnings: paid_on_in_future, paid_before_joining; never raises), `build_payment(membership, amount, paid_on, ledger, recorded_at)` (quantized plain amount, source=recorded, id from RAW ledger).
- **money.py**: `format_money` Indian grouping (₹2,35,400), paise only when present.
- **views.py**: `tiles`, `receivables_rows(statuses, show_fully_paid)`, `issue_rows`, `ledger_warnings`, `ROW_COLUMNS`, `TILE_LABELS`, `ISSUE_COLUMNS`. Each dict = typed values + `display` dict of strings keyed by screen label. Status "DUE"/""/"Paid"; settled rows show "—" Next Due.
- **app.py**: path mode primary (text input / `GYM_SHEET` / CLI arg after `--`), upload fallback; `configured_today()` = `GYM_TODAY` or `date.today()` (once); stale-corrections Discard/Keep prompt; issues table + fix widgets from `fix_options` (radios `index=None`, Apply disabled until answered) → apply_fixes → write_clean_members → rerun; dashboard = 4 metrics + one dataframe (pandas Styler red on Status where `is_overdue`), "Show fully paid" toggle off; friendly errors for PermissionError/FileNotFoundError/OSError/UnicodeDecodeError/ValueError. `datetime.now()` used once for .bak stamp.
- Docs changed: spec.md Done-when now pays MS-001 (MS-025 is fully paid); spec rule 7 + ticket 08 "Decisions" for default_membership; issue 01 comment on token-payment grace reset.

## 3. Next: ticket 12 (app: record a payment), then 13 (golden test + README + requirements.txt), then full-system run.
Not started. Brief for 12:
- Form: Member select (show `Member.name`, never the key) → Membership select only if `attribution_required`, preselected `default_membership` → amount → date → submit.
- `validate_payment` issues beside the field; blocking → nothing appended; warnings shown but submit allowed (decide: confirm checkbox or just show).
- `build_payment(..., ledger=read_payments(path) RAW, recorded_at=now)` → `append_payment` → `st.rerun()`. Total Receivable must fall by exactly the amount.
- **Fold clock reads into one**: single `now` read in app.py; `today = GYM_TODAY or now.date()`; reuse `now` for recorded_at and .bak stamp. Update the app.py clock test accordingly.
- Catch PermissionError (Excel lock) / ValueError from append as on-screen messages.
- Manual tests in ticket: ₹6,000 vs Suhas → selector MS-001/MS-025 default MS-001, receivable ₹91,300, MS-001 leaves table; ₹6,001 rejected naming ₹6,000, nothing appended; Priya Nair (one Membership, settled) → no selector, any amount rejected; payments.csv +1 row, prior bytes untouched. Use AppTest.
- Ticket 13: requirements.txt must list streamlit, pandas, openpyxl, pytest. Golden test: Book1 + empty ledger at 2026-11-08 → 19 / 11 / ₹97,300 / ₹60,950; Rohit Desai MS-011 not overdue on 2026-11-05, overdue on 2026-11-08. README per ticket (+ path vs upload mode, GYM_TODAY, data/ folder, token-payment note). Also a doc pass: TECHNICAL-PLAN lacks identity.py, with_ledger, Issue.severity, ResolvedInput, check_sheet, recording→identity edge; ticket 09 lists format_money under views; issue 01/TECHNICAL-PLAN line ~157 still say plain "earliest Next Due Date"; GLOSSARY lacks Total Membership Value / Total Members.
- Final: full suite + headless `streamlit run` smoke + end-to-end Done-when scenario from spec.md.

## 4. Constraints (keep)
- Pure core: no I/O, no streamlit, no clock in src/ except sheet/ledger/sidecar touch disk. Decimal never float. Input sheet never written. ADR 0001: app.py has no arithmetic, no date comparison, no business `if` (AST test enforces part of this).
- Membership IDs matched exactly (case-sensitive) everywhere — pinned by tests.
- Opening Payments never written to payments.csv; rebuilt from sheet each import.
- `next_payment_id`/`build_payment` get the RAW ledger, never `merge.dataset.payments`.
- Amounts written to the ledger must be plain quantized form.

## 5. Open edge cases / follow-ups
- **Business question (issue 01, for gym owners):** spec rule 4 restarts Next Due at Last Payment, so a ₹100 token payment clears DUE and removes the whole Outstanding from the Overdue tile for 2 months.
- `id` header alias → member_id ambiguous. apply_fixes groups duplicates by pre-fix names. 29 Feb infer-year message misleading.
- Case-only ID near-duplicates (MS-1 / ms-1, M001 / m001) not warned. Same Member ID with different names → first name wins silently.
- mtime-based stale check can be fooled by timestamp-preserving copies (hash would be more robust); Excel re-save without change triggers a harmless prompt.
- Ledger with extra columns (owner added "Notes") → append refused; needs a clear message in ticket 12.
- Upload mode has no AppTest (file_uploader); save_upload is unit-tested.
- DUE colour is hard-coded white-on-red (no dark-theme adaptation).

## 6. Process (user's request)
3 agents per ticket: **coder** (mattpocock-skills:tdd, red first; no commits) → **tester** (superpowers:verification-before-completion, hand-checks vs fixtures, mutation testing with binary-mode hash-verified restore, adds `tests/test_*_acceptance.py`, PASS/REWORK; rework loops back to coder) → **committer** (mattpocock-skills:code-review, full suite, sets ticket `Status: resolved` + dated `## Comments` line, stages explicit paths only, Co-Authored-By trailer). `ask-matt` skill is NOT installed; these are the substitutes. Run tickets sequentially (shared working tree; tester mutates files).
