"""Adding a Member from the dashboard (pure core): the form's rules and the row it becomes.

The owner's sheet is never written (ADR 0002). The new Member becomes one more
row after the rows the dashboard already shows, and the shell saves them all
as `members_clean.csv`, the sidecar that already takes precedence over the
sheet. Money paid at sign-up is new money, so it becomes a recorded Payment in
the Payment Ledger (`payments.csv`), never a Paid Amount in the row: the
ledger stays the one source of truth for what was paid, and nothing is counted
twice. Nothing here reads the clock or a file: `today` and `recorded_at` come
from the shell.
"""

import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from itertools import count

from src.identity import (
    effective_membership_ids,
    generate_membership_id,
    member_key,
    next_payment_id,
)
from src.models import MembershipType, Payment, RawRow
from src.money import format_money, is_whole_paise, parse_money, quantize
from src.validation import Issue, is_valid_instalments, validate

MEMBERSHIP_TYPES = tuple(t.value for t in MembershipType)
# Upper bounds that catch a slipped finger, far above any real gym membership.
MAX_AMOUNT = Decimal("10000000")  # ₹1,00,00,000
MAX_INSTALMENTS = 120
MAX_NAME_LENGTH = 100
# What a spreadsheet cell starts with to be run as a formula (CSV injection).
FORMULA_STARTS = ("=", "+", "-", "@")
_NUMBERED = re.compile(r"(.*?)([0-9]+)")


@dataclass(frozen=True)
class NewMember:
    """What the owner typed or picked in the form, untouched."""

    name: str
    membership_type: str | None  # None until the owner chooses one
    joined_on: date | None
    amount_text: str
    instalments_text: str
    paid_text: str = ""  # paid at sign-up; blank means nothing
    paid_on: date | None = None


@dataclass(frozen=True)
class MemberCheck:
    """The form's answer: what is wrong, and when nothing blocks, what to save.

    `rows` is every row the dashboard showed with the new one appended (empty
    while anything blocks), ready for `write_clean_members`. `row` is the new
    row itself. `first_payment` is the money paid at sign-up, if any.
    """

    issues: tuple[Issue, ...]
    rows: tuple[RawRow, ...] = ()
    row: RawRow | None = None
    first_payment: Decimal | None = None
    paid_on: date | None = None

    @property
    def accepted(self) -> bool:
        """True when the member may be added: a row was built and nothing blocks."""
        return self.row is not None and not self.errors

    @property
    def errors(self) -> tuple[Issue, ...]:
        """Blocking issues: nothing may be saved."""
        return tuple(i for i in self.issues if i.blocking)

    @property
    def warnings(self) -> tuple[Issue, ...]:
        """Shown to the owner, but the member may still be added."""
        return tuple(i for i in self.issues if not i.blocking)


def _error(column: str, code: str, message: str) -> Issue:
    return Issue(None, column, code, message)


def _warning(column: str, code: str, message: str) -> Issue:
    return Issue(None, column, code, message, severity="warning")


def _money(text: str, column: str, what: str, issues: list[Issue]) -> Decimal | None:
    """`text` as rupees, or None after adding the reason it is not."""
    typed = text.strip()
    try:
        amount = parse_money(typed)
    except ValueError:
        problem = f"{typed!r} is not an amount. " if typed else ""
        issues.append(_error(column, "invalid_amount",
                             f"{problem}Enter the {what} in rupees, for example 12000 or ₹12,000."))
        return None
    if not is_whole_paise(amount):
        issues.append(_error(column, "invalid_amount",
                             f"{typed} is not an amount in rupees and paise (at most 2 decimals)."))
        return None
    return amount


def _name_key(name: str) -> str:
    """A name as identity.member_key compares it (case and spacing ignored)."""
    return member_key({"member_name": name})


def _same_name(rows: list[RawRow], name: str) -> list[RawRow]:
    return [r for r in rows if _name_key(r.get("member_name") or "") == _name_key(name)]


def _style(typed: Iterable[str]) -> str | None:
    """The commonest prefix among the numbered IDs typed in the sheet (`M` for M001)."""
    prefixes = Counter(m.group(1) for t in typed if (m := _NUMBERED.fullmatch(t.strip())))
    return prefixes.most_common(1)[0][0] if prefixes else None


def _first_free(candidates: Iterable[str], taken: Iterable[str]) -> str:
    """The first candidate not in `taken`, ignoring case (`candidates` must be endless)."""
    used = {t.strip().casefold() for t in taken}
    return next(c for c in candidates if c.casefold() not in used)


def next_id(typed: Iterable[str], taken: Iterable[str], default_prefix: str) -> str:
    """A new ID in the style the sheet already uses, free in `taken` (ignoring case).

    The style is the commonest prefix among the IDs typed in the sheet
    (`M` for M001, `MS-` for MS-001), numbered one above the highest number
    with that prefix and padded to the same width; `default_prefix` and
    three digits when the sheet types none. Case is ignored when checking
    `taken`, so an ID can never differ from an existing one only by case.
    """
    typed = [t.strip() for t in typed]
    prefix = _style(typed) or default_prefix
    same = [m.group(2) for t in typed
            if (m := _NUMBERED.fullmatch(t)) and m.group(1) == prefix]
    width = max((len(n) for n in same), default=3)
    start = max((int(n) for n in same), default=0)
    return _first_free((f"{prefix}{n:0{width}d}" for n in count(start + 1)), taken)


def _new_ids(rows: list[RawRow], ledger: Iterable[Payment]) -> tuple[str, str]:
    """A Member ID and a Membership ID that nothing in the sheet or the ledger uses.

    Member IDs are checked against every member key, including names used as
    keys by rows without an ID. Membership IDs are checked against the IDs
    rows will assemble under (generated ones too) and every Membership the
    ledger names, so an old orphaned payment can never attach to the newcomer.

    A sheet whose Membership IDs are a Member ID plus a number (`M001-01`)
    has no gym-wide numbering to continue: copying the commonest prefix
    would file the newcomer under another member (`M001-03`). Such sheets
    get identity's own scheme for the new Member instead (`M003-01`).
    """
    member_ids = [r.get("member_id") or "" for r in rows]
    member_id = next_id(member_ids, (member_key(r) for r in rows), "M")
    typed = [r.get("membership_id") or "" for r in rows]
    taken = [*(i for i in effective_membership_ids(rows) if i),
             *(p.membership_id for p in ledger)]
    prefix = _style(typed)
    owners = {i.strip().casefold() for i in member_ids} - {""}
    if prefix is not None and prefix.rstrip("-_ ").casefold() in owners:
        candidates = (generate_membership_id(member_id, n) for n in count(1))
        return member_id, _first_free(candidates, taken)
    return member_id, next_id(typed, taken, "MS-")


def _plain(amount: Decimal) -> str:
    """12000 rather than 12000.00 or 1.2E+4, for a row the owner may read."""
    return f"{quantize(amount).normalize():f}"


@dataclass(frozen=True)
class _Fields:
    """The form's values as understood; None (or the typed text) where a rule failed."""

    name: str
    kind: MembershipType | None
    joined: date | None
    amount: Decimal | None
    instalments: str
    paid: Decimal | None


def _name_issues(name: str) -> list[Issue]:
    if not name:
        return [_error("name", "missing_member_name", "Enter the member's name.")]
    if len(name) > MAX_NAME_LENGTH:
        return [_error("name", "name_too_long",
                       f"A name can be at most {MAX_NAME_LENGTH} characters.")]
    if name.startswith(FORMULA_STARTS):
        # Excel runs a cell starting with one of these as a formula when the
        # owner opens members_clean.csv; no real name starts that way.
        return [_error("name", "name_looks_like_formula",
                       f"A name cannot start with {', '.join(FORMULA_STARTS)}: a spreadsheet "
                       "would treat it as a formula.")]
    return []


def _field_issues(form: NewMember, today: date) -> tuple[list[Issue], _Fields]:
    """Every rule on the form's own fields, and the values that passed them."""
    name = " ".join(form.name.split())
    issues = _name_issues(name)
    kind = MembershipType.parse(form.membership_type or "")
    if kind is None:
        issues.append(_error("membership_type", "unknown_membership_type",
                             f"Choose the membership type: {', '.join(MEMBERSHIP_TYPES)}."))
    joined = form.joined_on
    if joined is None:
        issues.append(_error("joined_on", "date_missing", "Pick the date the member joined."))
    elif joined > today:
        issues.append(_warning("joined_on", "joined_on_in_future",
                               f"{joined.isoformat()} is in the future. Add the member anyway?"))
    amount = _money(form.amount_text, "amount", "membership amount", issues)
    if amount is not None and amount <= 0:
        issues.append(_error("amount", "amount_not_positive",
                             "Enter a membership amount above ₹0."))
    elif amount is not None and amount > MAX_AMOUNT:
        issues.append(_error("amount", "amount_too_large",
                             f"{format_money(amount)} is more than {format_money(MAX_AMOUNT)}. "
                             "Check for an extra digit."))
    instalments = form.instalments_text.strip()
    if not is_valid_instalments(instalments) or int(instalments) > MAX_INSTALMENTS:
        issues.append(_error("instalments", "invalid_instalments",
                             f"Installments must be a whole number from 1 to {MAX_INSTALMENTS}."))
    paid = (_money(form.paid_text, "paid", "amount paid", issues)
            if form.paid_text.strip() else Decimal(0))
    if paid and amount is not None and paid > amount:
        issues.append(_error("paid", "paid_exceeds_contract",
                             f"{format_money(paid)} paid is more than the membership amount "
                             f"{format_money(amount)}."))
    if paid:
        issues += _paid_on_issues(form.paid_on, joined, today)
    return issues, _Fields(name, kind, joined, amount, instalments, paid)


def _paid_on_issues(paid_on: date | None, joined: date | None, today: date) -> list[Issue]:
    """The same date rules as recording a payment: missing blocks, odd dates only warn."""
    if paid_on is None:
        return [_error("paid_on", "date_missing", "Pick the date the money was paid.")]
    issues = []
    if joined is not None and paid_on < joined:
        issues.append(_warning("paid_on", "paid_before_joining",
                               f"The payment date {paid_on.isoformat()} is before the date "
                               f"joined {joined.isoformat()}. Check the year."))
    if paid_on > today:
        issues.append(_warning("paid_on", "paid_on_in_future",
                               f"{paid_on.isoformat()} is in the future. Record it anyway?"))
    return issues


def _duplicate_warning(rows: list[RawRow], name: str) -> list[Issue]:
    same = _same_name(rows, name)
    if not same:
        return []
    ids = ", ".join(i for i in effective_membership_ids(same) if i)
    return [_warning("name", "duplicate_name",
                     f"There is already a member named {same[0].get('member_name')} ({ids}). "
                     "This adds a different person with the same name. To take money for an "
                     "existing membership, use Record a payment instead.")]


def _sheet_issues(rows: list[RawRow], columns: list[str], name: str) -> list[Issue]:
    """The sheet's own rules on the rows with the new one: anything it now raises blocks.

    The dashboard showed a clean sheet, so any issue touching the new row
    would replace the dashboard with a question; it is refused here instead.
    The one way this can happen is a same-name Member whose rows carry no
    Member ID, which the sheet's duplicate-name rule cannot tell apart.
    """
    report = validate(rows, list(dict.fromkeys([*columns, *rows[-1]])))
    new_row = len(rows)
    touching = [i for i in report.issues if new_row in (i.row_number, *i.related_rows)]
    if any(i.code == "duplicate_name" for i in touching):
        return [_error("name", "duplicate_name_without_id",
                       f"{name} is already in the sheet without a Member ID, so the tool could "
                       "not tell the two people apart. Give that member a Member ID in your "
                       "sheet first, or add this member under a slightly different name "
                       "(for example with an initial).")]
    return [_error("name", i.code, f"This member cannot be added: {i.message}") for i in touching]


def check_new_member(
    rows: list[RawRow], columns: list[str], ledger: Iterable[Payment], form: NewMember,
    today: date,
) -> MemberCheck:
    """Everything wrong with adding `form`, and the row to save when nothing blocks.

    `rows` and `columns` are what the dashboard was built from
    (`resolve_input`), which validated clean. `ledger` is the RAW ledger
    (`read_payments`), so new IDs avoid every Membership it names.

    Errors: no name, one over MAX_NAME_LENGTH, or one starting like a
    spreadsheet formula (= + - @);
    no type chosen; no date joined; a membership amount that is not money,
    not above ₹0 or above MAX_AMOUNT; installments not a whole number from 1
    to MAX_INSTALMENTS; an amount paid that is not money or is more than the
    membership amount; money paid with no date; anything the sheet's own
    rules would then raise about the new row. Warnings (shown, but the
    member may still be added): a date joined or paid in the future, paid
    before joining, and a name another member already has. Never raises for
    anything typed.
    """
    issues, v = _field_issues(form, today)
    ledger = list(ledger)
    if v.name:
        issues += _duplicate_warning(rows, v.name)
    if any(i.blocking for i in issues):
        return MemberCheck(tuple(issues))
    member_id, membership_id = _new_ids(rows, ledger)
    row: RawRow = {
        "member_id": member_id,
        "member_name": v.name,
        "membership_id": membership_id,
        "membership_type": v.kind.value,
        "date_joined": v.joined.isoformat(),
        "membership_amount": _plain(v.amount),
        "instalments": str(int(v.instalments)),
        "paid_amount": "0",  # money paid at sign-up goes to the ledger instead
        "last_payment_date": "",
    }
    new_rows = [*rows, row]
    refused = _sheet_issues(new_rows, columns, v.name)
    if any(i.code == "duplicate_name_without_id" for i in refused):
        issues = [i for i in issues if i.code != "duplicate_name"]  # the error says it all
    issues += refused
    paid = quantize(v.paid) if v.paid else None
    return MemberCheck(tuple(issues), tuple(new_rows), row, paid,
                       form.paid_on if paid else None)


def first_payment(check: MemberCheck, ledger: Iterable[Payment], recorded_at: datetime
                  ) -> Payment | None:
    """The recorded Payment for money paid at sign-up, or None when nothing was paid.

    `ledger` must be the RAW ledger (`read_payments`), as for
    `recording.build_payment`, so the new `P-NNNN` id can never reuse one.
    Raises ValueError for a check that was not accepted (a shell bug).
    """
    if not check.accepted:
        raise ValueError("The new member was not accepted; there is nothing to record.")
    if check.first_payment is None:
        return None
    return Payment(
        payment_id=next_payment_id(ledger),
        membership_id=check.row["membership_id"],
        amount=check.first_payment,
        paid_on=check.paid_on,
        source="recorded",
        recorded_at=recorded_at,
    )
