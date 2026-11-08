# Spec: Payment visibility for service businesses (V1)

Status: ready-for-agent

## Purpose

A gym owner maintains a spreadsheet of members and the money they have paid. Because that sheet is hand-maintained and has no logic in it, the owner cannot reliably answer the only question that matters to their cash flow: **who owes me money, how much, and since when?** Members train for months without paying, and the owner finds out late or never.

This tool reads that spreadsheet and answers that question. It is a budgeting aid for the owner of a service business, not an accounting system.

Vocabulary used below is defined in `/GLOSSARY.md` and is binding.

## Users

- **V1**: a single gym owner, running the tool locally on their own machine from a cloned repository.
- **Explicitly not V1**: multiple gyms, user accounts, authentication, hosting. The architecture must not make these impossible, but no code is written for them.

## The core rules

1. **Contract Amount** is the total price of a Membership for its whole period. It is never a monthly rate and is never calculated by us.
2. **Outstanding Balance** = Contract Amount − sum of that Membership's Payments. Always computed; never stored.
3. **Instalments** is the planned total number of Payments for the contract — a constant, minimum `1`. It is not a countdown and is never decremented.
4. **Next Due Date** = Last Payment Date + 2 whole calendar months; for a Membership with no Payments, Date Joined + 2 months. The Grace Period is fixed at 2 months in V1, with no per-Membership or per-gym override.
5. A Membership is **Overdue** when `today > Next Due Date` **and** `Outstanding Balance > 0`. Both clauses are required: owing money inside the grace window is not Overdue.
6. A Payment that would take Outstanding Balance below zero is **rejected**. Overpayment, credit notes and refunds are out of scope.
7. Every Payment is attributed to exactly one Membership. Attribution is automatic when the Member holds one Membership, and an explicit choice when they hold more than one (default: earliest Next Due Date). See issue `01`.
8. Payments are immutable and append-only. Nothing in the system edits or deletes a Payment.

## Data in

One row per **Membership** (so a renewal is a second row for the same Member).

| Column | Required | Notes |
|---|---|---|
| `Member ID` | optional | Takes precedence over name for identity when present |
| `Member Name` | required | |
| `Membership ID` | optional | Generated as `<MemberKey>-01`, `-02` when absent |
| `Membership Type` | required | `Monthly` \| `Half-Yearly` \| `Yearly` |
| `Date Joined` | required | Must carry a year |
| `Membership Amount` | required | The Contract Amount |
| `Installments` | required | Integer ≥ 1 |
| `Paid Amount` | required | `0` allowed; becomes the Opening Balance Payment |
| `Last Payment Date` | required when `Paid Amount` > 0 | Dates the Opening Balance |

Header matching is case-insensitive and alias-tolerant (`Name`, `Member`, `Joined`, `Amount`, …) so a real gym's sheet loads without re-keying.

**Removed from the old sheet**: `Pending Amount` and `Date of next payment`. Both are derived, and both were already wrong in the original `Book1.csv` (`Pending Amount` read `0` for members owing ₹6,000 and ₹16,000). Displaying the owner's own incorrect figures back to them is the failure this tool exists to prevent.

## Data out

Two sidecar files written next to the input sheet. **The input sheet itself is never written to** (ADR 0002).

- `payments.csv` — append-only Payment Ledger: `payment_id, membership_id, amount, paid_on, source, recorded_at`. `source` distinguishes `opening` (synthesised at import) from `recorded` (entered by the owner).
- `members_clean.csv` — the corrected sheet produced by in-dashboard fixes (years supplied, duplicate names resolved into Member IDs). On later runs it takes precedence over the raw input.

## Validation

Validation runs on upload, before any figure is shown. A sheet with errors produces no dashboard — showing half a dashboard built on bad input is worse than showing none.

Rules, each reported per row with the column named:

| Rule | Resolution |
|---|---|
| Date without a year (`1st June`) | Owner chooses: infer current year, or type the real date |
| `Last Payment Date` missing where `Paid Amount` > 0 | Owner chooses: use Date Joined, or type the real date |
| Duplicate `Member Name` with no `Member ID` | Owner answers: same person (renewal) or two people — written back as generated Member IDs |
| Unrecognised `Membership Type` | Owner corrects |
| `Installments` < 1 or not an integer | Owner corrects |
| `Paid Amount` > `Membership Amount` | Owner corrects |
| Missing required column | Hard stop; nothing is fixable in-dashboard |

The year and duplicate-name questions are the two that **only the owner can answer** — guessing either silently produces a wrong debtor list, so neither is ever defaulted without an explicit click. Corrections are written to `members_clean.csv` so they are answered once, not once per run.

`src/files/Book1_errors.csv` is the fixture carrying one instance of each rule.

## Dashboard

**Tiles**: Total Members · Total Membership Value · Total Receivable · Overdue.

**Table**: one row per Membership with Outstanding Balance > 0, sorted by Next Due Date ascending (most overdue first). Columns: Member Name, Membership ID, Membership Type, Date Joined, Contract Amount, Paid, Outstanding, Last Payment Date, Next Due Date, status tag. Overdue rows carry a red `DUE` tag. A *Show fully paid* toggle reveals settled Memberships.

**Record a payment**: pick Member → (pick Membership only if they hold more than one) → amount + date → appended to `payments.csv`. Rejects amounts above Outstanding Balance with a message naming the ceiling. Back-dated dates allowed; future dates warn.

**No monthly breakdown.** Considered and rejected: a "due this month" figure double-counts against Total Receivable and hides arrears behind a cheerful monthly number. The table sorted by Next Due Date answers the same question truthfully.

## Out of scope for V1

Pricing and discount logic · overpayment, credit notes, refunds · partial-instalment tracking (we track totals and one Next Due Date, not per-instalment expectations) · grace-period overrides · accounts, auth, multi-tenancy · hosting · notifications · editing or deleting Payments · writing to the owner's sheet.

## Architecture constraint

All logic lives in pure functions under `src/`. `app.py` performs no arithmetic and holds no business rule — it uploads, calls, renders, collects. This is ADR 0001 and it is what keeps the eventual FastAPI migration to a presentation-layer rewrite. See `docs/adr/TECHNICAL-PLAN.md` for the file-by-file design.

## Done when

An owner can clone the repo, run one command, upload `src/files/Book1.csv`, see 4 correct tiles and a 19-row receivables table with 11 `DUE` tags, record a payment against Suhas Prakash's second Membership, and see Total Receivable fall by that amount — with their original spreadsheet unmodified.
