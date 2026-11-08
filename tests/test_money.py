from decimal import Decimal

import pytest

from src.money import format_money, parse_money, quantize


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


@pytest.mark.parametrize(
    "amount, expected",
    [
        (Decimal("6000"), "₹6,000"),
        (Decimal("97300"), "₹97,300"),
        (Decimal("6000.00"), "₹6,000"),
        (Decimal("6E+3"), "₹6,000"),
        (Decimal("1000.5"), "₹1,000.50"),
        (Decimal("0.10"), "₹0.10"),
        (Decimal("0"), "₹0"),
        (Decimal("1234567.891"), "₹12,34,567.89"),
        (Decimal("999"), "₹999"),
        (Decimal("99999.99"), "₹99,999.99"),
        (Decimal("235400"), "₹2,35,400"),
        (Decimal("100000"), "₹1,00,000"),
        (Decimal("12345678.9"), "₹1,23,45,678.90"),
        (Decimal("1000000000"), "₹1,00,00,00,000"),
    ],
)
def test_format_money_uses_indian_grouping_and_shows_paise_only_when_present(amount, expected):
    assert format_money(amount) == expected
