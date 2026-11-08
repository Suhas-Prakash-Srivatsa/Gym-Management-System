# Validation rules and report

Status: resolved
Blocked by: 02, 04

## Goal

Turn bad input into specific, answerable questions — one per row, naming the column — and express the remedy as data so the UI contains no knowledge of what is fixable.

## Deliverables

`src/validation.py`: `Issue`, `Report`, `check_required_columns`, `check_dates`, `check_membership_type`, `check_instalments`, `check_amounts`, `check_last_payment_date`, `check_duplicate_names`, `validate`, `apply_fixes`.

## Acceptance criteria

- One function per rule; each takes a row (except `check_duplicate_names`, which needs all rows) and returns `list[Issue]`.
- `Issue` carries `row_number`, `column`, `code`, a human message, and `fix_options` (e.g. `infer_current_year` | `enter_manually`).
- The two questions only the owner can answer are **never defaulted**: a missing year and a duplicate name with no `Member ID`. Both must surface as an explicit choice.
- Missing required column is fatal and not fixable in-dashboard.
- `apply_fixes(rows, fixes) -> rows` is pure and returns new rows; it writes nothing.
- A `Report` with any issue means no dashboard is rendered (spec: validation is fatal before any figure is shown).

## Tests

`tests/test_validation.py`, driven by `src/files/Book1_errors.csv`, which carries exactly one instance of each rule:

- `1st June` / `1st September` → date issues offering `infer_current_year`
- Vandana: `Paid Amount` 8000 with empty `Last Payment Date` → issue offering `use_date_joined`
- Rakesh Sharma ×2 with no `Member ID` → one duplicate-name issue asking renewal-or-two-people
- Anita Rao: `Installments` 0 → issue; `Paid Amount` 15000 > `Membership Amount` 12000 → issue
- Vinod Bhatt: `Quarterly` → unrecognised membership type
- A clean `Book1.csv` produces an empty, non-fatal report
- `apply_fixes` with `infer_current_year` leaves the input rows unmutated and returns corrected copies

## Comments

- 2026-11-08: Implemented, reviewed and committed. Book1_errors.csv yields 9 issues (Vandana and Rakesh rows each hit two rules).
- 2026-11-08: Follow-up committed. Added `check_duplicate_membership_ids`, which flags rows that would assemble under one Membership ID (compared after `<member_key>-NN` generation, so a generated ID colliding with a typed one is caught); one issue per ID, anchored at its first row, fixed with `enter_manually`. `check_instalments` now requires ASCII digits, so "²" is reported instead of crashing. The identity scheme (`is_blank_row`, `member_key`, `generate_membership_id`, `effective_membership_ids`) moved to `src/identity.py`, shared by validation and assembly.
