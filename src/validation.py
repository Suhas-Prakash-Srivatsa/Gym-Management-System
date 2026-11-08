"""Turning bad input into answerable questions (pure core).

Every rule is one function returning `list[Issue]`. Issues name the row and
column and carry `fix_options` as data, so the UI renders whatever remedies it
is handed and knows nothing about what is fixable.

Row numbers are 1-based positions among the data rows (the header excluded),
i.e. the first member row is row 1.
"""

from dataclasses import dataclass
from decimal import Decimal

from src.dates import parse_date
from src.identity import effective_membership_ids, is_blank_row
from src.models import MembershipType, RawRow
from src.money import parse_money

COLUMN_LABELS = {
    "member_id": "Member ID",
    "member_name": "Member Name",
    "membership_id": "Membership ID",
    "membership_type": "Membership Type",
    "date_joined": "Date Joined",
    "membership_amount": "Membership Amount",
    "instalments": "Installments",
    "paid_amount": "Paid Amount",
    "last_payment_date": "Last Payment Date",
}

# A leap year, so "29 February" counts as a date that only lacks its year.
_PROBE_YEAR = 2000


@dataclass(frozen=True)
class Issue:
    row_number: int | None  # None for sheet-level issues (a missing column)
    column: str
    code: str
    message: str
    fix_options: tuple[str, ...] = ()
    # Every row the issue spans, when it spans more than `row_number` alone
    # (a duplicate name); the answer applies to all of them at once.
    related_rows: tuple[int, ...] = ()


def _value(row: RawRow, column: str) -> str:
    return (row.get(column) or "").strip()


def _label(column: str) -> str:
    return COLUMN_LABELS.get(column, column)


def _with_year(raw: str, year: int) -> str | None:
    """`raw` completed with `year`, as an ISO date, if it is a day-and-month date."""
    for candidate in (f"{raw} {year}", f"{raw}/{year}"):
        parsed = parse_date(candidate)
        if parsed is not None and parsed.year == year:
            return parsed.isoformat()
    return None


def _date_issue(row: RawRow, row_number: int, column: str) -> list[Issue]:
    raw = _value(row, column)
    label = _label(column)
    if not raw:
        return [Issue(row_number, column, "date_missing",
                      f"Row {row_number}: {label} is empty.", ("enter_manually",))]
    if parse_date(raw) is not None:
        return []
    if _with_year(raw, _PROBE_YEAR) is not None:
        return [Issue(row_number, column, "date_missing_year",
                      f"Row {row_number}: {label} '{raw}' has no year.",
                      ("infer_current_year", "enter_manually"))]
    return [Issue(row_number, column, "date_invalid",
                  f"Row {row_number}: {label} '{raw}' is not a date with a 4-digit year "
                  "(use 2026-06-01, 01/06/2026 or 1 June 2026).",
                  ("enter_manually",))]


def check_dates(row: RawRow, row_number: int) -> list[Issue]:
    """Date Joined must be a full date; Last Payment Date too, when present.

    A day-and-month without a year offers `infer_current_year`; anything else
    unreadable (including a 2-digit year) can only be typed in by the owner.
    """
    issues = _date_issue(row, row_number, "date_joined")
    if _value(row, "last_payment_date"):
        issues += _date_issue(row, row_number, "last_payment_date")
    return issues


_TYPE_NAMES = ", ".join(t.value for t in MembershipType)


def check_membership_type(row: RawRow, row_number: int) -> list[Issue]:
    """A type MembershipType.parse recognises (case and separators are tolerated)."""
    raw = _value(row, "membership_type")
    if MembershipType.parse(raw) is not None:
        return []
    return [Issue(row_number, "membership_type", "unknown_membership_type",
                  f"Row {row_number}: Membership Type '{raw}' is not one of {_TYPE_NAMES}.",
                  ("enter_manually",))]


def check_instalments(row: RawRow, row_number: int) -> list[Issue]:
    """A whole number written in ASCII digits, at least 1.

    `str.isdigit` alone is not enough: it accepts "²", which `int` rejects.
    """
    raw = _value(row, "instalments")
    if raw.isascii() and raw.isdigit() and int(raw) >= 1:
        return []
    return [Issue(row_number, "instalments", "invalid_instalments",
                  f"Row {row_number}: Installments '{raw}' must be a whole number of at least 1.",
                  ("enter_manually",))]


def _money(row: RawRow, column: str) -> Decimal | None:
    try:
        return parse_money(_value(row, column))
    except ValueError:
        return None


def check_amounts(row: RawRow, row_number: int) -> list[Issue]:
    """Both amounts readable and non-negative; Paid Amount within the Contract Amount."""
    issues = []
    amounts = {}
    for column in ("membership_amount", "paid_amount"):
        amounts[column] = _money(row, column)
        if amounts[column] is None:
            issues.append(Issue(
                row_number, column, "invalid_amount",
                f"Row {row_number}: {_label(column)} '{_value(row, column)}' "
                "is not an amount of zero or more.",
                ("enter_manually",)))
    contract, paid = amounts["membership_amount"], amounts["paid_amount"]
    if contract is not None and paid is not None and paid > contract:
        issues.append(Issue(
            row_number, "paid_amount", "paid_exceeds_contract",
            f"Row {row_number}: Paid Amount {_value(row, 'paid_amount')} is more than "
            f"the Membership Amount {_value(row, 'membership_amount')}.",
            ("enter_manually",)))
    return issues


def check_last_payment_date(row: RawRow, row_number: int) -> list[Issue]:
    """Money recorded as paid must say when, so the Opening Balance can be dated."""
    paid = _money(row, "paid_amount")
    if paid is None or paid == 0 or _value(row, "last_payment_date"):
        return []
    return [Issue(row_number, "last_payment_date", "last_payment_date_missing",
                  f"Row {row_number}: Paid Amount is {_value(row, 'paid_amount')} "
                  "but Last Payment Date is empty.",
                  ("use_date_joined", "enter_manually"))]


REQUIRED_COLUMNS = (
    "member_name",
    "membership_type",
    "date_joined",
    "membership_amount",
    "instalments",
    "paid_amount",
)


def check_required_columns(columns: list[str]) -> list[Issue]:
    """Sheet-level and fatal: a required column absent, or one column given twice.

    `Last Payment Date` is not required as a column: a sheet where nobody has
    paid yet need not have it, and rows that do need it are caught per row.
    Neither problem can be fixed in the dashboard; the owner edits the sheet.
    """
    issues = [
        Issue(None, c, "missing_column",
              f"The sheet has no {_label(c)} column. Add it to the sheet and upload again.")
        for c in REQUIRED_COLUMNS
        if c not in columns
    ]
    seen = set()
    for c in columns:
        if c in COLUMN_LABELS and c in seen:
            issues.append(Issue(
                None, c, "ambiguous_column",
                f"The sheet has more than one column meaning {_label(c)}. "
                "Keep one, rename or remove the others, and upload again."))
        seen.add(c)
    return issues


def _name_key(name: str) -> str:
    return " ".join(name.casefold().split())


def _ambiguous_name_groups(rows: list[RawRow]) -> dict[str, list[int]]:
    """Row numbers per normalised name, for names on 2+ rows where any row lacks a Member ID.

    A name whose every row carries a Member ID is already resolved by the IDs.
    """
    groups: dict[str, list[int]] = {}
    for n, r in enumerate(rows, start=1):
        if _value(r, "member_name"):
            groups.setdefault(_name_key(_value(r, "member_name")), []).append(n)
    return {
        name: numbers
        for name, numbers in groups.items()
        if len(numbers) > 1 and any(not _value(rows[n - 1], "member_id") for n in numbers)
    }


def _duplicate_options(rows: list[RawRow], numbers: list[int]) -> tuple[str, ...]:
    """Only remedies apply_fixes can honour: rows already carrying two
    different Member IDs cannot be declared one person."""
    ids = {_value(rows[n - 1], "member_id") for n in numbers} - {""}
    return ("different_people",) if len(ids) > 1 else ("same_person", "different_people")


def check_duplicate_names(rows: list[RawRow]) -> list[Issue]:
    """A name repeated where some row has no Member ID: renewal or different people?

    Only the owner knows. One issue per such name, anchored at its first row,
    spanning all of its rows in `related_rows` (including rows that do carry
    an ID). Never defaulted: guessing either way silently produces a wrong
    debtor list.
    """
    issues = []
    for numbers in _ambiguous_name_groups(rows).values():
        name = _value(rows[numbers[0] - 1], "member_name")
        listed = ", ".join(str(n) for n in numbers)
        issues.append(Issue(
            numbers[0], "member_name", "duplicate_name",
            f"Rows {listed} are all named '{name}' and not all have a Member ID. Is this one person "
            "with a renewal, or different people who share a name?",
            _duplicate_options(rows, numbers),
            tuple(numbers)))
    return issues


def check_member_name(row: RawRow, row_number: int) -> list[Issue]:
    if _value(row, "member_name"):
        return []
    return [Issue(row_number, "member_name", "missing_member_name",
                  f"Row {row_number}: Member Name is empty.", ("enter_manually",))]


def check_duplicate_membership_ids(rows: list[RawRow]) -> list[Issue]:
    """Two rows that would assemble under one Membership ID.

    Compares the IDs assembly will actually use (`effective_membership_ids`),
    so a generated `M001-01` colliding with one typed in the sheet is caught
    too. Left unflagged, both rows' Payments would count against each
    contract and the receivable would vanish. One issue per ID, anchored at
    its first row and spanning all of them; the owner types a new ID.
    """
    groups: dict[str, list[int]] = {}
    for n, membership_id in enumerate(effective_membership_ids(rows), start=1):
        if membership_id is not None:
            groups.setdefault(membership_id, []).append(n)
    issues = []
    for membership_id, numbers in groups.items():
        if len(numbers) > 1:
            listed = ", ".join(str(n) for n in numbers)
            issues.append(Issue(
                numbers[0], "membership_id", "duplicate_membership_id",
                f"Rows {listed} would all have Membership ID '{membership_id}'. "
                "Each Membership needs its own ID; enter a different one.",
                ("enter_manually",),
                tuple(numbers)))
    return issues


ROW_RULES = (
    check_member_name,
    check_membership_type,
    check_dates,
    check_amounts,
    check_instalments,
    check_last_payment_date,
)


@dataclass(frozen=True)
class Report:
    issues: tuple[Issue, ...]
    is_fatal: bool  # the sheet itself must be edited; nothing is fixable in-dashboard

    @property
    def is_clean(self) -> bool:
        """Only a clean report may be turned into a dashboard."""
        return not self.issues


def validate(rows: list[RawRow], columns: list[str]) -> Report:
    """Run every rule. Any issue at all means no figures are shown.

    Missing or ambiguous columns stop validation (fatal): row rules would only
    repeat the same problem on every row. Blank rows are skipped but still
    counted, so row numbers match the sheet's data rows.
    """
    sheet_issues = check_required_columns(columns)
    if sheet_issues:
        return Report(tuple(sheet_issues), is_fatal=True)
    issues = []
    for n, r in enumerate(rows, start=1):
        if not is_blank_row(r):
            for rule in ROW_RULES:
                issues += rule(r, n)
    issues += check_duplicate_names(rows)
    issues += check_duplicate_membership_ids(rows)
    return Report(tuple(issues), is_fatal=False)


@dataclass(frozen=True)
class Fix:
    """The owner's answer to one Issue.

    `row_number` and `column` are copied from the Issue being answered;
    `option` is one of that Issue's `fix_options`; `value` is the typed text
    for `enter_manually` and is ignored by every other option.
    """

    row_number: int
    column: str
    option: str
    value: str | None = None


def apply_fixes(
    rows: list[RawRow], fixes: list[Fix], *, current_year: int | None = None
) -> list[RawRow]:
    """Return corrected copies of `rows`; the input is never mutated, nothing is written.

    `current_year` is required only for `infer_current_year`; the caller
    passes it (from the one `date.today()` in app.py), never this module.

    `use_date_joined` fixes run last, so they copy the already-corrected
    Date Joined regardless of the order the answers arrive in.

    `same_person` / `different_people` answer a duplicate-name Issue (its
    `row_number` and `column`). Rows that already carry a Member ID keep it;
    each row lacking one gets: for `same_person`, the group's existing ID (or
    one generated `GEN-001`-style ID if none; conflicting existing IDs raise
    ValueError); for `different_people`, a fresh generated ID per row.
    Generated IDs never collide with an ID already in the sheet.
    """
    fixed = [dict(r) for r in rows]
    new_id = _member_id_generator(rows)
    groups = _ambiguous_name_groups(rows)
    ordered = sorted(fixes, key=lambda f: f.option == "use_date_joined")
    for fix in ordered:
        if not 1 <= fix.row_number <= len(rows):
            raise ValueError(f"No row {fix.row_number} in a sheet of {len(rows)} rows.")
        target = fixed[fix.row_number - 1]
        if fix.option == "infer_current_year":
            if current_year is None:
                raise ValueError("infer_current_year needs current_year.")
            completed = _with_year(_value(target, fix.column), current_year)
            if completed is None:
                raise ValueError(
                    f"Row {fix.row_number}: {_label(fix.column)} "
                    f"'{_value(target, fix.column)}' has no day and month to add a year to.")
            target[fix.column] = completed
        elif fix.option == "enter_manually":
            if fix.value is None:
                raise ValueError(f"Row {fix.row_number}: enter_manually needs a value.")
            target[fix.column] = fix.value
        elif fix.option == "use_date_joined":
            target["last_payment_date"] = target.get("date_joined", "")
        elif fix.option in ("same_person", "different_people"):
            group = _duplicate_group(groups, rows, fix.row_number)
            unidentified = [n for n in group if not _value(rows[n - 1], "member_id")]
            if fix.option == "same_person":
                shared = _shared_member_id(rows, group, fix.row_number) or new_id()
                for n in unidentified:
                    fixed[n - 1]["member_id"] = shared
            else:
                for n in unidentified:
                    fixed[n - 1]["member_id"] = new_id()
        else:
            raise ValueError(f"Unknown fix option {fix.option!r}.")
    return fixed


def _duplicate_group(groups: dict[str, list[int]], rows: list[RawRow], row_number: int) -> list[int]:
    group = groups.get(_name_key(_value(rows[row_number - 1], "member_name")), [])
    if len(group) < 2:
        raise ValueError(f"Row {row_number} is not part of a duplicate name without Member ID.")
    return group


def _shared_member_id(rows: list[RawRow], group: list[int], row_number: int) -> str | None:
    """The one Member ID a same-person group already carries, if any."""
    ids = sorted({_value(rows[n - 1], "member_id") for n in group} - {""})
    if len(ids) > 1:
        raise ValueError(
            f"Row {row_number}: these rows already carry different Member IDs "
            f"({', '.join(ids)}), so they cannot be one person; correct the sheet.")
    return ids[0] if ids else None


def _member_id_generator(rows: list[RawRow]):
    taken = {_value(r, "member_id") for r in rows}
    counter = 0

    def new_id() -> str:
        nonlocal counter
        while True:
            counter += 1
            candidate = f"GEN-{counter:03d}"
            if candidate not in taken:
                return candidate

    return new_id
