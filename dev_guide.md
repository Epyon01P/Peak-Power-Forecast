# Peak Power Forecast – Developer Guide

## Goal

Provide clear, minimal guidance for implementing the **Peak Power Forecast** as a Home Assistant custom integration.

This guide complements `docs/peak_power_forecast_spec.md` (what to build) with **how to structure and implement it**.

---

## High-Level Architecture

Implement as a standard HA custom integration with a config flow and a single data coordinator.

### Domain

```
peak_power_forecast
```

### Files

```
custom_components/peak_power_forecast/
  __init__.py
  manifest.json
  const.py
  config_flow.py
  coordinator.py
  sensor.py
  forecast.py
```

---

## Design Principles

1. **Single source of truth:** All runtime state lives in the coordinator.
2. **Stateful logic:** Do NOT rely on HA template helpers; keep state in Python.
3. **Deterministic updates:** Updates are driven by source sensor state changes.
4. **No race conditions at reset:** Preserve a bridge across reset events.
5. **Graceful degradation:** Handle stale telemetry and zero quarters explicitly.

---

## Entities Exposed

### Required

- `sensor.peak_power_forecast_final`

### Optional (recommended for debugging)

- `sensor.peak_power_forecast_projected_final`

Entities should read values from the coordinator only.

---

## Config Flow

### User input

- `source_sensor` (entity_id)

Constraints:

- must be a sensor
- must have numeric state

Store in config entry:

```python
{
  "source_sensor": "sensor.utility_meter_current_average_demand"
}
```

---

## Coordinator Responsibilities

The coordinator maintains all runtime state and performs updates.

### Internal State

- `previous_quarter_final: float`
- `current_quarter_max: float`
- `last_reset_ts: datetime`
- `last_good_prediction: float`
- `last_source_value: float`
- `last_update_ts: datetime`

---

## Update Trigger

Subscribe to state changes of the `source_sensor`.

On every update:

```python
handle_new_sample(value: float, timestamp: datetime)
```

---

## Core Logic (Order Matters)

### 1. Validate sample

Reject if:

- state is unknown/unavailable
- not numeric

Detect stale if:

```python
now - last_update_ts > 40 seconds
```

---

### 2. Detect reset

Reset occurs when:

```python
value < last_source_value and last_source_value > 0
```

On reset:

```python
previous_quarter_final = current_quarter_max
last_reset_ts = now
current_quarter_max = value  # usually 0
```

IMPORTANT:

- Do NOT zero `current_quarter_max` before copying it.
- This preserves the **handover bridge**.

---

### 3. Update current quarter max

```python
current_quarter_max = max(current_quarter_max, value)
```

---

### 4. Compute elapsed time

```python
minutes_elapsed = clamp((now - last_reset_ts) / 60, 0, 15)
```

---

### 5. Compute projected final

If:

- `minutes_elapsed <= 0`: return `previous_quarter_final`
- `minutes_elapsed >= 15`: return `current_quarter_max`

Else:

```python
raw_projection = value * (15 / minutes_elapsed)
```

Apply caps:

```python
cap_from_previous = previous_quarter_final * 2.0
cap_from_current = max(value * 3.0, current_quarter_max * 2.0, 0.25)
hard_cap = max(cap_from_previous, cap_from_current)
projected = min(raw_projection, hard_cap)
projected = max(projected, value, current_quarter_max)
```

---

### 6. Compute final forecast

If stale:

```python
final = max(last_good_prediction, current_quarter_max, previous_quarter_final)
```

Else:

```python
confidence = min(minutes_elapsed / 5, 1)
blended = previous_quarter_final * (1 - confidence) + projected * confidence
final = max(blended, value, current_quarter_max)
```

---

### 7. Store last good prediction

If not stale:

```python
last_good_prediction = final
```

---

### 8. Zero-quarter fallback

If no reset detected AND:

```python
value == 0 for ~1 full quarter
```

Then force:

```python
previous_quarter_final = 0
current_quarter_max = 0
last_reset_ts = now
```

Implementation suggestion:

- track time since last non-zero value
- trigger fallback after ~15 minutes

---

## forecast.py

Keep forecasting math as pure functions:

- `detect_reset(prev, curr)`
- `compute_projected(...)`
- `compute_final(...)`

This enables:

- unit testing
- easier iteration
- safe refactoring

---

## sensor.py

Each sensor should:

- subscribe to coordinator updates
- expose `native_value`
- no internal logic

---

## const.py

Define:

- domain
- attribute keys
- default thresholds (40s stale, 5 min confidence ramp)

---

## Key Pitfalls to Avoid

### ❌ Using wall-clock quarter boundaries

Always detect resets from the **sensor drop**, not time.

### ❌ Removing current_quarter_max

It is required as a **reset bridge**, even if redundant during normal operation.

### ❌ Letting projected dominate too early

Must be blended with previous quarter early in interval.

### ❌ Ignoring stale telemetry

Must hold `last_good_prediction`.

### ❌ Ignoring zero quarters

Must implement fallback reset logic.

---

## Acceptance Criteria

The implementation is correct if:

1. No dip to zero at quarter boundary.
2. Forecast converges to actual value by end of quarter.
3. Forecast is stable during telemetry dropouts.
4. Forecast drops to zero during long PV-only periods.
5. No race-condition artifacts.

---

## Future Improvements (Optional)

- slope-based estimation using recent samples
- adaptive confidence curve
- diagnostics entity
- debug mode logging

---

## Summary

This system is a **stateful real-time estimator**, not a simple template.

The most important implementation aspects are:

- correct reset detection
- preserving state across resets
- blending past and projected values
- handling edge cases explicitly

If these are preserved, the Python integration will match the working YAML behavior.

