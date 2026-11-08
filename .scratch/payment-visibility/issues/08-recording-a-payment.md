# Recording a payment

Status: ready-for-agent
Blocked by: 02, 03, 07

## Goal

The rules governing new money: which Membership it belongs to, and whether it is allowed at all.

## Deliverables

`src/recording.py`: `attribution_required`, `default_membership`, `validate_payment`, `build_payment`.

## Acceptance criteria

- `attribution_required` is `True` only when the Member holds more than one Membership. One Membership → attribute automatically, ask the owner nothing.
- `default_membership` picks the Membership with the earliest Next Due Date.
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
