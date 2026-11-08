# Domain types, money and date primitives

Status: ready-for-agent
Blocked by: —

## Goal

Establish the vocabulary as types, and the two primitives every money rule depends on. Nothing above this ticket can be written correctly until rupees add up exactly and "two calendar months" has one definition.

## Deliverables

- `src/models.py` (replaces the existing file): `MembershipType` enum with `.months` → 1/6/12; frozen dataclasses `Member`, `Membership`, `Payment`, `Dataset`, `MembershipStatus`. Monetary fields are `Decimal`. No behaviour, no I/O, no derived fields stored.
- `src/money.py`: `parse_money`, `quantize`.
- `src/dates.py`: `add_calendar_months`, `parse_date`.
- **Delete** `src/loader.py` and `src/analyze.py`. They encode the rejected flat model (`installments: bool`, inline arithmetic in a print loop, a loader returning `None`). Leaving them means two contradictory models in one `src/`.

## Acceptance criteria

- `Payment` and `Membership` are `frozen=True` — append-only and sheet-immutability enforced by the type, not by convention.
- `Membership` has no `paid_amount`, `pending_amount` or `next_payment_date` field.
- No `float` anywhere in the three modules.
- `parse_date` returns `None` for a yearless date rather than raising.
- `add_calendar_months` clamps to month end.

## Tests

`tests/test_money.py`: `"₹12,000"`, `"12,000"`, `" 9500 "` all parse; negatives and `"abc"` rejected; repeated addition of parsed values stays exact.

`tests/test_dates.py`: `2026-12-31 + 2 → 2027-02-28`; `2027-12-31 + 2 → 2028-02-29`; `2026-06-01 + 2 → 2026-08-01`; `"1st June"` → `None`; `2026-06-01`, `01/06/2026`, `1 June 2026` all parse to the same date.
