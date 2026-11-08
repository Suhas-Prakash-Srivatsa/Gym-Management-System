"""Acceptance pins for ticket 03 not covered by the coder's tests."""

from pathlib import Path

import pytest

SOURCE = (Path(__file__).resolve().parent.parent / "src" / "balances.py").read_text(encoding="utf-8")


@pytest.mark.parametrize("forbidden", ["date.today", "datetime.now", "open(", "print(", "streamlit", "float"])
def test_balances_is_pure(forbidden):
    assert forbidden not in SOURCE
