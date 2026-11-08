"""Acceptance pins for ticket 02 not covered by the coder's tests."""

import dataclasses
import typing
from decimal import Decimal
from pathlib import Path

import pytest

from src import models

SRC = Path(__file__).resolve().parent.parent / "src"


@pytest.mark.parametrize("module", ["models.py", "money.py", "dates.py"])
def test_no_float_in_domain_primitive_modules(module):
    assert "float" not in (SRC / module).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "cls, field",
    [
        (models.Membership, "contract_amount"),
        (models.Payment, "amount"),
        (models.MembershipStatus, "paid"),
        (models.MembershipStatus, "outstanding"),
    ],
)
def test_monetary_fields_are_decimal(cls, field):
    assert typing.get_type_hints(cls)[field] is Decimal


@pytest.mark.parametrize(
    "cls",
    [models.Member, models.Membership, models.Payment, models.Dataset, models.MembershipStatus],
)
def test_all_domain_types_are_frozen_dataclasses(cls):
    assert dataclasses.is_dataclass(cls)
    assert cls.__dataclass_params__.frozen


def test_loader_and_analyze_are_deleted():
    assert not (SRC / "loader.py").exists()
    assert not (SRC / "analyze.py").exists()
