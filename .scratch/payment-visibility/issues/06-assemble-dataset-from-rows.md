# Assemble the dataset from validated rows

Status: ready-for-agent
Blocked by: 02, 04, 05

## Goal

Cross the boundary once: validated `RawRow`s in, domain objects out. After this function returns, no code downstream needs a guard clause.

## Deliverables

`src/assemble.py`: `member_key`, `generate_membership_id`, `opening_payment`, `build_dataset(rows) -> Dataset`.

## Acceptance criteria

- `member_key` prefers `Member ID`; falls back to the normalised name.
- Two rows sharing a member key produce **one** `Member` and **two** `Membership`s (the renewal case).
- `Membership ID` from the sheet wins; generated as `<member_key>-01`, `-02` when absent, which requires seeing all rows.
- `opening_payment` returns `None` when `Paid Amount` is 0 — a ₹0 Payment never happened, and inserting one would set a Last Payment Date and wrongly reset the grace clock for a member who has paid nothing.
- Opening Payments carry `source="opening"` and are dated by `Last Payment Date`.
- No validation here; assembly assumes valid rows (ticket 05 owns that).

## Tests

`tests/test_assemble.py`, against `Book1.csv`:

- 26 rows → 24 `Member`s and 26 `Membership`s.
- Suhas Prakash (`M001`) owns MS-001 and MS-025; Manoj Verma (`M009`) owns MS-009 and MS-026.
- The four rows with `Paid Amount` 0 (MS-007, MS-011, MS-015, MS-022) produce no Payment at all.
- 22 Opening Balance Payments are produced, each dated from its row's `Last Payment Date`.
- A sheet with no `Membership ID` column generates `-01`/`-02` suffixes per member.
