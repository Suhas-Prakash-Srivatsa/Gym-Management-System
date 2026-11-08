from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from src.assemble import (
    LedgerMerge,
    build_dataset,
    generate_membership_id,
    member_key,
    opening_payment,
    with_ledger,
)
from src.models import Member, Membership, MembershipType, Payment
from src.sheet import read_rows

FILES = Path(__file__).resolve().parent.parent / "src" / "files"


def row(**overrides):
    base = {
        "member_id": "M001",
        "member_name": "Suhas Prakash",
        "membership_id": "MS-001",
        "membership_type": "Yearly",
        "date_joined": "2026-06-01",
        "membership_amount": "12000",
        "instalments": "2",
        "paid_amount": "6000",
        "last_payment_date": "2026-06-01",
    }
    return {**base, **overrides}


def test_member_key_prefers_member_id():
    assert member_key(row(member_id=" M001 ", member_name="Suhas Prakash")) == "M001"


def test_member_key_falls_back_to_normalised_name():
    assert member_key(row(member_id="", member_name="  Suhas   PRAKASH ")) == "suhas prakash"
    assert member_key({"member_name": "Suhas Prakash"}) == "suhas prakash"


def test_generated_membership_id_is_key_plus_two_digit_sequence():
    assert generate_membership_id("M001", 1) == "M001-01"
    assert generate_membership_id("M001", 2) == "M001-02"
    assert generate_membership_id("suhas prakash", 12) == "suhas prakash-12"


MS_001 = Membership("MS-001", "M001", MembershipType.YEARLY, date(2026, 6, 1), Decimal("12000"), 2)


def test_opening_payment_is_the_rows_paid_amount_dated_by_last_payment_date():
    payment = opening_payment(MS_001, row(paid_amount="₹6,000", last_payment_date="15/07/2026"))
    assert payment.membership_id == "MS-001"
    assert payment.amount == Decimal("6000")
    assert isinstance(payment.amount, Decimal)
    assert payment.paid_on == date(2026, 7, 15)
    assert payment.source == "opening"


@pytest.mark.parametrize("paid", ["0", "0.00", "₹0", " 0 "])
def test_no_opening_payment_when_nothing_was_paid(paid):
    assert opening_payment(MS_001, row(paid_amount=paid, last_payment_date="")) is None


def test_opening_payment_is_deterministic():
    # Pure: no clock is read, so the same row always yields the same Payment.
    r = row()
    assert opening_payment(MS_001, r) == opening_payment(MS_001, r)
    assert isinstance(opening_payment(MS_001, r).recorded_at, datetime)


@pytest.fixture(scope="module")
def book1():
    rows, _ = read_rows(FILES / "Book1.csv")
    return build_dataset(rows)


def _owned(dataset, member_id):
    return sorted(m.membership_id for m in dataset.memberships if m.member_id == member_id)


def test_book1_yields_24_members_and_26_memberships(book1):
    assert len(book1.members) == 24
    assert len(book1.memberships) == 26


def test_renewals_share_one_member(book1):
    assert _owned(book1, "M001") == ["MS-001", "MS-025"]
    assert _owned(book1, "M009") == ["MS-009", "MS-026"]
    assert [m.name for m in book1.members if m.member_id == "M001"] == ["Suhas Prakash"]
    assert [m.name for m in book1.members if m.member_id == "M009"] == ["Manoj Verma"]


def test_zero_paid_rows_produce_no_payment(book1):
    paid = {p.membership_id for p in book1.payments}
    for unpaid in ("MS-007", "MS-011", "MS-015", "MS-022"):
        assert unpaid not in paid


def test_book1_yields_22_opening_payments_dated_by_last_payment_date(book1):
    rows, _ = read_rows(FILES / "Book1.csv")
    expected = {
        r["membership_id"]: (date.fromisoformat(r["last_payment_date"]), Decimal(r["paid_amount"]))
        for r in rows
        if r["paid_amount"] != "0"
    }
    assert len(book1.payments) == 22
    assert all(p.source == "opening" for p in book1.payments)
    assert {p.membership_id: (p.paid_on, p.amount) for p in book1.payments} == expected
    assert len({p.payment_id for p in book1.payments}) == 22


def test_book1_spot_check_values(book1):
    ms_026 = next(m for m in book1.memberships if m.membership_id == "MS-026")
    assert ms_026 == Membership(
        "MS-026", "M009", MembershipType.YEARLY, date(2026, 11, 1), Decimal("12000"), 2)
    rohit = next(p for p in book1.payments if p.membership_id == "MS-012")
    assert rohit.paid_on == date(2026, 10, 20) and rohit.amount == Decimal("6250")


def test_no_membership_is_orphaned(book1):
    member_ids = {m.member_id for m in book1.members}
    assert all(ms.member_id in member_ids for ms in book1.memberships)
    membership_ids = {ms.membership_id for ms in book1.memberships}
    assert all(p.membership_id in membership_ids for p in book1.payments)


def test_book1_dataset_feeds_the_balance_rules():
    # The golden figures from TECHNICAL-PLAN, end to end from the sheet.
    from src.balances import all_statuses

    rows, _ = read_rows(FILES / "Book1.csv")
    statuses = all_statuses(build_dataset(rows), date(2026, 11, 8))
    owing = [s for s in statuses if s.outstanding > 0]
    overdue = [s for s in owing if s.is_overdue]
    assert (len(owing), len(overdue)) == (19, 11)
    assert sum(s.outstanding for s in owing) == Decimal("97300")
    assert sum(s.outstanding for s in overdue) == Decimal("60950")


def test_blank_rows_are_skipped():
    blank = {k: "" for k in row()}
    dataset = build_dataset([row(), blank, {k: "  " for k in row()}])
    assert len(dataset.memberships) == 1
    assert len(dataset.members) == 1


def test_membership_type_is_parsed_tolerantly():
    dataset = build_dataset([row(membership_type=" half_yearly ")])
    assert dataset.memberships[0].type is MembershipType.HALF_YEARLY


def test_member_without_id_is_keyed_by_name():
    dataset = build_dataset([row(member_id="", membership_id="MS-1"),
                             row(member_id="", member_name="suhas  prakash", membership_id="MS-2")])
    assert dataset.members == (Member("suhas prakash", "Suhas Prakash"),)
    assert {ms.member_id for ms in dataset.memberships} == {"suhas prakash"}


def _without_membership_id(rows):
    return [{k: v for k, v in r.items() if k != "membership_id"} for r in rows]


def test_missing_membership_id_column_generates_suffixes_per_member():
    rows, _ = read_rows(FILES / "Book1.csv")
    dataset = build_dataset(_without_membership_id(rows))
    assert _owned(dataset, "M001") == ["M001-01", "M001-02"]
    assert _owned(dataset, "M009") == ["M009-01", "M009-02"]
    assert _owned(dataset, "M002") == ["M002-01"]
    ids = [ms.membership_id for ms in dataset.memberships]
    assert len(set(ids)) == 26
    # Payments follow the generated ids, not a missing one.
    assert {p.membership_id for p in dataset.payments} <= set(ids)
    renewal = next(ms for ms in dataset.memberships if ms.membership_id == "M001-02")
    assert renewal.joined_on == date(2026, 10, 20)


def test_generated_ids_number_in_sheet_order_for_name_keyed_members():
    rows = _without_membership_id([
        row(member_id="", date_joined="2026-01-01"),
        row(member_id="M002", member_name="Vandana Rao"),
        row(member_id="", date_joined="2026-07-01"),
    ])
    dataset = build_dataset(rows)
    by_id = {ms.membership_id: ms for ms in dataset.memberships}
    assert by_id["suhas prakash-01"].joined_on == date(2026, 1, 1)
    assert by_id["suhas prakash-02"].joined_on == date(2026, 7, 1)
    assert "M002-01" in by_id


def test_empty_membership_id_cell_is_generated_too():
    dataset = build_dataset([row(membership_id="MS-001"), row(membership_id=" ")])
    assert [ms.membership_id for ms in dataset.memberships] == ["MS-001", "M001-02"]


@pytest.mark.parametrize("rows", [
    [row(membership_id="MS-1"), row(membership_id="MS-1")],
    [row(membership_id=""), row(membership_id="M001-01")],
    [row(member_id="", membership_id=""), row(member_id="", membership_id="suhas prakash-01")],
])
def test_colliding_membership_ids_never_reach_assembly_from_a_clean_report(rows):
    from src.validation import validate

    assert not validate(rows, list(row())).is_clean


def test_every_clean_sheet_assembles_unique_membership_and_payment_ids():
    from src.validation import validate

    rows, columns = read_rows(FILES / "Book1.csv")
    for sheet in (rows, _without_membership_id(rows)):
        assert validate(sheet, columns).is_clean
        dataset = build_dataset(sheet)
        ids = [ms.membership_id for ms in dataset.memberships]
        assert len(ids) == len(set(ids)) == 26
        assert len({p.payment_id for p in dataset.payments}) == len(dataset.payments)


def test_validation_and_assembly_share_one_effective_id_scheme():
    from src.identity import effective_membership_ids

    blank = {k: "" for k in row()}
    rows = [row(membership_id=""), blank, row(membership_id="MS-5"), row(membership_id="")]
    assert effective_membership_ids(rows) == ["M001-01", None, "MS-5", "M001-03"]
    assert [ms.membership_id for ms in build_dataset(rows).memberships] == [
        "M001-01", "MS-5", "M001-03"]


# --- Merging the Payment Ledger into the sheet's Dataset ---


def recorded(payment_id, membership_id="MS-001", amount="1000", paid_on=date(2026, 11, 1)):
    return Payment(payment_id, membership_id, Decimal(amount), paid_on, "recorded",
                   datetime(2026, 11, 1, 9, 0))


def _sheet():
    return build_dataset([row(), row(member_id="M002", member_name="Vandana Rao",
                                     membership_id="MS-002", paid_amount="0",
                                     last_payment_date="")])


def test_recorded_payments_join_the_opening_balances():
    dataset = _sheet()
    merge = with_ledger(dataset, [recorded("P-0001"), recorded("P-0002", "MS-002", "500")])
    assert isinstance(merge, LedgerMerge)
    assert [p.payment_id for p in merge.dataset.payments] == ["OPEN-MS-001", "P-0001", "P-0002"]
    assert merge.dataset.members == dataset.members
    assert merge.dataset.memberships == dataset.memberships
    assert merge.orphaned == () and merge.conflicting == ()


def test_an_empty_ledger_leaves_the_dataset_unchanged():
    dataset = _sheet()
    assert with_ledger(dataset, []) == LedgerMerge(dataset, (), ())


def test_a_stray_copy_of_an_opening_payment_is_not_counted_twice():
    dataset = _sheet()
    [opening] = dataset.payments
    merge = with_ledger(dataset, [opening, recorded("P-0001"), recorded("P-0001")])
    assert [p.payment_id for p in merge.dataset.payments] == ["OPEN-MS-001", "P-0001"]
    assert merge.conflicting == ()


def test_the_sheet_wins_over_a_differing_opening_payment_in_the_ledger():
    # The sheet is the one source for pre-tool money: a ledger copy that
    # disagrees with it is reported, never counted.
    dataset = _sheet()
    [opening] = dataset.payments
    stale = Payment(opening.payment_id, "MS-001", Decimal("9000"), opening.paid_on,
                    "opening", opening.recorded_at)
    unknown_opening = Payment("OPEN-MS-002", "MS-002", Decimal("100"), date(2026, 1, 1),
                              "opening", datetime(2026, 1, 1))
    merge = with_ledger(dataset, [stale, unknown_opening])
    assert merge.dataset.payments == (opening,)
    assert merge.conflicting == (stale, unknown_opening)


def test_reused_recorded_payment_id_with_different_content_is_reported_not_counted():
    first, clash = recorded("P-0001"), recorded("P-0001", amount="2500")
    merge = with_ledger(_sheet(), [first, clash])
    assert [p for p in merge.dataset.payments if p.source == "recorded"] == [first]
    assert merge.conflicting == (clash,)


def test_ledger_payments_for_unknown_memberships_are_reported_not_counted_and_never_crash():
    from src.balances import all_statuses

    ghost, wrong_case = recorded("P-0001", "MS-999"), recorded("P-0002", "ms-001")
    merge = with_ledger(_sheet(), [ghost, wrong_case, recorded("P-0003")])
    assert merge.orphaned == (ghost, wrong_case)  # IDs match exactly, case included
    assert [p.payment_id for p in merge.dataset.payments] == ["OPEN-MS-001", "P-0003"]
    statuses = all_statuses(merge.dataset, date(2026, 11, 8))
    assert {s.membership.membership_id: s.paid for s in statuses} == {
        "MS-001": Decimal("7000"), "MS-002": Decimal("0")}


def test_golden_book1_with_an_empty_ledger(tmp_path):
    from src.balances import all_statuses
    from src.ledger import read_payments

    rows, _ = read_rows(FILES / "Book1.csv")
    merge = with_ledger(build_dataset(rows), read_payments(tmp_path / "payments.csv"))
    owing = [s for s in all_statuses(merge.dataset, date(2026, 11, 8)) if s.outstanding > 0]
    assert len(owing) == 19 and sum(s.outstanding for s in owing) == Decimal("97300")
