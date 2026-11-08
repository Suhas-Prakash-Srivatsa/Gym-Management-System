from datetime import date

import pytest

from src.dates import add_calendar_months, parse_date


@pytest.mark.parametrize(
    "start, months, expected",
    [
        (date(2026, 12, 31), 2, date(2027, 2, 28)),
        (date(2027, 12, 31), 2, date(2028, 2, 29)),
        (date(2026, 6, 1), 2, date(2026, 8, 1)),
        (date(2026, 8, 31), 1, date(2026, 9, 30)),
        (date(2026, 11, 15), 2, date(2027, 1, 15)),
        (date(2026, 1, 31), 12, date(2027, 1, 31)),
    ],
)
def test_add_calendar_months_clamps_to_month_end(start, months, expected):
    assert add_calendar_months(start, months) == expected


@pytest.mark.parametrize("raw", ["2026-06-01", "01/06/2026", "1 June 2026", " 1 June 2026 ", "1st June 2026"])
def test_parse_date_accepts_supported_formats_as_the_same_date(raw):
    assert parse_date(raw) == date(2026, 6, 1)


@pytest.mark.parametrize("raw", ["1st June", "1 June", "01/06", "", "abc", "2026-02-30"])
def test_parse_date_returns_none_for_yearless_or_invalid_input(raw):
    assert parse_date(raw) is None


@pytest.mark.parametrize("raw", ["01/06/26", "26-06-01", "1 June 26", "01/06/026", "0026-06-01"])
def test_parse_date_returns_none_for_short_years_rather_than_guessing_a_century(raw):
    assert parse_date(raw) is None
