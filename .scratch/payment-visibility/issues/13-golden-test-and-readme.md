# Golden test and README

Status: resolved
Blocked by: 06, 09, 12, 14

## Goal

One test that fails if any link in the chain is wrong, and instructions a gym owner can actually follow.

## Deliverables

- `tests/test_golden.py`
- `README.md`
- `requirements.txt` (streamlit, pytest; pandas only if actually needed)

## Acceptance criteria

The golden test loads `src/files/Book1.csv` with an empty ledger at a frozen `today = 2026-11-08` and asserts the four hand-calculated figures:

| Figure | Expected |
|---|---|
| Rows with Outstanding > 0 | 19 |
| Of those, Overdue | 11 |
| Total Receivable | ₹97,300 |
| Overdue total | ₹60,950 |

These were calculated by hand from the fixture during design. A single wrong boundary, sign, or anchor anywhere between the sheet reader and the view projections changes at least one of them — which is the point of asserting all four rather than one.

It must also assert the frozen-clock boundary: at `today = 2026-11-05`, Rohit Desai (MS-011) is **not** overdue; at 2026-11-08 he is. This is the only test that proves `today` is genuinely injected rather than read from the system clock somewhere.

README covers: what the tool answers, the column contract (required vs optional, aliases), that the input sheet is never modified and what the two sidecars are, the fixed 2-month grace rule, `pip install -r requirements.txt` + `streamlit run app.py`, and the V1 non-goals (no accounts, no hosting, no overpayment).

## Tests

`pytest` green across all test files, run and output confirmed before this ticket is closed.

## Comments

- 2026-11-09 (committer): Reviewed (standards + spec): no blocking findings. Full suite green: 809 passed in 73.83s. Golden figures 19 / 11 / ₹97,300 / ₹60,950 with the Rohit (MS-011) boundary. Committed together with the ticket-14 letter-case re-upload fix (`src/sidecar.py`) and the doc pass (TECHNICAL-PLAN, GLOSSARY, issues 01 and 09). Non-blocking notes: `_stored_as` matches any entry in the folder, not just files or dirs (an `is_dir()`/`is_file()` check would close it); the casefold comparison now lives in a few places and could share one helper; the two golden test files each build their own Book1.csv path instead of the shared `FILES` constant.
