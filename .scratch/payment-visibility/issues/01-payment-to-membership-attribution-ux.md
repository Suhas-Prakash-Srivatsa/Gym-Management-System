# Payment-to-Membership attribution UX

Status: needs-info
Type: grilling

## Question

When the owner records a Payment, it must be attributed to exactly one Membership (balances and Next Due Date are per Membership — see `GLOSSARY.md`). The V1 rule is deliberately minimal:

- Member holds **one** Membership → attribute automatically, ask nothing.
- Member holds **more than one** Membership → require an explicit choice, defaulting to the Membership with the earliest Next Due Date.

This is agreed as good enough to ship, but not believed to be the right long-term interaction. Open until real gym owners have been observed recording payments: do they think in terms of contracts at all, or just "Suhas gave me 3000 today"? If the latter, the model may need an attribution step that is separate from recording, rather than a dropdown at entry time.

Deliberately **not** doing meanwhile: silent arbitrary attribution when a member has several open Memberships. It resets the wrong Next Due Date and makes the `DUE` tag wrong, which defeats the tool's purpose, and an arbitrary choice is indistinguishable from a deliberate one afterwards.

## Comments

- 2026-11-08: Raised during the design grilling session. Blocks nothing in V1; revisit after user feedback.
- 2026-11-08: Spec rule 4 restarts Next Due from the Last Payment Date, so any partial payment (even ₹100 on MS-020's ₹4,500) clears its `DUE` tag and takes its whole Outstanding off the Overdue tile for 2 months. Correct per spec, but a business question for gym owners: should a token payment reset the grace clock? Also, `default_membership` now prefers Memberships with Outstanding > 0 (see ticket 08 Decisions).
