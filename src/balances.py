"""The money and timing rules (spec rules 1-5) as pure functions.

Nothing here reads a file, prints, or asks the clock: `today` is always passed in.
Functions taking a Membership plus `payments` accept the whole ledger and
consider only that Membership's Payments.
"""

from collections.abc import Iterable
from datetime import date
from decimal import Decimal

from src.dates import add_calendar_months
from src.models import Dataset, Member, Membership, MembershipStatus, Payment

GRACE_MONTHS = 2


def payments_for(payments: Iterable[Payment], membership_id: str) -> list[Payment]:
    return [p for p in payments if p.membership_id == membership_id]


def total_paid(payments: Iterable[Payment]) -> Decimal:
    return sum((p.amount for p in payments), Decimal("0"))


def outstanding_balance(membership: Membership, payments: Iterable[Payment]) -> Decimal:
    """Contract Amount minus that Membership's Payments, floored at zero."""
    paid = total_paid(payments_for(payments, membership.membership_id))
    return max(membership.contract_amount - paid, Decimal("0"))


def last_payment_on(payments: Iterable[Payment]) -> date | None:
    return max((p.paid_on for p in payments), default=None)


def next_due_on(membership: Membership, payments: Iterable[Payment]) -> date:
    """(Last Payment Date, or Date Joined if never paid) + the Grace Period."""
    anchor = last_payment_on(payments_for(payments, membership.membership_id))
    return add_calendar_months(anchor or membership.joined_on, GRACE_MONTHS)


def is_overdue(membership: Membership, payments: Iterable[Payment], today: date) -> bool:
    """Overdue needs both: the Next Due Date has passed AND money is still owed."""
    payments = list(payments)
    return today > next_due_on(membership, payments) and outstanding_balance(
        membership, payments
    ) > 0


def status_for(
    membership: Membership, member: Member, payments: Iterable[Payment], today: date
) -> MembershipStatus:
    own = payments_for(payments, membership.membership_id)
    return MembershipStatus(
        membership=membership,
        member=member,
        paid=total_paid(own),
        outstanding=outstanding_balance(membership, own),
        last_payment_on=last_payment_on(own),
        next_due_on=next_due_on(membership, own),
        is_overdue=is_overdue(membership, own, today),
    )


def all_statuses(dataset: Dataset, today: date) -> list[MembershipStatus]:
    members = {m.member_id: m for m in dataset.members}
    return [
        status_for(ms, members[ms.member_id], dataset.payments, today)
        for ms in dataset.memberships
    ]
