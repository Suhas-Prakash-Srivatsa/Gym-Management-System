from decimal import Decimal

import pytest

from src.money import parse_money, quantize


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("₹12,000", Decimal("12000")),
        ("12,000", Decimal("12000")),
        (" 9500 ", Decimal("9500")),
        ("₹ 9500", Decimal("9500")),
        ("0", Decimal("0")),
        ("12,500.50", Decimal("12500.50")),
    ],
)
def test_parse_money_accepts_human_typed_amounts(raw, expected):
    assert parse_money(raw) == expected


@pytest.mark.parametrize("raw", ["-500", "₹-500", "abc", "", "12.5.0", "NaN", "Infinity"])
def test_parse_money_rejects_negatives_and_non_numerics(raw):
    with pytest.raises(ValueError):
        parse_money(raw)


def test_repeated_addition_of_parsed_values_stays_exact():
    total = sum((parse_money("0.10") for _ in range(10)), Decimal("0"))
    assert total == Decimal("1.00")
    assert parse_money("12,500") - sum(
        (parse_money(x) for x in ["4,166.67", "4,166.67", "4,166.66"]), Decimal("0")
    ) == Decimal("0")


@pytest.mark.parametrize(
    "value, expected",
    [("2.345", "2.35"), ("2.344", "2.34"), ("100", "100.00"), ("0.005", "0.01")],
)
def test_quantize_rounds_half_up_to_two_places(value, expected):
    assert quantize(Decimal(value)) == Decimal(expected)
    assert str(quantize(Decimal(value))) == expected
