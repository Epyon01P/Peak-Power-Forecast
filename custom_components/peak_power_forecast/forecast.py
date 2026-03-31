"""Pure forecasting helpers used by the coordinator."""

from __future__ import annotations

from datetime import datetime

from .const import (
    ENERGY_UNIT_KWH,
    ENERGY_UNIT_WH,
    POWER_UNIT_KW,
    POWER_UNIT_W,
    QUARTER_MINUTES,
)


def detect_reset(previous: float | None, current: float) -> bool:
    """Return True when the source indicates a new meter quarter."""
    if previous is None:
        return False
    if previous <= 0 or current >= previous:
        return False
    # Direct meter data can decrease intra-quarter (e.g. net injection). Treat a reset
    # only as a hard drop near zero, not any downward step.
    return current <= max(0.05, previous * 0.25)


def compute_projected(
    *,
    current_value: float,
    previous_quarter_final: float,
    current_quarter_max: float,
    minutes_elapsed: float,
    prior_minutes: float | None = None,
    prior_value: float | None = None,
) -> float:
    """Project quarter-end running-average kW from current sample and short trend.

    For a quarter-average demand sensor, the naive constant-continuation estimate is
    the current average itself (not current * 15/t, which mis-scales early in the
    quarter). We add a linear trend from the prior sample in the same quarter:
    projected = current + (remaining_minutes) * slope.
    """
    if minutes_elapsed <= 0:
        return round(max(current_value, 0.0), 3)
    if minutes_elapsed >= QUARTER_MINUTES:
        return round(max(current_value, 0.0), 3)

    remaining = QUARTER_MINUTES - minutes_elapsed
    dt = (
        (minutes_elapsed - prior_minutes)
        if prior_minutes is not None and prior_value is not None
        else 0.0
    )
    if dt <= 1e-6:
        slope = 0.0
    else:
        slope = (current_value - prior_value) / dt

    raw_projection = current_value + remaining * slope

    cap_from_previous = previous_quarter_final * 2.0
    cap_from_current = max(current_value * 3.0, current_quarter_max * 2.0, 0.25)
    hard_cap = max(cap_from_previous, cap_from_current)
    projected = min(raw_projection, hard_cap)
    return round(max(projected, 0.0), 3)


def compute_final(
    *,
    stale: bool,
    minutes_elapsed: float,
    confidence_ramp_minutes: float,
    current_value: float,
    previous_quarter_final: float,
    current_quarter_max: float,
    projected: float,
    last_good_prediction: float,
) -> float:
    """Compute the user-facing final forecast."""
    ramp = confidence_ramp_minutes if confidence_ramp_minutes > 0 else 5.0
    confidence = min(minutes_elapsed / ramp, 1.0)
    blended = previous_quarter_final * (1 - confidence) + projected * confidence
    out = round(max(blended, 0.0), 3)
    # Stale only nudges toward the last reading; do not pin to previous_quarter_final
    # or last_good (that caused post-reset plateaus when the first event after a gap
    # was still marked stale).
    if stale:
        out = round(max(out, current_value), 3)
    return out


def floor_to_quarter(ts: datetime) -> datetime:
    """Return wall-clock quarter boundary for a timestamp."""
    quarter_min = (ts.minute // 15) * 15
    return ts.replace(minute=quarter_min, second=0, microsecond=0)


def energy_to_kwh(value: float, unit: str) -> float:
    """Normalize Wh/kWh values to kWh."""
    if unit == ENERGY_UNIT_KWH:
        return value
    if unit == ENERGY_UNIT_WH:
        return value / 1000.0
    raise ValueError(f"Unsupported energy unit: {unit}")


def power_to_kw(value: float, unit: str) -> float:
    """Normalize W/kW values to kW."""
    if unit == POWER_UNIT_KW:
        return value
    if unit == POWER_UNIT_W:
        return value / 1000.0
    raise ValueError(f"Unsupported power unit: {unit}")


def cumulative_delta_to_current_avg_kw(delta_kwh: float, minutes_elapsed: float) -> float:
    """Convert quarter energy delta to current quarter-average demand (kW)."""
    if minutes_elapsed <= 0:
        return 0.0
    return delta_kwh / (minutes_elapsed / 60.0)
