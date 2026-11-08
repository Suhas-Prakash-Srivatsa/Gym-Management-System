"""Raw rows into the domain (pure core): the parsing boundary is crossed once, here.

Assembly assumes rows that validation has passed; it reports nothing and
guards nothing. What comes out is a Dataset whose objects downstream code can
trust without a single check.
"""

from datetime import datetime, time

from src.dates import parse_date
from src.identity import (
    effective_membership_ids,
    generate_membership_id,
    member_key,
)
from src.models import Dataset, Member, Membership, MembershipType, Payment, RawRow
from src.money import parse_money

# member_key and generate_membership_id live in identity.py (shared with
# validation) and are re-exported here as part of assembly's interface.
__all__ = ["member_key", "generate_membership_id", "opening_payment", "build_dataset"]


def _value(row: RawRow, column: str) -> str:
    return (row.get(column) or "").strip()


def opening_payment(membership: Membership, row: RawRow) -> Payment | None:
    """The Opening Balance Payment for the money the sheet says was already paid.

    None when Paid Amount is 0: a zero Payment never happened, and inventing
    one would set a Last Payment Date and restart the grace clock for a
    Member who has paid nothing.

    The id is derived from the Membership (`OPEN-<membership_id>`) and
    `recorded_at` is midnight of the payment date, so assembly stays pure and
    re-importing the same sheet yields identical Payments.
    """
    amount = parse_money(_value(row, "paid_amount"))
    if amount == 0:
        return None
    paid_on = parse_date(_value(row, "last_payment_date"))
    return Payment(
        payment_id=f"OPEN-{membership.membership_id}",
        membership_id=membership.membership_id,
        amount=amount,
        paid_on=paid_on,
        source="opening",
        recorded_at=datetime.combine(paid_on, time.min),
    )


def build_dataset(rows: list[RawRow]) -> Dataset:
    """Every non-blank row becomes one Membership; rows sharing a member key share one Member.

    Each Member is created from the first row bearing its key, before any of
    its Memberships, so no Membership can name a Member that does not exist.
    A Membership ID missing from the sheet is generated as `<member_key>-NN`
    by `identity.effective_membership_ids`, the scheme validation also checks
    for collisions. Opening Balance Payments are
    added for every row with money already paid.
    """
    members: dict[str, Member] = {}
    memberships: list[Membership] = []
    payments: list[Payment] = []
    for row, membership_id in zip(rows, effective_membership_ids(rows)):
        if membership_id is None:  # a blank row
            continue
        key = member_key(row)
        members.setdefault(key, Member(member_id=key, name=_value(row, "member_name")))
        membership = Membership(
            membership_id=membership_id,
            member_id=key,
            type=MembershipType.parse(_value(row, "membership_type")),
            joined_on=parse_date(_value(row, "date_joined")),
            contract_amount=parse_money(_value(row, "membership_amount")),
            instalments=int(_value(row, "instalments")),
        )
        memberships.append(membership)
        payment = opening_payment(membership, row)
        if payment is not None:
            payments.append(payment)
    return Dataset(tuple(members.values()), tuple(memberships), tuple(payments))
