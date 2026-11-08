"""The rules for new money (pure core): which Membership it belongs to, and whether it is allowed.

These are domain rules, kept here rather than in app.py so they can be found
and revisited (issue 01 questions the attribution rule). Nothing here reads
the clock or a file: `today` and `recorded_at` are passed in by the shell.

`dataset` is always the merged view (`with_ledger(...).dataset`), so every
Payment already counted is seen. Membership and Member IDs match exactly.
"""

from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from src.balances import next_due_on, outstanding_balance
from src.identity import next_payment_id
from src.models import Dataset, Membership, Payment
from src.money import format_money, quantize
from src.validation import Issue


def _memberships_of(dataset: Dataset, member_id: str) -> list[Membership]:
    return [m for m in dataset.memberships if m.member_id == member_id]


def attribution_required(dataset: Dataset, member_id: str) -> bool:
    """Ask the owner which Membership a payment is for only when the Member holds several.

    With one Membership the payment is attributed automatically.
    """
    return len(_memberships_of(dataset, member_id)) > 1


def default_membership(dataset: Dataset, member_id: str, today: date) -> Membership:
    """The Membership a payment form preselects for this Member.

    The one with the earliest Next Due Date among those still owing money;
    if none owe, the earliest overall. A settled contract is skipped because
    any payment against it would be refused as an over-payment. Equal dates
    keep sheet order. `today` is part of the interface for the shell's
    convenience; Next Due Date does not depend on it.

    Raises ValueError when the Member holds no Membership (not a user error:
    the shell only offers Members from the dataset).
    """
    candidates = _memberships_of(dataset, member_id)
    if not candidates:
        raise ValueError(f"Member {member_id!r} holds no Membership.")
    owing = [m for m in candidates if outstanding_balance(m, dataset.payments) > 0]
    # min() keeps the first of equal keys, i.e. sheet order.
    return min(owing or candidates, key=lambda m: next_due_on(m, dataset.payments))


def _whole_paise(amount: Decimal) -> bool:
    """Finite, and exactly representable in rupees and paise.

    Never raises: `quantize` signals InvalidOperation for amounts beyond the
    Decimal context's 28 digits (1E+30), and those are simply not money.
    """
    if not amount.is_finite():
        return False
    try:
        return quantize(amount) == amount
    except InvalidOperation:
        return False


def validate_payment(
    dataset: Dataset, membership: Membership, amount: Decimal, paid_on: date, today: date
) -> list[Issue]:
    """Everything wrong with recording `amount` on `paid_on` against `membership`.

    Returns Issues for the form rather than raising: these are expected user
    errors. `severity="error"` (Issue.blocking) means the payment must not be
    recorded; `"warning"` is shown but the payment may still be built. The
    shell decides only by `blocking`, never by code, so it holds no rules.

    Errors:
    - `invalid_amount`: not finite, finer than a paisa, or too large to
      hold in paise (beyond 28 digits). Rejected rather than rounded:
      silently changing a typed ₹100.005 records money the owner did not
      enter, and a third decimal is almost always a typo. Never raises,
      whatever the Decimal.
    - `amount_not_positive`: zero or less.
    - `exceeds_outstanding`: more than the Outstanding Balance, naming the
      ceiling. Checked against the balance after every counted Payment, so
      two payments can never sum past the Contract Amount.
    Warnings:
    - `paid_before_joining`: before Date Joined. Allowed, because a renewal
      is often paid in advance (Manoj pays MS-026 on 30 Oct; it starts
      1 Nov), but flagged since it may be a wrong year, and an early date
      moves the Next Due Date earlier.
    - `paid_on_in_future`: after `today`. Allowed (the owner may be entering
      a post-dated cheque) but worth a second look. Back-dating is fine.

    Raises ValueError if `membership` is not in `dataset` (a shell bug).
    """
    if membership not in dataset.memberships:
        raise ValueError(f"Membership {membership.membership_id!r} is not in the dataset.")
    member = next(m for m in dataset.members if m.member_id == membership.member_id)
    who = f"{member.name} / {membership.membership_id}"
    issues = []
    if not _whole_paise(amount):
        issues.append(Issue(None, "amount", "invalid_amount",
                            f"{amount} is not an amount in rupees and paise (at most 2 decimals)."))
    elif amount <= 0:
        issues.append(Issue(None, "amount", "amount_not_positive",
                            "Enter an amount above ₹0."))
    else:
        outstanding = outstanding_balance(membership, dataset.payments)
        if amount > outstanding:
            ceiling = format_money(outstanding)
            message = (f"{who} has nothing outstanding." if outstanding == 0 else
                       f"{who} has {ceiling} outstanding — enter {ceiling} or less.")
            issues.append(Issue(None, "amount", "exceeds_outstanding", message))
    if paid_on < membership.joined_on:
        issues.append(Issue(None, "paid_on", "paid_before_joining",
                            f"{who} began on {membership.joined_on.isoformat()}; a payment "
                            f"dated {paid_on.isoformat()} is before that. Check the year.",
                            severity="warning"))
    if paid_on > today:
        issues.append(Issue(None, "paid_on", "paid_on_in_future",
                            f"{paid_on.isoformat()} is in the future. Record it anyway?",
                            severity="warning"))
    return issues


def build_payment(
    membership: Membership,
    amount: Decimal,
    paid_on: date,
    ledger: Iterable[Payment],
    recorded_at: datetime,
) -> Payment:
    """The recorded Payment to append, once `validate_payment` has no blocking issue.

    `ledger` must be the RAW ledger (`read_payments(path)`), never
    `with_ledger(...).dataset.payments`: the merged view drops orphaned and
    conflicting rows whose ids are still taken in the file, so a new id
    computed from it could reuse one. `recorded_at` comes from the shell's
    clock; nothing here reads it.

    The amount is stored to exactly 2 places in plain form (`6000.00`, never
    `6E+3`), which is what the ledger file accepts. Raises ValueError for an
    amount `validate_payment` calls invalid, rather than rounding money away.
    """
    if not _whole_paise(amount):
        raise ValueError(f"Amount {amount} is not a whole number of paise.")
    stored = quantize(amount)
    return Payment(
        payment_id=next_payment_id(ledger),
        membership_id=membership.membership_id,
        amount=stored,
        paid_on=paid_on,
        source="recorded",
        recorded_at=recorded_at,
    )
