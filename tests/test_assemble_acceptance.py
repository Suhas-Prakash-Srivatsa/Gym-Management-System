"""Independent acceptance tests for ticket 06 (assemble), written by the tester.

Expectations are hand-derived from src/files/Book1.csv rather than computed
from the rows, so a reader bug and an assembly bug cannot cancel out.
"""

import ast
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from src.assemble import build_dataset, member_key, opening_payment
from src.balances import all_statuses
from src.models import Dataset, Member, Membership, MembershipType, Payment
from src.sheet import read_rows
from src.validation import validate

ROOT = Path(__file__).resolve().parent.parent
BOOK1 = ROOT / "src" / "files" / "Book1.csv"

# Hand-copied from Book1.csv: membership_id -> (paid, last payment date) for paid > 0.
PAID = {
    "MS-001": ("6000", date(2026, 6, 1)),
    "MS-002": ("8000", date(2026, 8, 5)),
    "MS-003": ("4500", date(2026, 10, 1)),
    "MS-004": ("2000", date(2026, 11, 1)),
    "MS-005": ("12000", date(2026, 3, 10)),
    "MS-006": ("5000", date(2026, 7, 20)),
    "MS-008": ("9000", date(2026, 7, 15)),
    "MS-009": ("11500", date(2026, 1, 5)),
    "MS-010": ("4000", date(2026, 6, 10)),
    "MS-012": ("6250", date(2026, 10, 20)),
    "MS-013": ("8800", date(2026, 6, 12)),
    "MS-014": ("4000", date(2026, 9, 18)),
    "MS-016": ("12000", date(2026, 10, 1)),
    "MS-017": ("3000", date(2026, 7, 5)),
    "MS-018": ("6400", date(2026, 10, 15)),
    "MS-019": ("1000", date(2026, 10, 10)),
    "MS-020": ("4500", date(2026, 2, 20)),
    "MS-021": ("6000", date(2026, 9, 1)),
    "MS-023": ("11000", date(2026, 2, 15)),
    "MS-024": ("4650", date(2026, 8, 15)),
    "MS-025": ("2500", date(2026, 10, 20)),
    "MS-026": ("6000", date(2026, 11, 1)),
}
UNPAID = {"MS-007", "MS-011", "MS-015", "MS-022"}


@pytest.fixture(scope="module")
def sheet():
    return read_rows(BOOK1)


@pytest.fixture(scope="module")
def ds(sheet):
    rows, columns = sheet
    assert validate(rows, columns).is_clean  # assembly is only ever fed clean rows
    return build_dataset(rows)


def base(**kw):
    r = {
        "member_id": "M001", "member_name": "Suhas Prakash", "membership_id": "MS-001",
        "membership_type": "Yearly", "date_joined": "2026-06-01", "membership_amount": "12000",
        "instalments": "2", "paid_amount": "6000", "last_payment_date": "2026-06-01",
    }
    r.update(kw)
    return r


# --- Book1 acceptance -------------------------------------------------------

def test_counts(ds):
    assert isinstance(ds, Dataset)
    assert isinstance(ds.members, tuple) and isinstance(ds.memberships, tuple)
    assert isinstance(ds.payments, tuple)
    assert (len(ds.members), len(ds.memberships), len(ds.payments)) == (24, 26, 22)


def test_member_ids_are_m001_to_m024_once_each(ds):
    assert sorted(m.member_id for m in ds.members) == [f"M{n:03d}" for n in range(1, 25)]


def test_renewal_owners(ds):
    owners = {ms.membership_id: ms.member_id for ms in ds.memberships}
    assert owners["MS-001"] == owners["MS-025"] == "M001"
    assert owners["MS-009"] == owners["MS-026"] == "M009"
    names = {m.member_id: m.name for m in ds.members}
    assert names["M001"] == "Suhas Prakash" and names["M009"] == "Manoj Verma"


def test_sheet_membership_ids_are_used_verbatim(ds):
    assert sorted(ms.membership_id for ms in ds.memberships) == [f"MS-{n:03d}" for n in range(1, 27)]


def test_opening_payments_match_the_sheet_exactly(ds):
    got = {p.membership_id: (p.amount, p.paid_on) for p in ds.payments}
    assert got == {k: (Decimal(a), d) for k, (a, d) in PAID.items()}
    assert not UNPAID & got.keys()


def test_every_payment_is_opening_and_decimal(ds):
    for p in ds.payments:
        assert isinstance(p, Payment)
        assert p.source == "opening"
        assert type(p.amount) is Decimal
    assert len({p.payment_id for p in ds.payments}) == len(ds.payments)


def test_memberships_are_fully_typed(ds):
    ms = {m.membership_id: m for m in ds.memberships}
    assert ms["MS-003"] == Membership("MS-003", "M003", MembershipType.HALF_YEARLY,
                                      date(2026, 9, 15), Decimal("9000"), 2)
    assert ms["MS-007"] == Membership("MS-007", "M007", MembershipType.MONTHLY,
                                      date(2026, 10, 25), Decimal("2200"), 1)
    for m in ds.memberships:
        assert type(m.contract_amount) is Decimal and type(m.instalments) is int
        assert isinstance(m.type, MembershipType)


def test_no_orphans(ds):
    mids = {m.member_id for m in ds.members}
    msids = {ms.membership_id for ms in ds.memberships}
    assert all(ms.member_id in mids for ms in ds.memberships)
    assert all(p.membership_id in msids for p in ds.payments)


def test_unpaid_rows_anchor_on_date_joined_not_a_phantom_payment(ds):
    # MS-022 joined 5 Nov, paid nothing: a ₹0 Payment would give it a Last Payment Date.
    st = {s.membership.membership_id: s for s in all_statuses(ds, date(2026, 11, 8))}
    for unpaid in UNPAID:
        assert st[unpaid].last_payment_on is None
        assert st[unpaid].paid == 0


def test_golden_figures_end_to_end(ds):
    statuses = all_statuses(ds, date(2026, 11, 8))
    owing = [s for s in statuses if s.outstanding > 0]
    overdue = [s for s in owing if s.is_overdue]
    assert (len(owing), len(overdue)) == (19, 11)
    assert sum(s.outstanding for s in owing) == Decimal("97300")
    assert sum(s.outstanding for s in overdue) == Decimal("60950")


# --- Generated Membership IDs ----------------------------------------------

def _drop(rows, column):
    return [{k: v for k, v in r.items() if k != column} for r in rows]


def test_no_membership_id_column_numbers_each_member_in_sheet_order(sheet):
    rows, _ = sheet
    ds = build_dataset(_drop(rows, "membership_id"))
    by_member = {}
    for ms in ds.memberships:
        by_member.setdefault(ms.member_id, []).append(ms.membership_id)
    assert by_member["M001"] == ["M001-01", "M001-02"]
    assert by_member["M009"] == ["M009-01", "M009-02"]
    assert all(v == [f"{k}-01"] for k, v in by_member.items() if k not in ("M001", "M009"))
    # MS-025 (the Oct 2026 monthly renewal) becomes M001-02 and keeps its payment.
    pay = {p.membership_id: p for p in ds.payments}
    assert pay["M001-02"].amount == Decimal("2500")
    assert pay["M001-02"].paid_on == date(2026, 10, 20)
    assert len(ds.payments) == 22


def test_no_membership_id_and_no_member_id_columns(sheet):
    rows, _ = sheet
    ds = build_dataset(_drop(_drop(rows, "membership_id"), "member_id"))
    assert len(ds.members) == 24
    ids = {ms.membership_id for ms in ds.memberships}
    assert {"suhas prakash-01", "suhas prakash-02", "manoj verma-01", "manoj verma-02"} <= ids
    assert len(ids) == 26
    # Name-keyed members still flow through the balance rules (no KeyError).
    assert len(all_statuses(ds, date(2026, 11, 8))) == 26


def test_blank_rows_do_not_consume_a_sequence_number():
    blank = {k: "" for k in base()}
    rows = _drop([base(), blank, base(date_joined="2026-07-01")], "membership_id")
    ds = build_dataset(rows)
    assert [ms.membership_id for ms in ds.memberships] == ["M001-01", "M001-02"]


def test_blank_row_with_none_values_is_skipped():
    # csv.DictReader yields None for short rows; assembly must not choke.
    ds = build_dataset([base(), {k: None for k in base()}])
    assert len(ds.memberships) == 1


def test_counters_are_per_member_not_global():
    rows = _drop([base(), base(member_id="M002", member_name="Vandana Rao"), base()],
                 "membership_id")
    ids = [ms.membership_id for ms in build_dataset(rows).memberships]
    assert ids == ["M001-01", "M002-01", "M001-02"]


# --- Identity ---------------------------------------------------------------

def test_member_id_whitespace_does_not_split_a_member():
    ds = build_dataset([base(member_id=" M001"), base(member_id="M001 ", membership_id="MS-2")])
    assert ds.members == (Member("M001", "Suhas Prakash"),)


def test_member_id_beats_name():
    assert member_key(base(member_id="M777", member_name="Someone Else")) == "M777"
    ds = build_dataset([base(), base(member_name="S. Prakash", membership_id="MS-2")])
    assert len(ds.members) == 1


def test_display_name_is_trimmed_original_not_the_key():
    ds = build_dataset([base(member_id="", member_name="  Suhas  Prakash ")])
    assert ds.members[0].member_id == "suhas prakash"
    assert ds.members[0].name.strip() == ds.members[0].name


def test_membership_id_is_trimmed():
    ds = build_dataset([base(membership_id="  MS-001 ")])
    assert ds.memberships[0].membership_id == "MS-001"
    assert ds.payments[0].membership_id == "MS-001"


# --- Opening payment --------------------------------------------------------

MS = Membership("MS-001", "M001", MembershipType.YEARLY, date(2026, 6, 1), Decimal("12000"), 2)


def test_zero_paid_with_a_stray_date_is_still_no_payment():
    assert opening_payment(MS, base(paid_amount="0", last_payment_date="2026-06-01")) is None
    assert opening_payment(MS, base(paid_amount="₹ 0.00", last_payment_date="2026-06-01")) is None


def test_paise_are_exact():
    p = opening_payment(MS, base(paid_amount="₹6,000.10"))
    assert p.amount == Decimal("6000.10")


def test_opening_payment_points_at_its_membership():
    p = opening_payment(MS, base(membership_id="IGNORED"))
    assert p.membership_id == "MS-001" and p.source == "opening"
    assert p.paid_on == date(2026, 6, 1)


def test_empty_input():
    assert build_dataset([]) == Dataset((), (), ())


# --- Constraints ------------------------------------------------------------

def test_assemble_is_pure():
    src = (ROOT / "src" / "assemble.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
        elif isinstance(node, ast.Call):
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            assert name not in {"open", "today", "now", "float", "utcnow"}, name
        elif isinstance(node, ast.Constant) and isinstance(node.value, float):
            pytest.fail("float literal in assemble.py")
    assert not imported & {"streamlit", "os", "pathlib", "io", "csv", "openpyxl", "random", "uuid"}
    assert "Report" not in src and "Issue(" not in src  # no validation here
