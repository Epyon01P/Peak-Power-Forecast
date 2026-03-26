"""Pure forecasting helpers used by the coordinator."""

from __future__ import annotations

from datetime import datetime

from .const import ENERGY_UNIT_KWH, ENERGY_UNIT_WH


def detect_reset(previous: float | None, current: float) -> bool:
    """Return True when the source indicates a new meter quarter."""
    if previous is None:
        return False
    return previous > 0 and current < previous


def compute_projected(
    *,
    current_value: float,
    previous_quarter_final: float,
    current_quarter_max: float,
    minutes_elapsed: float,
) -> float:
    """Compute projected end-of-quarter value from current sample."""
    if minutes_elapsed <= 0:
        return round(previous_quarter_final, 3)
    if minutes_elapsed >= 15:
        return round(max(current_value, current_quarter_max), 3)

    raw_projection = current_value * (15 / minutes_elapsed)
    cap_from_previous = previous_quarter_final * 2.0
    cap_from_current = max(current_value * 3.0, current_quarter_max * 2.0, 0.25)
    hard_cap = max(cap_from_previous, cap_from_current)
    projected = min(raw_projection, hard_cap)
    projected = max(projected, current_value, current_quarter_max)
    return round(projected, 3)


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
    if stale:
        return round(
            max(last_good_prediction, current_quarter_max, previous_quarter_final), 3
        )

    ramp = confidence_ramp_minutes if confidence_ramp_minutes > 0 else 5.0
    confidence = min(minutes_elapsed / ramp, 1.0)
    blended = previous_quarter_final * (1 - confidence) + projected * confidence
    return round(max(blended, current_value, current_quarter_max), 3)


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


def cumulative_delta_to_current_avg_kw(delta_kwh: float, minutes_elapsed: float) -> float:
    """Convert quarter energy delta to current quarter-average demand (kW)."""
    if minutes_elapsed <= 0:
        return 0.0
    return delta_kwh / (minutes_elapsed / 60.0)
