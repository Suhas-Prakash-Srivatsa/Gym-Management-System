# Balance and overdue rules

Status: resolved
Blocked by: 02

## Goal

Implement every money and timing rule from the spec (rules 1–5) as pure functions. This is the heart of the program; the rest of the codebase reads from it.

## Deliverables

`src/balances.py`: `payments_for`, `total_paid`, `outstanding_balance`, `last_payment_on`, `next_due_on`, `is_overdue`, `status_for`, `all_statuses`.

## Acceptance criteria

- `today` is a **parameter** of every function that needs it. No module-level or inline `date.today()`.
- `next_due_on` anchors to the latest Payment date, falling back to `joined_on` when the Membership has no Payments.
- `is_overdue` requires **both** `today > next_due_on` **and** `outstanding_balance > 0`.
- `outstanding_balance` is floored at zero and never negative.
- No file access, no printing, no Streamlit import.

## Tests

`tests/test_balances.py`:

- Owing money inside the grace window is **not** overdue (paid ₹6,000 of ₹12,000 yesterday → not overdue).
- Fully paid but historically late is **not** overdue.
- Never-paid Membership anchors to `joined_on`: joined 2026-09-05, nothing paid → overdue on 2026-11-08, not overdue on 2026-11-05.
- A Membership with two Payments anchors to the later one.
- Outstanding for a never-paid Membership equals the full Contract Amount.

## Comments

- 2026-11-08: Implemented, reviewed and committed.
