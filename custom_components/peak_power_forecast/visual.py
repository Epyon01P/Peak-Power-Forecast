"""Status and color helpers derived from forecast and thresholds."""

from __future__ import annotations

import math

from .const import STATE_CRITICAL, STATE_GOOD, STATE_WARNING

# Gradient anchor colors tuned for LED ring + diffuser visibility
_COLOR_GREEN = "#39FF14"
_COLOR_WARNING = "#FFC400"
_COLOR_RED = "#FF4B33"


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.removeprefix("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


_RGB_GREEN = _hex_to_rgb(_COLOR_GREEN)
_RGB_WARNING = _hex_to_rgb(_COLOR_WARNING)
_RGB_RED = _hex_to_rgb(_COLOR_RED)


def _lerp_rgb(
    a: tuple[int, int, int], b: tuple[int, int, int], t: float
) -> str:
    t = max(0.0, min(1.0, t))
    r = int(round(a[0] + (b[0] - a[0]) * t))
    g = int(round(a[1] + (b[1] - a[1]) * t))
    bl = int(round(a[2] + (b[2] - a[2]) * t))
    return f"#{r:02X}{g:02X}{bl:02X}"


def effective_critical_threshold(
    *,
    configured_critical: float,
    monthly_peak_value: float | None,
) -> float:
    """Dynamic critical level: max(configured, monthly peak) when peak is known."""
    if monthly_peak_value is None:
        return configured_critical
    return max(configured_critical, monthly_peak_value)


def forecast_to_status(
    forecast: float,
    *,
    warning: float,
    critical_effective: float,
) -> str:
    """Return Good / Warning / Critical for automation-friendly state."""
    if forecast < warning:
        return STATE_GOOD
    if forecast < critical_effective:
        return STATE_WARNING
    return STATE_CRITICAL


def forecast_to_color_hex(
    forecast: float,
    *,
    warning: float,
    critical_effective: float,
) -> str:
    """
    Map forecast to green → warning amber → red using linear RGB in two segments.

    - [0, warning]: green (#39FF14) to #FFC400 (negative forecast clamps to green).
    - (warning, critical_effective): #FFC400 to red (#FF4B33).
    - At or above effective critical: red.
    """
    if not math.isfinite(forecast):
        return _COLOR_GREEN

    if critical_effective <= warning:
        return _COLOR_GREEN if forecast < warning else _COLOR_RED

    if forecast >= critical_effective:
        return _COLOR_RED

    if forecast <= warning:
        if warning <= 0:
            return _COLOR_WARNING
        t = max(0.0, forecast) / warning
        return _lerp_rgb(_RGB_GREEN, _RGB_WARNING, min(1.0, t))

    span = critical_effective - warning
    t = (forecast - warning) / span
    return _lerp_rgb(_RGB_WARNING, _RGB_RED, max(0.0, min(1.0, t)))


def format_optional_float(value: float | None) -> float | None:
    """Return value only if finite and usable as a threshold input."""
    if value is None:
        return None
    if not math.isfinite(value):
        return None
    return value
