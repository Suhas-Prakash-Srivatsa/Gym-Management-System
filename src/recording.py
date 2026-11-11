"""The rules for new money (pure core): which Membership it belongs to, and whether it is allowed.

These are domain rules, kept here rather than in app.py so they can be found
and revisited (issue 01 questions the attribution rule). Nothing here reads
the clock or a file: `today` and `recorded_at` are passed in by the shell.

`dataset` is always the merged view (`with_ledger(...).dataset`), so every
Payment already counted is seen. Membership and Member IDs match exactly.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from src.balances import next_due_on, outstanding_balance
from src.identity import next_payment_id
from src.models import Dataset, Membership, Payment
from src.money import format_money, is_whole_paise, parse_money, quantize
from src.validation import Issue


def memberships_of(dataset: Dataset, member_id: str) -> list[Membership]:
    """The Member's Memberships, in sheet order (IDs match exactly)."""
    return [m for m in dataset.memberships if m.member_id == member_id]


def attribution_required(dataset: Dataset, member_id: str) -> bool:
    """Ask the owner which Membership a payment is for only when the Member holds several.

    With one Membership the payment is attributed automatically.
    """
    return len(memberships_of(dataset, member_id)) > 1


def member_options(dataset: Dataset) -> dict[str, str]:
    """What the payment form shows for each Member -> that Member's key, in sheet order.

    The name, never the key (a generated key like "suhas prakash" or an
    internal "#2" suffix means nothing to the owner). Two Members who share
    a name are told apart by their Membership IDs, which the dashboard
    table also shows, so every label is unique and maps back to one Member.
    """
    names = [m.name for m in dataset.members]

    def label(member) -> str:
        if names.count(member.name) == 1:
            return member.name
        ids = ", ".join(ms.membership_id for ms in memberships_of(dataset, member.member_id))
        return f"{member.name} ({ids})"
    return {label(m): m.member_id for m in dataset.members}


def membership_options(dataset: Dataset, member_id: str) -> dict[str, str]:
    """Membership ID -> its label in the selector, in sheet order: ID, type, what it still owes."""
    def label(ms: Membership) -> str:
        outstanding = outstanding_balance(ms, dataset.payments)
        owes = f"{format_money(outstanding)} outstanding" if outstanding > 0 else "fully paid"
        return f"{ms.membership_id} · {ms.type.value} · {owes}"
    return {ms.membership_id: label(ms) for ms in memberships_of(dataset, member_id)}


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
    candidates = memberships_of(dataset, member_id)
    if not candidates:
        raise ValueError(f"Member {member_id!r} holds no Membership.")
    owing = [m for m in candidates if outstanding_balance(m, dataset.payments) > 0]
    # min() keeps the first of equal keys, i.e. sheet order.
    return min(owing or candidates, key=lambda m: next_due_on(m, dataset.payments))


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
    who = _who(dataset, membership)
    return _amount_issues(dataset, membership, amount, who) + _date_issues(
        membership, paid_on, today, who)


def _who(dataset: Dataset, membership: Membership) -> str:
    """"Suhas Prakash / MS-001", for messages. ValueError if not in the dataset."""
    if membership not in dataset.memberships:
        raise ValueError(f"Membership {membership.membership_id!r} is not in the dataset.")
    member = next(m for m in dataset.members if m.member_id == membership.member_id)
    return f"{member.name} / {membership.membership_id}"


def _amount_issues(dataset: Dataset, membership: Membership, amount: Decimal, who: str) -> list[Issue]:
    if not is_whole_paise(amount):
        return [Issue(None, "amount", "invalid_amount",
                      f"{amount} is not an amount in rupees and paise (at most 2 decimals).")]
    if amount <= 0:
        return [Issue(None, "amount", "amount_not_positive", "Enter an amount above ₹0.")]
    outstanding = outstanding_balance(membership, dataset.payments)
    if amount > outstanding:
        ceiling = format_money(outstanding)
        message = (f"{who} has nothing outstanding." if outstanding == 0 else
                   f"{who} has {ceiling} outstanding — enter {ceiling} or less.")
        return [Issue(None, "amount", "exceeds_outstanding", message)]
    return []


def _date_issues(membership: Membership, paid_on: date, today: date, who: str) -> list[Issue]:
    issues = []
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
    if not is_whole_paise(amount):
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


@dataclass(frozen=True)
class PaymentCheck:
    """The payment form's answer: the amount as understood, and what is wrong with it.

    `amount` is None when the typed text is not an amount at all.
    """

    amount: Decimal | None
    issues: tuple[Issue, ...]

    @property
    def accepted(self) -> bool:
        """True when the payment may be recorded: an amount, and no blocking issue."""
        return self.amount is not None and not self.errors

    @property
    def errors(self) -> tuple[Issue, ...]:
        """Blocking issues: the payment must not be recorded."""
        return tuple(i for i in self.issues if i.blocking)

    @property
    def warnings(self) -> tuple[Issue, ...]:
        """Shown to the owner, but the payment may still be recorded."""
        return tuple(i for i in self.issues if not i.blocking)


def check_payment(
    dataset: Dataset, membership: Membership, amount_text: str, paid_on: date, today: date
) -> PaymentCheck:
    """Parse the amount as the owner typed it ("6000", "₹6,000"), then `validate_payment`.

    Text that is not an amount (blank, words, a sign, an exponent) is an
    `invalid_amount` error with `amount=None`; the date warnings are still
    reported, so the form can show everything at once. Never raises for
    anything typed.

    One exception: while the form is untouched (no amount typed and the date
    still today, its default) `paid_before_joining` is not reported. A
    Membership that starts in the future would otherwise greet the owner
    with a warning about a payment they have not begun to enter.
    """
    who = _who(dataset, membership)
    dated = _date_issues(membership, paid_on, today, who)
    if not amount_text.strip() and paid_on == today:
        dated = [i for i in dated if i.code != "paid_before_joining"]
    try:
        amount = parse_money(amount_text)
    except ValueError:
        typed = amount_text.strip()
        problem = f"{typed!r} is not an amount. " if typed else ""
        unreadable = Issue(None, "amount", "invalid_amount",
                           f"{problem}Enter rupees, for example 6000 or ₹6,000.")
        return PaymentCheck(None, (unreadable, *dated))
    return PaymentCheck(amount, tuple(_amount_issues(dataset, membership, amount, who) + dated))
