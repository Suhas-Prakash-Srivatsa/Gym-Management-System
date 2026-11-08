# App: record a payment

Status: resolved
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

## Comments

- 2026-11-08 (coder): UX decisions for the form.
  - **Warnings vs errors.** No confirm checkbox. The form is not an `st.form`, so picking a date reruns at once and any warning (future date, before Date Joined) shows under the date *before* Record is pressed; pressing Record then records it, and the receipt repeats the warning. Errors (unreadable amount, ≤ ₹0, over the Outstanding Balance with the ceiling named) show under the amount only after Record is pressed, and nothing is written.
  - **Amount is a text box, not `st.number_input`** (which is float). `recording.check_payment` parses "6000" / "₹6,000" with `parse_money`; anything else is an `invalid_amount` error, never a traceback.
  - **No double-recording.** After a payment the amount and date widgets get a fresh key (the new payment_id), so they reset to empty / today; a second click has no amount and is refused.
  - **Member labels** come from `recording.member_options` (label → member key): the name, or "Name (MS-…)" when two Members share a name, so labels are unique (Streamlit 1.67 matches selectbox values by label). One-Membership Members see a caption naming the Membership the money goes to.
  - **One clock read**: `now = datetime.now()` in `main`; `today = GYM_TODAY or now.date()`; `now` is the `.bak` stamp and `recorded_at`.
  - **File trouble**: append errors are shown under the amount, prefixed "Nothing was recorded." Excel lock → the same "open in another program" message as elsewhere; a ledger header with an added column (e.g. Notes) now names that column instead of asking to "restore the column order" (`ledger._header_problem`).
- 2026-11-08 (committer): Resolved. Delivered the payment form in app.py (Member select by name via `recording.member_options`; Membership select only when `attribution_required`, preselected to `default_membership`; text amount parsed by `recording.check_payment`; warnings under the date before Record, errors under the amount after; accepted payments built from the raw ledger and appended with `append_payment`, then rerun with a receipt), one clock read (`now`) for today / .bak stamp / recorded_at, `ledger._header_problem` naming added or missing columns, and PermissionError/ValueError on append shown as "Nothing was recorded." Code review (standards + spec) clean. Suite: 717 passed; tester killed 10/10 mutants.
