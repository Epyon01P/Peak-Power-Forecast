"""Tests for forecast_to_color_hex piecewise RGB gradient."""

from custom_components.peak_power_forecast.visual import forecast_to_color_hex


def test_color_at_zero_is_green() -> None:
    assert (
        forecast_to_color_hex(0.0, warning=3.0, critical_effective=10.0) == "#39FF14"
    )


def test_color_negative_forecast_is_green() -> None:
    assert (
        forecast_to_color_hex(-1.0, warning=3.0, critical_effective=10.0) == "#39FF14"
    )


def test_color_at_warning_is_amber() -> None:
    assert (
        forecast_to_color_hex(3.0, warning=3.0, critical_effective=10.0) == "#FFC400"
    )


def test_color_at_critical_is_red() -> None:
    assert (
        forecast_to_color_hex(10.0, warning=3.0, critical_effective=10.0) == "#FF4B33"
    )


def test_color_mid_first_segment() -> None:
    # Halfway 0 → 3 kW: halfway green → amber (linear RGB)
    c = forecast_to_color_hex(1.5, warning=3.0, critical_effective=10.0)
    assert c == "#9CE20A"


def test_color_just_above_warning_not_green() -> None:
    c = forecast_to_color_hex(3.5, warning=3.0, critical_effective=10.0)
    assert c != "#39FF14"
    assert c.startswith("#")


def test_degenerate_thresholds() -> None:
    assert (
        forecast_to_color_hex(2.0, warning=5.0, critical_effective=5.0) == "#39FF14"
    )
    assert forecast_to_color_hex(5.0, warning=5.0, critical_effective=5.0) == "#FF4B33"
