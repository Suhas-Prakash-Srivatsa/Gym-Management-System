# Technical plan
Spec: `.scratch/payment-visibility/spec.md`. Vocabulary: `/GLOSSARY.md`.

---

## 1. The paradigms, before any file

Four ideas decide the entire shape of the codebase. Everything below is a consequence of them.

### Functional core, imperative shell

The program is split in two. The **core** is pure functions: given the same inputs they always return the same outputs, they read no files, write no files, know nothing about today's date unless it is handed to them, and never print. The **shell** is the thin outer layer that does the dirty work: reading the upload, appending to a file, drawing a table.

Why this matters here concretely: "is Suhas overdue?" is a pure question about three values (last payment date, grace, today). If that rule lives inside a Streamlit callback, the only way to test it is to run a browser. If it lives in `src/balances.py` as `is_overdue(membership, payments, today)`, it is testable with one line and survives the move to FastAPI untouched. This is ADR 0001 stated as a programming technique rather than a policy.

### Derive, never store

Any value computable from other values is computed on demand, never written down. Outstanding Balance, Last Payment Date, Next Due Date and Overdue are all derived from the Payment Ledger.

Why: a stored copy of a derived value is a second source of truth, and the moment the two disagree the system is lying. The original `Book1.csv` is the proof — its `Pending Amount` column said `0` for members owing ₹6,000, because a human updated the payment and forgot the derived column. Software makes exactly the same mistake, just faster. The only defence that actually works is to have nowhere for the stale value to live.

### Append-only ledger

Money events are facts that happened. Facts are inserted, never updated or deleted. `payments.csv` only ever grows.

Why: it makes the answer to "why does this member owe ₹4,000?" reconstructible — you can read the rows and see. With a mutable `paid_amount` field, a wrong balance is a dead end; there is no history to inspect. This is also what makes the eventual database migration a straight `COPY` into a table rather than a data-modelling exercise.

### Parse, don't validate

Data crosses a boundary once. On the outside of that boundary live `RawRow`s: dicts of strings straight from the CSV, any field possibly missing, malformed or absurd. On the inside live `Member`, `Membership` and `Payment` objects whose very existence guarantees validity — a `Membership` cannot hold a yearless date, because constructing one requires a real `date`.

Why: the alternative is defensive checks scattered everywhere (`if row["amount"]:` in the table renderer, in the tile calculation, in the payment form). Those checks always get missed somewhere. Pushing all conversion into one parsing step means the other 90% of the code can assume valid data without a single guard clause. It also tells us precisely where validation code belongs: at the boundary, nowhere else.

---

## 2. Dependency shape

```
app.py  (shell: Streamlit only)
  │
  ├── views.py ─────────► balances.py ──► dates.py
  │                          │            money.py
  │                          └──► models.py
  ├── recording.py ─────► balances.py
  ├── assemble.py ──────► models.py, money.py, dates.py
  ├── validation.py ────► money.py, dates.py
  ├── sheet.py          (shell: reads bytes)
  ├── ledger.py         (shell: reads/appends payments.csv)
  └── sidecar.py        (shell: paths, members_clean.csv)
```

Arrows point from caller to callee, and there are no cycles. Note what is absent: nothing in the core imports `streamlit`, and nothing in the core opens a file. `sheet.py`, `ledger.py` and `sidecar.py` are the only modules allowed to touch the filesystem, which is also why they are the only ones that need mocking in tests.

Old files `src/loader.py` and `src/analyze.py` are **deleted**, and `src/models.py` is replaced. They encode the flat single-entity model the design has since rejected (`installments: bool`, arithmetic inline in a print loop, a loader that returns `None`); keeping them alongside the new modules would leave two contradictory models in one `src/`.

---

## 3. The files

### `src/models.py` — the vocabulary, as types

The glossary expressed as code. No behaviour, no I/O.

| Definition | Why it exists |
|---|---|
| `MembershipType` (enum: `MONTHLY`, `HALF_YEARLY`, `YEARLY`) with `.months` → 1/6/12 | An open string field lets `"Quarterly"` and `"yearly "` into the system; an enum makes the valid set the type's definition and forces unknown types to fail at the boundary where they can be reported. `.months` is the only place the type→period mapping lives. |
| `Member(member_id, name)` | Identity, nothing else. Holding no money or dates is what lets one Member own two Memberships without duplicating prices. |
| `Membership(membership_id, member_id, type, joined_on, contract_amount, instalments)` | One contract. Frozen, because everything here comes from the sheet and nothing in the program may alter it. Note what is *not* a field: `paid_amount`, `pending_amount`, `next_payment_date` — all derived (§1). |
| `Payment(payment_id, membership_id, amount, paid_on, source, recorded_at)` | One arrival of money. `frozen=True` enforces append-only at the type level: there is no setter to call. `source` (`opening`/`recorded`) keeps the synthesised import balance distinguishable from money the owner actually keyed in — without it, a later bug in import looks identical to a real payment. |
| `Dataset(members, memberships, payments)` | The whole in-memory world after import, passed as one argument. Avoids every function taking three collections and lets callers hold a single immutable snapshot. |
| `MembershipStatus(membership, member, paid, outstanding, last_payment_on, next_due_on, is_overdue)` | The fully-derived view of one Membership — computed once, consumed by tiles, table and payment form. Without it, each consumer recomputes the same four values and they drift apart. |

`contract_amount` and `amount` are `Decimal`, never `float` (see `money.py`).

### `src/money.py` — rupees that add up

- `parse_money(raw: str) -> Decimal` — strips `₹`, commas and spaces; rejects negatives and non-numerics. Why: the sheet is typed by a human, so `"12,000"` and `"₹ 9500"` are normal input, and a bare `Decimal(raw)` raises on both.
- `quantize(d: Decimal) -> Decimal` — two decimal places, `ROUND_HALF_UP`.

Why the module exists at all: `0.1 + 0.2 != 0.3` in binary floating point. With `float`, a ₹12,500 contract split across payments can leave an Outstanding Balance of `0.000000001`, which is `> 0`, which tags a fully-paid member as owing money — and the owner chases a member who paid in full. `Decimal` makes the arithmetic exact. Isolating it in one module means there is one place to check that no `float` ever enters.

### `src/dates.py` — the grace-period calendar

- `add_calendar_months(d: date, months: int) -> date` — clamps to month end: 31 Dec + 2 → 28 Feb (29 in a leap year).
- `parse_date(raw: str) -> date | None` — accepts `2026-06-01`, `01/06/2026`, `1 June 2026`; returns `None` for anything without a year, which is the signal validation turns into a question for the owner.

Why: "two whole calendar months" is not 60 days, and the naïve `month + 2` produces 31 February. There are exactly two date rules in this system and both belong here, where one test file can pin them. `parse_date` returning `None` rather than raising is deliberate — a yearless date is an expected, fixable condition, not an exception.

### `src/balances.py` — the money rules

The heart of the program. Every function is pure, and `today` is always a parameter, never `date.today()`.

- `payments_for(payments, membership_id) -> list[Payment]`
- `total_paid(payments) -> Decimal`
- `outstanding_balance(membership, payments) -> Decimal` — contract − paid, floored at zero
- `last_payment_on(payments) -> date | None`
- `next_due_on(membership, payments) -> date` — `(last payment or joined_on) + 2 months`
- `is_overdue(membership, payments, today) -> bool` — `today > next_due_on` **and** `outstanding > 0`
- `status_for(membership, member, payments, today) -> MembershipStatus`
- `all_statuses(dataset, today) -> list[MembershipStatus]`

Why `today` is injected rather than read: a rule that calls `date.today()` internally can only be tested by waiting, or by monkey-patching the clock. Passing it makes "is this member overdue on 5 Nov vs 8 Nov?" a one-line test — which matters, because Rohit Desai's Membership in the fixture flips exactly at that boundary. This is the single most important testability decision in the codebase.

Why both clauses in `is_overdue`: dropping the `outstanding > 0` clause flags everyone who has ever been late, including members who have since paid in full; dropping the date clause flags every member of a 12-month plan on day one. The spec's rule 5 requires both, and this is where it is enforced once for every consumer.

### `src/sheet.py` — reading the owner's file (shell)

- `HEADER_ALIASES: dict[str, str]` — `{"name": "member_name", "member": "member_name", "joined": "date_joined", …}`
- `normalise_header(raw: str) -> str | None` — lowercase, strip, collapse spaces, look up
- `read_rows(file) -> tuple[list[RawRow], list[str]]` — returns rows plus the canonical columns found

Why aliases: a real gym's sheet says `Name`, not `Member Name`. Demanding our exact headers means every owner re-keys their spreadsheet before the tool runs once, which is where adoption dies. Why `RawRow` is strings-only: this module's job ends at reading; converting here would scatter parsing across two modules and break the single boundary of §1.

### `src/validation.py` — turning bad input into answerable questions

- `Issue(row_number, column, code, message, fix_options)` and `Report(issues, is_fatal)`
- One function per rule, each `(row, row_number) -> list[Issue]`: `check_required_columns`, `check_dates`, `check_membership_type`, `check_instalments`, `check_amounts`, `check_last_payment_date`
- `check_duplicate_names(rows) -> list[Issue]` — operates across rows, not within one
- `validate(rows, columns) -> Report`
- `apply_fixes(rows, fixes) -> list[RawRow]` — pure; returns corrected rows

Why one function per rule: each is independently testable, and new rules are additive rather than edits to a growing `if` chain. Why `Issue` carries `fix_options`: it lets the core *describe* the remedy (`infer_current_year` | `enter_manually`) while `app.py` merely renders buttons for whatever options it is handed — the UI contains no knowledge of what is fixable. Why `apply_fixes` is pure and returns new rows: the correction pipeline becomes `rows → fixes → rows`, testable without a browser, and `sidecar.py` simply persists the result.

Why validation is fatal before any figure is shown: a dashboard built on half-valid rows displays a confidently wrong Total Receivable, which is worse than no dashboard, because the owner acts on it.

### `src/assemble.py` — raw rows into the domain

- `member_key(row) -> str` — `Member ID` when present, else normalised name
- `generate_membership_id(member_key, n) -> str` — `<key>-01`, `-02`
- `opening_payment(membership, row) -> Payment | None` — `None` when `Paid Amount` is 0
- `build_dataset(rows) -> Dataset`

Why this module is separate from `validation.py`: validation answers "is this input usable?", assembly answers "what does it mean?". Fusing them produces a function that both reports errors and constructs objects, which cannot be tested for either cleanly. Why `opening_payment` returns `None` for zero: a ₹0 Payment is not a fact — it never happened — and inserting one would wrongly set a Last Payment Date, resetting the grace clock for a member who has paid nothing. That is precisely the "never paid" case the spec singles out.

Why IDs are generated here rather than in the sheet reader: generation needs the whole set of rows to number a member's second Membership `-02`, which a per-row reader cannot see.

### `src/ledger.py` — the Payment Ledger on disk (shell)

- `read_payments(path) -> list[Payment]`
- `append_payment(path, payment) -> None` — opens in append mode, writes one row, creates the file with a header if absent
- `next_payment_id(existing) -> str`

Why append mode specifically, rather than read-modify-write: it is the mechanical guarantee behind §3. A rewrite-the-whole-file implementation can truncate the ledger on a crash and silently destroy payment history; `"a"` physically cannot touch existing bytes.

### `src/sidecar.py` — where derived files live (shell)

- `payments_path(input_path) -> Path` and `clean_members_path(input_path) -> Path`
- `read_clean_members(path) -> list[RawRow] | None`
- `write_clean_members(path, rows) -> None`
- `resolve_input(input_path) -> tuple[list[RawRow], bool]` — prefers the cleaned sidecar, reports which was used

Why a module for path logic: the rule "sidecars sit next to the input and take precedence on later runs" (ADR 0002) is a real policy, and if it is inlined at three call sites it will be implemented inconsistently at three call sites. Why `resolve_input` reports *which* file it used: the owner must be told they are seeing corrected data, or the cleaned sidecar becomes an invisible second truth.

### `src/recording.py` — the rules for new money

- `attribution_required(dataset, member_id) -> bool` — `True` only when the Member holds more than one Membership
- `default_membership(dataset, member_id, today) -> Membership` — earliest Next Due Date
- `validate_payment(membership, payments, amount, paid_on, today) -> list[Issue]` — rejects `amount > outstanding` with the ceiling in the message, rejects `amount <= 0`, warns on a future `paid_on`
- `build_payment(membership, amount, paid_on, existing) -> Payment`

Why attribution is a core function and not a UI condition: "ask only when the member has several Memberships" is a domain rule (issue `01` exists to revisit it), and a rule buried in an `if` inside `app.py` cannot be revisited — nobody will find it. Why rejection returns `Issue`s rather than raising: the form needs to show the message next to the field, and exceptions are a poor fit for expected user error.

### `src/views.py` — shaping data for the screen

- `tiles(statuses) -> dict` — total members, total membership value, Total Receivable, Overdue
- `receivables_rows(statuses, show_fully_paid=False) -> list[dict]` — filters Outstanding > 0, sorts by Next Due Date ascending, attaches the `DUE` tag
- `format_money(d) -> str` — `₹97,300`

Why a projection layer rather than letting `app.py` sort and filter: the ordering rule ("most overdue first") and the tile definitions are decisions from the spec, not presentation. Keeping them here means the FastAPI migration serialises `tiles()` and `receivables_rows()` straight to JSON and reimplements nothing. `app.py` is left with the genuinely visual part: which widget, what colour.

### `app.py` — the shell

Sequence, and nothing more: upload → `resolve_input` → `validate` → if issues, render them with fix buttons → `apply_fixes` → `write_clean_members` → `build_dataset` → `read_payments` → `all_statuses(dataset, date.today())` → `tiles` + `receivables_rows` → render → payment form → `validate_payment` → `append_payment` → rerun.

`date.today()` is called **here, exactly once**, and passed down. That is the single line of the program that is not a pure function of its inputs, and keeping it in the shell is what makes everything above deterministic.

The constraint from ADR 0001 restated as something checkable in review: `app.py` contains no `+`, `-`, `*`, `/`, no comparison of dates, and no `if` on a business condition. If one appears, the rule it encodes belongs in `src/`.

### `tests/`

`test_dates.py` (month-end clamping, yearless input) · `test_money.py` (`"₹12,000"`, exactness) · `test_balances.py` (the two `is_overdue` clauses, the never-paid anchor, the 5-vs-8 Nov boundary) · `test_validation.py` (each rule against `Book1_errors.csv`) · `test_assemble.py` (renewals produce two Memberships for one Member; zero paid produces no Payment) · `test_recording.py` (over-payment rejected, attribution rule) · `test_ledger.py` (append preserves prior rows) · `test_golden.py`.

`test_golden.py` is the one that matters most: loading `Book1.csv` at a frozen `today` of 2026-11-08 must yield **19 rows** with Outstanding > 0, **11** of them Overdue, Total Receivable **₹97,300**, Overdue **₹60,950**. Hand-calculated from the fixture. A single wrong sign or boundary anywhere in the chain changes one of those four numbers.

---

## 4. Build order

Bottom of the dependency graph upward, so every step is testable when written: `models` + `money` + `dates` → `balances` → `sheet` → `validation` → `assemble` → `ledger` + `sidecar` → `recording` → `views` → `app.py`. Tickets `02`–`13` in `.scratch/payment-visibility/issues/` follow this order and record the blocking relationships.
