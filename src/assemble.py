"""Raw rows into the domain (pure core): the parsing boundary is crossed once, here.

Assembly assumes rows that validation has passed; it reports nothing and
guards nothing. What comes out is a Dataset whose objects downstream code can
trust without a single check.
"""

from dataclasses import dataclass
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
__all__ = [
    "member_key", "generate_membership_id", "opening_payment", "build_dataset",
    "LedgerMerge", "with_ledger",
]


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


@dataclass(frozen=True)
class LedgerMerge:
    """The sheet's Dataset with the ledger's Payments added, plus what was left out.

    Left-out Payments are returned, never silently dropped, so the shell can
    tell the owner. `dataset` itself stays orphan-free.
    """

    dataset: Dataset
    orphaned: tuple[Payment, ...]  # name a Membership ID the sheet does not have
    conflicting: tuple[Payment, ...]  # reuse a payment_id with different content


def with_ledger(dataset: Dataset, ledger_payments) -> LedgerMerge:
    """Add the Payment Ledger to a Dataset built from the sheet (pure).

    - An exact copy of a Payment already present (same payment_id, same
      fields) is the same fact twice and is dropped: deterministic
      `OPEN-<membership_id>` ids mean a stray opening copy cannot double-count.
    - A Payment whose payment_id is already taken by different content, or an
      opening Payment the sheet did not produce, is `conflicting`: the sheet
      is the one source of pre-tool money, and of two clashing records
      neither can be trusted to replace the other.
    - A Payment whose membership_id matches no Membership exactly (case
      included) is `orphaned`.

    Left-out Payments are reported rather than raised: one stale row (say,
    after a Membership ID was corrected) must not block the whole dashboard,
    yet counting it would put money against a contract that does not exist.
    """
    membership_ids = {m.membership_id for m in dataset.memberships}
    kept = {p.payment_id: p for p in dataset.payments}
    orphaned: list[Payment] = []
    conflicting: list[Payment] = []
    for payment in ledger_payments:
        if payment.membership_id not in membership_ids:
            orphaned.append(payment)
        elif payment.payment_id in kept:
            if kept[payment.payment_id] != payment:
                conflicting.append(payment)
        elif payment.source == "opening":
            conflicting.append(payment)
        else:
            kept[payment.payment_id] = payment
    merged = Dataset(dataset.members, dataset.memberships, tuple(kept.values()))
    return LedgerMerge(merged, tuple(orphaned), tuple(conflicting))
