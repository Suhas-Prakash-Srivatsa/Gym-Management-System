# Project1

A local tool that reads a gym's existing spreadsheet of members, memberships and payments, shows what money is still owed, and lets the owner record new payments. Its purpose is to help the owner of a service business manage their financial budget by making unpaid money visible.

## Language

### Core entities

**Member**:
A person who trains at the gym. Identity only — a Member holds no prices, dates or balances.
_Avoid_: Customer, user, client

**Membership**:
A single dated contract between a Member and the gym, covering one period for one total amount. A Member may hold several Memberships over time (renewals, lapses); each Membership belongs to exactly one Member.
_Avoid_: Subscription, plan, package

**Membership Type**:
The length of a Membership's period — monthly, half-yearly, or yearly. The type determines the period; it does not change what the amount means.
_Avoid_: Tier, duration, plan

**Contract Amount**:
The total price of a Membership for its entire period, never a per-month rate. A yearly Membership's Contract Amount covers all twelve months.
_Avoid_: Membership amount, fee, price, total

**Payment**:
An immutable record that a sum of money arrived on a date, recorded against exactly one Membership. Payments are appended, never edited.
_Avoid_: Transaction, receipt, instalment

**Payment Ledger**:
The full append-only collection of Payments. It is the only source of truth for how much has been paid; every balance in the tool is computed from it.
_Avoid_: Payment history, log, audit trail

**Opening Balance**:
The Payment created at import from a sheet row's recorded paid amount, dated by its Last Payment Date. It is how money collected before the tool existed enters the Ledger.
_Avoid_: Initial payment, seed, carry-over

### Money and timing

**Instalments**:
The total number of Payments a Membership's Contract Amount is planned to arrive in — a constant of the contract, never a count of what is outstanding. `1` means paid in one shot; the minimum is `1`.
_Avoid_: Payment plan, splits, EMIs, cycles

**Outstanding Balance**:
Contract Amount minus the sum of a Membership's Payments. Always computed, never stored.
_Avoid_: Pending amount, balance due, arrears

**Last Payment Date**:
The date of the most recent Payment against a Membership. On import it comes from the sheet; afterwards it is derived from the Ledger.
_Avoid_: Date of payment, paid on

**Grace Period**:
The fixed span of two whole calendar months allowed after the Last Payment Date before unpaid money counts as Overdue.
_Avoid_: Buffer, leeway, grace days

**Next Due Date**:
Last Payment Date plus the Grace Period, or Date Joined plus the Grace Period for a Membership with no Payments.
_Avoid_: Due date, next payment date

**Overdue**:
The state of a Membership whose Next Due Date has passed while its Outstanding Balance is still above zero. Shown in the dashboard as a red `DUE` tag.
_Avoid_: Flagged, defaulter, late, at-risk

**Total Receivable**:
The sum of Outstanding Balance across every Membership, whether or not it is Overdue yet. The headline figure of the dashboard.
_Avoid_: Total pending, revenue, dues

**Total Membership Value**:
The sum of Contract Amount across every Membership, paid or not. What all the contracts are worth, against which Total Receivable is what is still to come in.
_Avoid_: Revenue, turnover, sales

**Total Members**:
The number of distinct Members holding the Memberships shown. A Member with a renewal counts once.
_Avoid_: Total memberships, headcount, customers

### Explicit non-concepts

These were considered and deliberately left out of the model. Do not reintroduce them without a decision.

- **Overpayment / credit note**: a Payment that would take the Outstanding Balance below zero is rejected. The tool tracks receivables, not accounts.
- **Due This Month**: a monthly breakdown was rejected as misleading; the table ordered by Next Due Date carries that information.
- **Pricing**: discounts for paying a year upfront are the gym's business. The Contract Amount is given to us, never calculated.
