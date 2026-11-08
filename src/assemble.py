"""Raw rows into the domain (pure core): the parsing boundary is crossed once, here.

Assembly assumes rows that validation has passed; it reports nothing and
guards nothing. What comes out is a Dataset whose objects downstream code can
trust without a single check.
"""

from datetime import datetime, time

from src.dates import parse_date
from src.models import Dataset, Member, Membership, MembershipType, Payment, RawRow
from src.money import parse_money
from src.validation import is_blank_row


def _value(row: RawRow, column: str) -> str:
    return (row.get(column) or "").strip()


def member_key(row: RawRow) -> str:
    """The row's Member identity: its Member ID, else its normalised name."""
    return _value(row, "member_id") or " ".join(_value(row, "member_name").casefold().split())


def generate_membership_id(member_key: str, n: int) -> str:
    """The n-th (1-based) Membership ID for a Member whose sheet gave none."""
    return f"{member_key}-{n:02d}"


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
    A Membership ID missing from the sheet is generated as `<member_key>-NN`,
    numbering that Member's rows in sheet order. Opening Balance Payments are
    added for every row with money already paid.
    """
    members: dict[str, Member] = {}
    memberships: list[Membership] = []
    payments: list[Payment] = []
    seen: dict[str, int] = {}  # member key -> that Member's rows so far
    for row in rows:
        if is_blank_row(row):
            continue
        key = member_key(row)
        members.setdefault(key, Member(member_id=key, name=_value(row, "member_name")))
        seen[key] = seen.get(key, 0) + 1
        membership = Membership(
            membership_id=_value(row, "membership_id") or generate_membership_id(key, seen[key]),
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
