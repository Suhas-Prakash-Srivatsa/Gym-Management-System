# View projections for tiles and table

Status: ready-for-agent
Blocked by: 03

## Goal

Shape derived data into exactly what the screen shows — as plain Python data, so the eventual FastAPI version serialises these same functions to JSON and reimplements nothing.

## Deliverables

`src/views.py`: `tiles`, `receivables_rows`, `format_money`.

## Acceptance criteria

- `tiles` returns Total Members, Total Membership Value, Total Receivable, Overdue. **No "due this month"** — rejected in the spec as double-counting against Total Receivable and hiding arrears behind a monthly figure.
- `receivables_rows` filters to Outstanding > 0, sorts by Next Due Date **ascending** (most overdue first), and attaches the `DUE` tag where `is_overdue`.
- `show_fully_paid=True` includes settled Memberships, ordered after the unpaid ones.
- Returns lists of dicts / primitives. No Streamlit import, no HTML, no colour.
- `format_money` renders `Decimal("97300")` as `₹97,300`.

## Tests

`tests/test_views.py`, against `Book1.csv` at `today = 2026-11-08`:

- `receivables_rows` returns 19 rows; the first is overdue since 2026-04-20 (Pooja Shetty, MS-020) and the last is due 2027-01-05 (Ritu Malhotra, MS-022).
- Exactly 11 rows carry the `DUE` tag.
- `tiles` → 24 members, Total Receivable ₹97,300, Overdue ₹60,950.
- `show_fully_paid=True` returns 26 rows with the 7 settled ones last.
