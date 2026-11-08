# App: dashboard render

Status: ready-for-agent
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
