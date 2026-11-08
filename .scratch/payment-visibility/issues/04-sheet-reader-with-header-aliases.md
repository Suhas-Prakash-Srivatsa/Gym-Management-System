# Sheet reader with header aliases

Status: ready-for-agent
Blocked by: 02

## Goal

Read the owner's CSV/Excel into `RawRow`s — dicts of strings — without converting or judging anything. Tolerate the header spellings a real gym's sheet actually uses.

## Deliverables

`src/sheet.py`: `HEADER_ALIASES`, `normalise_header`, `read_rows(file) -> (rows, columns)`.

## Acceptance criteria

- Header matching is case-insensitive, whitespace-tolerant, and alias-aware (`Name`/`Member` → `member_name`, `Joined` → `date_joined`, `Amount` → `membership_amount`, …).
- Values are returned as untouched strings. No date parsing, no number parsing, no defaulting here — that belongs to `validation.py` and `assemble.py` (single boundary; see TECHNICAL-PLAN §1).
- Unrecognised columns are preserved but reported, not silently dropped.
- Strips a UTF-8 BOM (the original `Book1.csv` had one on `Member Name`).
- Reads `src/files/Book1.csv` and `src/files/Book1_errors.csv` without raising — including the error fixture, whose whole point is that bad data must reach validation rather than crash the reader.

## Tests

`tests/test_sheet.py`: a sheet headed `name,joined,amount,...` normalises to canonical keys; a BOM-prefixed header still matches; `Book1_errors.csv` yields 6 rows with no exception; the yearless `1st June` arrives as the literal string.
