# Recording a payment

Status: resolved
Blocked by: 02, 03, 07

## Goal

The rules governing new money: which Membership it belongs to, and whether it is allowed at all.

## Deliverables

`src/recording.py`: `attribution_required`, `default_membership`, `validate_payment`, `build_payment`.

## Acceptance criteria

- `attribution_required` is `True` only when the Member holds more than one Membership. One Membership → attribute automatically, ask the owner nothing.
- `default_membership` picks the Membership with the earliest Next Due Date. (see Decisions)
- `validate_payment` rejects `amount > outstanding_balance`, with the ceiling named in the message ("Suhas Prakash / MS-001 has ₹6,000 outstanding — enter ₹6,000 or less"). This is the rule that enforces the no-overpayment decision; a per-payment-vs-contract check would let two ₹7,000 payments sum to ₹14,000 against a ₹12,000 contract.
- Rejects `amount <= 0`. Warns (does not reject) on a `paid_on` in the future. Allows back-dated `paid_on`, because cash gets recorded days late.
- Returns `list[Issue]` rather than raising — expected user error belongs next to the form field, not in a traceback.
- These rules live here, not in `app.py`, so that issue `01` has something findable to revisit.

## Tests

`tests/test_recording.py`:

- A Member with one Membership → `attribution_required` is `False`.
- Suhas Prakash (two Memberships) → `True`, and `default_membership` returns MS-001 (due 2026-08-01) over MS-025.
- ₹6,001 against ₹6,000 outstanding → rejected, message contains `6,000`.
- ₹6,000 against ₹6,000 → accepted, and Outstanding becomes exactly 0.
- Two sequential ₹3,000 payments against ₹6,000 → both accepted; a third is rejected.
- Future `paid_on` → warning issue, payment still constructible.

## Decisions

- `default_membership` picks the earliest Next Due Date among the Member's Memberships with Outstanding Balance > 0, else the earliest overall; equal dates keep sheet order. A settled contract would only invite a payment the over-payment rule refuses (Manoj Verma defaults to MS-026, not the settled MS-009).
- A `paid_on` before Date Joined **warns** (`paid_before_joining`, "check the year"), it does not block: renewals are paid in advance.
- An amount with more than 2 decimal places is **rejected** (`invalid_amount`), not rounded: rounding would record money the owner did not enter. The same code covers non-finite and out-of-range amounts; `validate_payment` never raises.
- `Issue.severity` (`error` | `warning`) and `Issue.blocking` let the shell tell a blocking error from a warning without knowing any codes.

## Comments

- 2026-11-08: Implemented, reviewed and committed. `src/recording.py` provides `attribution_required`, `default_membership`, `validate_payment` (returns Issues, never raises; errors `invalid_amount`, `amount_not_positive`, `exceeds_outstanding` naming the ceiling in Indian format; warnings `paid_before_joining`, `paid_on_in_future`) and `build_payment` (P-NNNN id from the raw ledger, amount stored to 2 places). Added `money.format_money` with Indian grouping and `Issue.severity`/`blocking`; `Report.is_clean` now means no blocking issue. Payment id rules moved to `src/identity.py`. spec.md rule 7 and the Done-when scenario updated to match (MS-025 is fully paid, so the scenario records against MS-001).
