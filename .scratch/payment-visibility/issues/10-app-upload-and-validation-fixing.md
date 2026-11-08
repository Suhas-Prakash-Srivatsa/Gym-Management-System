# App: upload and in-dashboard validation fixing

Status: resolved
Blocked by: 04, 05, 06, 07

## Goal

The owner uploads their sheet and fixes its problems on screen, rather than editing Excel, re-exporting and re-uploading.

## Deliverables

The upload and validation section of `app.py`, plus `write_clean_members` wired in.

## Acceptance criteria

- Upload → `resolve_input` → `validate`. If the report has issues, **no tiles and no table are rendered** — a dashboard built on half-valid rows shows a confidently wrong Total Receivable, which the owner then acts on.
- Issues are shown as a table of offending rows with the column named and the message shown; the fix controls offered are generated from each `Issue.fix_options`, so `app.py` decides nothing about what is fixable.
- The two owner-only questions are explicit choices, never pre-applied: *which year?* and *same person or two people?*
- Accepted fixes go through `apply_fixes`, then `write_clean_members`, so they are answered once ever rather than once per run.
- When the cleaned sidecar was used, say so on screen — otherwise it becomes an invisible second source of truth.
- Fatal issues (missing required column) explain what to add and stop.
- No arithmetic, no date comparison, no business `if` in this section (ADR 0001).

## Tests

Not unit-tested (Streamlit shell). Verified manually against both fixtures:

- `Book1_errors.csv` → 9 issues surfaced across 6 rows (rows 1, 2 and 5 each break two rules), no dashboard shown.
- Choosing *infer current year* for rows 1–2 and *two people* for Rakesh Sharma, then correcting the remaining fields, writes `members_clean.csv` and renders the dashboard.
- Re-running picks the sidecar up and asks nothing.
- `Book1.csv` → straight to the dashboard, no issues.
- The original input file's modification time is unchanged after all of the above.

## Comments

- 2026-11-08: Implemented, reviewed and committed. `app.py` runs choose sheet → stale check → `resolve_input` → `validate`. Any blocking issue shows the issue table and fix controls built from `Issue.fix_options` (via `validation.fix_for` / `preview_fix`, nothing pre-applied), and no figures. Fatal issues explain what to add and stop. Fixes go through `apply_fixes` then `write_clean_members`. Decisions: **path mode is primary** (a file on this computer, so sidecars sit beside the real sheet). **Upload** saves a working copy to `data/<stem>_<ext>/` (git-ignored) via `sidecar.save_upload`, so the browser upload has a folder for its sidecars. **`GYM_TODAY`** overrides the clock (read once per run in the shell). **Stale corrections**: when the sheet is newer than `members_clean.csv` the owner must choose **Discard** (sidecar kept as `members_clean.csv.bak`) or **Keep** (sidecar re-stamped as current). `views.issue_rows` and `ledger_warnings` shape the issue table and the ledger notices.
