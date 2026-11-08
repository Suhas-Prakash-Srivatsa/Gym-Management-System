from datetime import date, datetime
from decimal import Decimal

from src.balances import (
    all_statuses,
    is_overdue,
    last_payment_on,
    next_due_on,
    outstanding_balance,
    payments_for,
    status_for,
    total_paid,
)
from src.models import Dataset, Member, Membership, MembershipType, Payment

RECORDED_AT = datetime(2026, 11, 8, 9, 0)


def membership(mid="MS-001", joined=date(2026, 6, 1), amount="12000", member_id="M001"):
    return Membership(
        membership_id=mid,
        member_id=member_id,
        type=MembershipType.YEARLY,
        joined_on=joined,
        contract_amount=Decimal(amount),
        instalments=2,
    )


def payment(amount, paid_on, mid="MS-001", pid="P0001"):
    return Payment(
        payment_id=pid,
        membership_id=mid,
        amount=Decimal(amount),
        paid_on=paid_on,
        source="recorded",
        recorded_at=RECORDED_AT,
    )


def test_outstanding_for_never_paid_membership_is_full_contract_amount():
    assert outstanding_balance(membership(amount="12000"), []) == Decimal("12000")


def test_owing_money_inside_grace_window_is_not_overdue():
    ms = membership(amount="12000")
    ledger = [payment("6000", date(2026, 11, 7))]
    assert outstanding_balance(ms, ledger) == Decimal("6000")
    assert not is_overdue(ms, ledger, today=date(2026, 11, 8))


def test_fully_paid_but_historically_late_is_not_overdue():
    ms = membership(joined=date(2026, 1, 1), amount="12000")
    ledger = [
        payment("6000", date(2026, 1, 1), pid="P1"),
        payment("6000", date(2026, 7, 1), pid="P2"),  # months past its due date
    ]
    assert outstanding_balance(ms, ledger) == Decimal("0")
    assert not is_overdue(ms, ledger, today=date(2026, 11, 8))


def test_never_paid_membership_anchors_to_date_joined():
    ms = membership(joined=date(2026, 9, 5), amount="2000")
    assert next_due_on(ms, []) == date(2026, 11, 5)
    assert not is_overdue(ms, [], today=date(2026, 11, 5))
    assert is_overdue(ms, [], today=date(2026, 11, 8))


def test_membership_with_two_payments_anchors_to_the_later_one():
    ms = membership(joined=date(2026, 4, 1), amount="12500")
    ledger = [
        payment("3000", date(2026, 10, 20), pid="P2"),
        payment("3250", date(2026, 4, 1), pid="P1"),
    ]
    assert last_payment_on(ledger) == date(2026, 10, 20)
    assert next_due_on(ms, ledger) == date(2026, 12, 20)
    assert not is_overdue(ms, ledger, today=date(2026, 11, 8))


def test_outstanding_is_floored_at_zero():
    ms = membership(amount="2000")
    assert outstanding_balance(ms, [payment("2500", date(2026, 6, 1))]) == Decimal("0")


def test_other_memberships_payments_are_ignored():
    ms = membership(mid="MS-001", amount="12000")
    ledger = [payment("6000", date(2026, 6, 1), mid="MS-001", pid="P1"),
              payment("2500", date(2026, 10, 20), mid="MS-025", pid="P2")]
    assert payments_for(ledger, "MS-001") == [ledger[0]]
    assert total_paid(payments_for(ledger, "MS-001")) == Decimal("6000")
    assert outstanding_balance(ms, ledger) == Decimal("6000")
    assert next_due_on(ms, ledger) == date(2026, 8, 1)


def test_status_for_derives_every_figure_for_one_membership():
    ms = membership(mid="MS-001", joined=date(2026, 6, 1), amount="12000")
    suhas = Member("M001", "Suhas Prakash")
    ledger = [payment("6000", date(2026, 6, 1), mid="MS-001", pid="P1"),
              payment("2500", date(2026, 10, 20), mid="MS-025", pid="P2")]
    status = status_for(ms, suhas, ledger, today=date(2026, 11, 8))
    assert status.member == suhas
    assert status.paid == Decimal("6000")
    assert status.outstanding == Decimal("6000")
    assert status.last_payment_on == date(2026, 6, 1)
    assert status.next_due_on == date(2026, 8, 1)
    assert status.is_overdue is True


def test_all_statuses_returns_one_status_per_membership_with_its_member():
    suhas = Member("M001", "Suhas Prakash")
    ms1 = membership(mid="MS-001", joined=date(2026, 6, 1), amount="12000")
    ms25 = membership(mid="MS-025", joined=date(2026, 10, 20), amount="2500")
    ledger = (payment("6000", date(2026, 6, 1), mid="MS-001", pid="P1"),
              payment("2500", date(2026, 10, 20), mid="MS-025", pid="P2"))
    statuses = all_statuses(Dataset((suhas,), (ms1, ms25), ledger), today=date(2026, 11, 8))
    assert [(s.membership.membership_id, s.member.name, s.outstanding, s.is_overdue)
            for s in statuses] == [
        ("MS-001", "Suhas Prakash", Decimal("6000"), True),
        ("MS-025", "Suhas Prakash", Decimal("0"), False),
    ]
