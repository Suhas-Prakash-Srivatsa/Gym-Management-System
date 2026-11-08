# App: record a payment

Status: ready-for-agent
Blocked by: 08, 11

## Goal

Let the owner record money as it arrives, with as few questions as the domain allows.

## Deliverables

The payment form section of `app.py`.

## Acceptance criteria

- Pick Member → amount → date. A Membership selector appears **only** when `recording.attribution_required` is `True`, pre-selected to `recording.default_membership`. In `Book1.csv` that means 22 of 24 members never see it.
- Submit runs `validate_payment`; rejections render beside the field with the ceiling named. Future-dated payments warn but submit.
- Accepted payments are appended via `ledger.append_payment` — one new row, nothing rewritten.
- After submission the page reruns and Total Receivable falls by exactly the amount entered.
- No arithmetic and no attribution rule in `app.py`; both come from `src/recording.py`.

## Tests

Manual, against `Book1.csv`:

- Record ₹6,000 against Suhas Prakash → Membership selector appears listing MS-001 and MS-025, defaulted to MS-001; Total Receivable falls to ₹91,300 and MS-001 leaves the table.
- Record ₹6,001 against MS-001 → rejected, message names ₹6,000, nothing appended.
- Record against Priya Nair (one Membership, fully paid) → no selector, and any positive amount is rejected on zero outstanding.
- `payments.csv` grows by exactly one row per accepted payment and prior rows are untouched.
