# App: dashboard render

Status: resolved
Blocked by: 09, 10

## Goal

Show the owner what they are owed, worst first.

## Deliverables

The dashboard section of `app.py`: four tiles, the receivables table, the *Show fully paid* toggle.

## Acceptance criteria

- Tiles: Total Members · Total Membership Value · Total Receivable · Overdue, all from `views.tiles`.
- One table from `views.receivables_rows`, in the order that function returns — `app.py` does not sort.
- Overdue rows carry a visually distinct red `DUE` tag.
- Columns: Member Name, Membership ID, Membership Type, Date Joined, Contract Amount, Paid, Outstanding, Last Payment Date, Next Due Date, status.
- *Show fully paid* is an unchecked-by-default toggle.
- `date.today()` is called **once**, here in the shell, and passed into `all_statuses`. It appears nowhere in `src/`.
- No arithmetic in this section.

## Tests

Manual, against `Book1.csv` at 2026-11-08: tiles read 24 members / ₹2,35,400 total membership value / ₹97,300 receivable / ₹60,950 overdue; 19 rows; 11 `DUE` tags; Pooja Shetty first; toggling *Show fully paid* adds 7 rows.

## Comments

- 2026-11-08: Implemented, reviewed and committed. `app.py` renders the four `views.tiles` figures, a *Show fully paid* toggle (off by default) and one `views.receivables_rows` table in the order and columns views gives (`ROW_COLUMNS`), with no sorting or arithmetic in the shell. `today` is read once in `configured_today` and passed to `all_statuses`. Decisions: settled rows show "—" for Next Due (views still orders them by the typed date). The red `DUE` styling is a pandas Styler on the Status column, keyed on views' `is_overdue`, so the shell decides nothing. The table uses `width="stretch"` (Streamlit 1.67). Ticket 10 leftovers fixed in this commit: `sidecar.check_sheet` (a folder is refused clearly; a missing file gives FileNotFoundError), a Windows-name guard on uploads (invalid characters, reserved names like CON, trailing dot or space), timestamped `members_clean.csv.<YYYYMMDD-HHMMSS>.bak` backups that never overwrite an earlier one, an `OSError` catch in the shell, and neutral "save the sheet and reload" wording.
