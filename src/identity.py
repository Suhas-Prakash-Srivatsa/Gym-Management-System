"""Which rows are Memberships, whose they are, and what they are called (pure core).

The one place the identity scheme lives. Validation uses it to find rows that
would collide; assembly uses it to name what it builds. Both must agree
exactly, or a sheet could validate clean and still assemble two Memberships
under one ID. Depends only on models, so neither caller creates a cycle.
"""

from src.models import RawRow


def _value(row: RawRow, column: str) -> str:
    return (row.get(column) or "").strip()


def is_blank_row(row: RawRow) -> bool:
    """Every cell empty or whitespace, e.g. the `,,,,` lines Excel CSV exports leave.

    Such a row is not a Membership: validation and assembly both skip it.
    """
    return not any((v or "").strip() for v in row.values())


def member_key(row: RawRow) -> str:
    """The row's Member identity: its Member ID, else its normalised name."""
    return _value(row, "member_id") or " ".join(_value(row, "member_name").casefold().split())


def generate_membership_id(member_key: str, n: int) -> str:
    """The n-th (1-based) Membership ID for a Member whose sheet gave none."""
    return f"{member_key}-{n:02d}"


def effective_membership_ids(rows: list[RawRow]) -> list[str | None]:
    """The Membership ID each row will carry once assembled, aligned with `rows`.

    The sheet's ID (stripped) when present; otherwise `<member_key>-NN`, where
    NN numbers that Member's non-blank rows in sheet order (rows with a typed
    ID count too). None for a blank row, which is no Membership.
    """
    seen: dict[str, int] = {}
    ids: list[str | None] = []
    for row in rows:
        if is_blank_row(row):
            ids.append(None)
            continue
        key = member_key(row)
        seen[key] = seen.get(key, 0) + 1
        ids.append(_value(row, "membership_id") or generate_membership_id(key, seen[key]))
    return ids
