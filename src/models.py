"""The domain vocabulary (see GLOSSARY.md) expressed as types.

No behaviour, no I/O, and no derived values stored: Outstanding Balance,
Last Payment Date, Next Due Date and Overdue are computed in balances.py.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Literal

PaymentSource = Literal["opening", "recorded"]


class MembershipType(Enum):
    MONTHLY = "Monthly"
    HALF_YEARLY = "Half-Yearly"
    YEARLY = "Yearly"

    @property
    def months(self) -> int:
        return _MONTHS[self]


_MONTHS = {
    MembershipType.MONTHLY: 1,
    MembershipType.HALF_YEARLY: 6,
    MembershipType.YEARLY: 12,
}


@dataclass(frozen=True)
class Member:
    member_id: str
    name: str


@dataclass(frozen=True)
class Membership:
    membership_id: str
    member_id: str
    type: MembershipType
    joined_on: date
    contract_amount: Decimal
    instalments: int


@dataclass(frozen=True)
class Payment:
    payment_id: str
    membership_id: str
    amount: Decimal
    paid_on: date
    source: PaymentSource
    recorded_at: datetime


@dataclass(frozen=True)
class Dataset:
    members: tuple[Member, ...]
    memberships: tuple[Membership, ...]
    payments: tuple[Payment, ...]


@dataclass(frozen=True)
class MembershipStatus:
    membership: Membership
    member: Member
    paid: Decimal
    outstanding: Decimal
    last_payment_on: date | None
    next_due_on: date
    is_overdue: bool
