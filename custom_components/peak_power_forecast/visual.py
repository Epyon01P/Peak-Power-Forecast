"""Status and color helpers derived from forecast and thresholds."""

from __future__ import annotations

import math

from .const import STATE_CRITICAL, STATE_GOOD, STATE_WARNING

# Gradient anchor colors tuned for LED ring + diffuser visibility
_COLOR_GREEN = "#39FF14"
_COLOR_RED = "#FF4B33"


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


def _hsl_to_hex(h: float, s: float, l: float) -> str:
    """Convert HSL (degrees, 0..1, 0..1) to #RRGGBB."""
    h = ((h % 360) + 360) % 360
    s = max(0.0, min(1.0, s))
    l = max(0.0, min(1.0, l))
    c = (1 - abs(2 * l - 1)) * s
    x = c * (1 - abs((h / 60) % 2 - 1))
    m = l - c / 2
    if h < 60:
        rp, gp, bp = c, x, 0.0
    elif h < 120:
        rp, gp, bp = x, c, 0.0
    elif h < 180:
        rp, gp, bp = 0.0, c, x
    elif h < 240:
        rp, gp, bp = 0.0, x, c
    elif h < 300:
        rp, gp, bp = x, 0.0, c
    else:
        rp, gp, bp = c, 0.0, x
    r = int(round((rp + m) * 255))
    g = int(round((gp + m) * 255))
    b = int(round((bp + m) * 255))
    return f"#{r:02x}{g:02x}{b:02x}"


def forecast_to_color_hex(
    forecast: float,
    *,
    warning: float,
    critical_effective: float,
) -> str:
    """
    Map forecast to a smooth green → orange → red gradient between thresholds.

    - At or below warning: green (clamped).
    - At or above effective critical: red (clamped).
    - Between: interpolate hue from 120° (green) toward 0° (red).
    """
    if critical_effective <= warning:
        return _COLOR_GREEN if forecast < warning else _COLOR_RED

    if forecast <= warning:
        return _COLOR_GREEN
    if forecast >= critical_effective:
        return _COLOR_RED

    span = critical_effective - warning
    t = (forecast - warning) / span
    t = max(0.0, min(1.0, t))
    # Smoothstep for softer transition (no harsh linear banding)
    t_smooth = t * t * (3 - 2 * t)
    hue = 120.0 * (1.0 - t_smooth)
    return _hsl_to_hex(hue, 0.92, 0.44)


def format_optional_float(value: float | None) -> float | None:
    """Return value only if finite and usable as a threshold input."""
    if value is None:
        return None
    if not math.isfinite(value):
        return None
    return value
