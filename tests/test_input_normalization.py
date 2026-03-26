"""Skeleton tests for input normalization helpers."""

from datetime import datetime

from custom_components.peak_power_forecast.forecast import (
    cumulative_delta_to_current_avg_kw,
    energy_to_kwh,
    floor_to_quarter,
)


def test_wh_normalization_to_kwh() -> None:
    assert energy_to_kwh(2500.0, "Wh") == 2.5


def test_kwh_normalization_to_kwh() -> None:
    assert energy_to_kwh(2.5, "kWh") == 2.5


def test_unsupported_unit_rejected() -> None:
    try:
        energy_to_kwh(2.5, "MWh")
    except ValueError:
        pass
    else:
        raise AssertionError("Unsupported unit should raise ValueError")


def test_wall_clock_quarter_flooring() -> None:
    ts = datetime(2026, 3, 26, 14, 22, 11)
    assert floor_to_quarter(ts) == datetime(2026, 3, 26, 14, 15, 0)


def test_cumulative_delta_to_current_avg_kw() -> None:
    # 0.5 kWh in 7.5 minutes equals 4.0 kW average so far
    assert cumulative_delta_to_current_avg_kw(0.5, 7.5) == 4.0
