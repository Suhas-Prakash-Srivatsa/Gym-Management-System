import dataclasses
from datetime import date, datetime
from decimal import Decimal

import pytest

from src.models import Membership, MembershipType, Payment


def _membership():
    return Membership(
        membership_id="MS-001",
        member_id="M001",
        type=MembershipType.YEARLY,
        joined_on=date(2026, 6, 1),
        contract_amount=Decimal("12000"),
        instalments=2,
    )


def _payment():
    return Payment(
        payment_id="P0001",
        membership_id="MS-001",
        amount=Decimal("6000"),
        paid_on=date(2026, 6, 1),
        source="opening",
        recorded_at=datetime(2026, 11, 8, 10, 0),
    )


@pytest.mark.parametrize(
    "kind, months",
    [(MembershipType.MONTHLY, 1), (MembershipType.HALF_YEARLY, 6), (MembershipType.YEARLY, 12)],
)
def test_membership_type_knows_its_period_in_months(kind, months):
    assert kind.months == months


def test_payment_is_immutable():
    with pytest.raises(dataclasses.FrozenInstanceError):
        _payment().amount = Decimal("1")


def test_membership_is_immutable():
    with pytest.raises(dataclasses.FrozenInstanceError):
        _membership().contract_amount = Decimal("1")


def test_membership_stores_no_derived_money_or_dates():
    names = {f.name for f in dataclasses.fields(Membership)}
    assert names.isdisjoint({"paid_amount", "pending_amount", "next_payment_date"})


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Yearly", MembershipType.YEARLY),
        ("yearly", MembershipType.YEARLY),
        (" YEARLY ", MembershipType.YEARLY),
        ("Monthly", MembershipType.MONTHLY),
        ("Half-Yearly", MembershipType.HALF_YEARLY),
        ("Half Yearly", MembershipType.HALF_YEARLY),
        ("half-yearly", MembershipType.HALF_YEARLY),
        ("half_yearly", MembershipType.HALF_YEARLY),
        ("HALF  YEARLY", MembershipType.HALF_YEARLY),
    ],
)
def test_membership_type_parse_tolerates_case_and_separators(raw, expected):
    assert MembershipType.parse(raw) is expected


@pytest.mark.parametrize("raw", ["Quarterly", "", "Annual", "Halfyearly", "year"])
def test_membership_type_parse_rejects_unknown_types(raw):
    assert MembershipType.parse(raw) is None
