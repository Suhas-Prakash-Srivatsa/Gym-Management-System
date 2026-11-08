# Payment ledger and sidecar files

Status: ready-for-agent
Blocked by: 02

## Goal

Persist the two derived files beside the owner's sheet, and never touch the sheet itself (ADR 0002).

## Deliverables

- `src/ledger.py`: `read_payments`, `append_payment`, `next_payment_id`.
- `src/sidecar.py`: `payments_path`, `clean_members_path`, `read_clean_members`, `write_clean_members`, `resolve_input`.

## Acceptance criteria

- `append_payment` opens the file in **append** mode (`"a"`) and writes one row, creating it with a header when absent. A read-modify-write implementation is rejected: it can truncate the ledger on a crash and destroy payment history, which append mode physically cannot.
- `payments.csv` columns: `payment_id, membership_id, amount, paid_on, source, recorded_at`.
- Nothing in either module writes to the input sheet path — ever.
- `resolve_input` prefers `members_clean.csv` when present and **reports which file was used**, so the owner can be told they are looking at corrected data rather than their original sheet.
- Amounts round-trip through CSV as `Decimal` with no `float` in between.

## Tests

`tests/test_ledger.py` (using a temp directory):

- Appending to a ledger with 3 rows yields 4, with the original 3 byte-identical.
- `read_payments(append_payment(...))` round-trips amount, date and source exactly.
- `next_payment_id` never collides with an existing id.
- `payments_path` / `clean_members_path` resolve next to the input file, not into the working directory.
- `resolve_input` returns the cleaned rows and a flag when the sidecar exists, the raw rows and no flag when it does not.
