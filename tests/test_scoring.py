"""Unit tests for score conversion and risk banding (no model needed)."""
import pytest

import main


@pytest.mark.parametrize(
    "prob,expected",
    [(0.0, 0), (0.5999, 60), (0.294, 29), (0.295, 30), (1.0, 100), (1.0000001, 100), (-1e-9, 0)],
)
def test_to_percent_rounds_and_clamps(prob, expected):
    assert main._to_percent(prob) == expected
