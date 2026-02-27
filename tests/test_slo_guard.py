from __future__ import annotations

from scripts import slo_guard


def test_safe_float_and_int() -> None:
    assert slo_guard._safe_float("1.23") == 1.23
    assert slo_guard._safe_float("x", 2.0) == 2.0
    assert slo_guard._safe_int("7") == 7
    assert slo_guard._safe_int("x", 3) == 3
