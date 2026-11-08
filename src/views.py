"""Shaping derived data for the screen (pure core).

Plain dicts of primitives, so a later FastAPI version serialises these same
functions and reimplements nothing. No Streamlit, no markup, no styling, no
clock: the statuses passed in were already computed for the shell's `today`.

Every projection has the same two layers:
- typed values under snake_case keys (int, Decimal, date, None, bool, str),
  for sorting, linking (`member_id`) and serialising;
- a `display` dict of ready-to-show strings, keyed by the on-screen label in
  on-screen order (ROW_COLUMNS, TILE_LABELS).
One `display` dict per projection (rather than a `*_text` twin per field)
lets the shell render a table or tile row by picking a single key, so it
holds no formatting or column-order logic, and the labels live here, once.
"""

from collections.abc import Iterable
from datetime import date
from decimal import Decimal

from src.models import MembershipStatus
from src.money import format_money

__all__ = ["ROW_COLUMNS", "TILE_LABELS", "format_money", "receivables_rows", "tiles"]

TILE_LABELS = ("Total Members", "Total Membership Value", "Total Receivable", "Overdue")

ROW_COLUMNS = (
    "Member Name", "Membership ID", "Membership Type", "Date Joined", "Contract Amount",
    "Paid", "Outstanding", "Last Payment Date", "Next Due Date", "Status",
)

DUE_TAG = "DUE"  # Overdue: Next Due Date passed with money still owed
PAID_TAG = "Paid"  # settled; only shown with show_fully_paid
NO_DATE = "—"


def tiles(statuses: Iterable[MembershipStatus]) -> dict:
    """The four headline figures. Deliberately no "due this month" tile: it
    double-counts against Total Receivable and hides arrears (see spec).

    `total_members` counts distinct Members across the Memberships shown;
    `overdue` is the Outstanding Balance of Overdue Memberships, and
    `overdue_count` how many there are.
    """
    statuses = list(statuses)
    zero = Decimal("0")
    total_members = len({s.member.member_id for s in statuses})
    total_value = sum((s.membership.contract_amount for s in statuses), zero)
    receivable = sum((s.outstanding for s in statuses), zero)
    overdue = [s for s in statuses if s.is_overdue]
    overdue_total = sum((s.outstanding for s in overdue), zero)
    return {
        "total_members": total_members,
        "total_membership_value": total_value,
        "total_receivable": receivable,
        "overdue": overdue_total,
        "overdue_count": len(overdue),
        "display": dict(zip(TILE_LABELS, (
            str(total_members),
            format_money(total_value),
            format_money(receivable),
            format_money(overdue_total),
        ))),
    }


def receivables_rows(
    statuses: Iterable[MembershipStatus], show_fully_paid: bool = False
) -> list[dict]:
    """One row per Membership owing money, most overdue first.

    Sorted by Next Due Date ascending; equal dates keep the order of
    `statuses` (sheet order, from all_statuses). With `show_fully_paid`, the
    settled Memberships follow every unpaid one, ordered the same way.
    `status` is "DUE" when Overdue, "" when owing but not yet Overdue, and
    "Paid" when settled.
    """
    statuses = list(statuses)
    owing = [s for s in statuses if s.outstanding > 0]
    shown = _by_next_due(owing)
    if show_fully_paid:
        shown += _by_next_due([s for s in statuses if s.outstanding == 0])
    return [_row(s) for s in shown]


def _by_next_due(statuses: list[MembershipStatus]) -> list[MembershipStatus]:
    return sorted(statuses, key=lambda s: s.next_due_on)  # sorted() is stable


def _status_tag(s: MembershipStatus) -> str:
    if s.is_overdue:
        return DUE_TAG
    return PAID_TAG if s.outstanding == 0 else ""


def _date_text(d: date | None) -> str:
    return d.isoformat() if d is not None else NO_DATE


def _row(s: MembershipStatus) -> dict:
    ms = s.membership
    status = _status_tag(s)
    return {
        "member_id": s.member.member_id,
        "member_name": s.member.name,
        "membership_id": ms.membership_id,
        "membership_type": ms.type.value,
        "date_joined": ms.joined_on,
        "contract_amount": ms.contract_amount,
        "paid": s.paid,
        "outstanding": s.outstanding,
        "last_payment_date": s.last_payment_on,
        "next_due_date": s.next_due_on,
        "is_overdue": s.is_overdue,
        "status": status,
        "display": dict(zip(ROW_COLUMNS, (
            s.member.name,
            ms.membership_id,
            ms.type.value,
            _date_text(ms.joined_on),
            format_money(ms.contract_amount),
            format_money(s.paid),
            format_money(s.outstanding),
            _date_text(s.last_payment_on),
            _date_text(s.next_due_on),
            status,
        ))),
    }
