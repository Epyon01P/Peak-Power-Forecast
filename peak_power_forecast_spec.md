# Peak Power Forecast – Specification

## Purpose

This document specifies the **Peak Power Forecast** Home Assistant integration (`peak_power_forecast`), which forecasts the **final quarter-hour average demand** used for regional capacity tariffs (e.g. in Flanders, Belgium).

The original working implementation exists as a set of YAML helpers, template sensors, and automations. The goal of this spec is twofold:

1. document the current working YAML-based reference implementation;
2. serve as the basis for the **Peak Power Forecast** custom integration that non-technical users can install easily.

---

## Problem Statement

Home Assistant users in regions with a quarter-hour based capacity tariff often have access to a live sensor that represents the **current quarter-hour average demand so far**.

In this project, that source sensor is:

- `sensor.utility_meter_current_average_demand`

This source sensor has the following behavior:

- it starts at `0` at the beginning of each meter quarter;
- it increases monotonically within the quarter;
- its final value at the end of the quarter is the tariff-relevant quarter average demand;
- it may occasionally become stale due to dongle / telemetry delays;
- a drop in value indicates a new meter quarter has started.

The aim is to build a forecast that estimates the **final value that this sensor will reach at the end of the current quarter**.

---

## Desired User Outcome

The system should provide a forecast sensor that:

- does **not** collapse to zero at the start of each new quarter;
- gives a useful estimate of the final quarter-hour value early in the interval;
- gradually transitions from previous-quarter assumptions to current-quarter information;
- remains robust against reset edge cases;
- remains robust against stale telemetry;
- handles zero-import / full-PV quarters sensibly;
- is usable as an input for Home Assistant automations such as EV charging, battery control, or load shedding.

Primary forecast entity:

- `sensor.peak_power_forecast_final`

Supporting debug/inspection entity:

- `sensor.peak_power_forecast_projected_final`

---

## Core Forecasting Concept

The current working YAML approach is based on these ideas:

1. **Detect real quarter rollovers from the meter sensor itself**, not from Home Assistant wall-clock time.
2. Store the **final value of the previous completed quarter**.
3. Track the **current quarter max** as a handover bridge across reset moments.
4. Estimate a **projected final value** for the ongoing quarter.
5. Blend the projected value with the previous quarter final, with increasing confidence as the quarter progresses.
6. Hold the **last good forecast** during stale telemetry periods.

A key lesson from development was that `peak_power_forecast_current_quarter_max` appears redundant during normal monotonic operation, but is still useful as a **handover bridge** across the reset moment. Removing it reintroduced quarter-boundary dips.

---

## Source Assumptions

### Source sensor

- `sensor.utility_meter_current_average_demand`

### Assumptions about this sensor

- value is monotonic non-decreasing within a quarter;
- reset to a lower value indicates a new quarter;
- telemetry may lag or become stale;
- prolonged zero values can happen during continuous PV injection / full self-supply.

---

## Current Working YAML Reference Implementation

The following sections document the **current working reference implementation**.

## Helpers

### `input_number.yaml`

```yaml
peak_power_forecast_previous_quarter_final:
  name: Peak power forecast: previous quarter final
  min: 0
  max: 30
  step: 0.001
  unit_of_measurement: kW
  mode: box

peak_power_forecast_current_quarter_max:
  name: Peak power forecast: current quarter max
  min: 0
  max: 30
  step: 0.001
  unit_of_measurement: kW
  mode: box

peak_power_forecast_last_good_prediction:
  name: Peak power forecast: last good prediction
  min: 0
  max: 30
  step: 0.001
  unit_of_measurement: kW
  mode: box
```

### `input_datetime.yaml`

```yaml
peak_power_forecast_last_reset:
  name: Peak power forecast: last reset
  has_date: true
  has_time: true
```

---

## Template Sensors

### `template.yaml`

```yaml
- sensor:
    - name: Peak power forecast: minutes elapsed
      unique_id: peak_power_forecast_minutes_elapsed
      unit_of_measurement: min
      state: >
        {% set reset_ts = as_timestamp(states('input_datetime.peak_power_forecast_last_reset'), none) %}
        {% if reset_ts is none %}
          0
        {% else %}
          {% set elapsed = (as_timestamp(now()) - reset_ts) / 60 %}
          {{ [0, [elapsed, 15] | min] | max | round(3) }}
        {% endif %}

    - name: Peak power forecast: projected final
      unique_id: peak_power_forecast_projected_final
      unit_of_measurement: kW
      state: >
        {% set raw_state_obj = states.sensor.utility_meter_current_average_demand %}
        {% set raw_state = states('sensor.utility_meter_current_average_demand') %}
        {% set minutes_elapsed = states('sensor.peak_power_forecast_minutes_elapsed') | float(0) %}
        {% set previous_final = states('input_number.peak_power_forecast_previous_quarter_final') | float(0) %}
        {% set current_quarter_max = states('input_number.peak_power_forecast_current_quarter_max') | float(0) %}

        {% set live_valid =
          raw_state_obj is not none
          and raw_state not in ['unknown', 'unavailable', 'none', '']
          and (as_timestamp(now()) - as_timestamp(raw_state_obj.last_updated, 0) < 40)
        %}

        {% set current_avg = raw_state | float(0) if live_valid else current_quarter_max %}

        {% if minutes_elapsed <= 0 %}
          {{ previous_final | round(3) }}
        {% elif minutes_elapsed >= 15 %}
          {{ [current_avg, current_quarter_max] | max | round(3) }}
        {% else %}
          {% set raw_projection = current_avg * (15 / minutes_elapsed) %}

          {% set cap_from_previous = previous_final * 2.0 %}
          {% set cap_from_current = [current_avg * 3.0, current_quarter_max * 2.0, 0.25] | max %}
          {% set capped_projection = [raw_projection, [cap_from_previous, cap_from_current] | max] | min %}

          {{ [capped_projection, current_avg, current_quarter_max] | max | round(3) }}
        {% endif %}

    - name: Peak power forecast: final
      unique_id: peak_power_forecast_final
      unit_of_measurement: kW
      state: >
        {% set raw_state_obj = states.sensor.utility_meter_current_average_demand %}
        {% set raw_state = states('sensor.utility_meter_current_average_demand') %}
        {% set previous_final = states('input_number.peak_power_forecast_previous_quarter_final') | float(0) %}
        {% set current_quarter_max = states('input_number.peak_power_forecast_current_quarter_max') | float(0) %}
        {% set projected_final = states('sensor.peak_power_forecast_projected_final') | float(0) %}
        {% set last_good = states('input_number.peak_power_forecast_last_good_prediction') | float(0) %}
        {% set minutes_elapsed = states('sensor.peak_power_forecast_minutes_elapsed') | float(0) %}

        {% set live_valid =
          raw_state_obj is not none
          and raw_state not in ['unknown', 'unavailable', 'none', '']
          and (as_timestamp(now()) - as_timestamp(raw_state_obj.last_updated, 0) < 40)
        %}

        {% if not live_valid %}
          {{ [last_good, current_quarter_max, previous_final] | max | round(3) }}
        {% else %}
          {% set current_avg = raw_state | float(0) %}
          {% set confidence = [minutes_elapsed / 5, 1] | min %}
          {% set blended = previous_final * (1 - confidence) + projected_final * confidence %}
          {{ [blended, current_avg, current_quarter_max] | max | round(3) }}
        {% endif %}
```

---

## Automations

### `automations.yaml`

```yaml
- alias: Peak power forecast: track current quarter max
  description: Store the maximum valid current average demand seen in the current quarter
  trigger:
    - platform: state
      entity_id: sensor.utility_meter_current_average_demand

  condition:
    - condition: template
      value_template: >
        {{
          trigger.to_state is not none
          and trigger.to_state.state not in ['unknown', 'unavailable', 'none', '']
        }}

  action:
    - variables:
        new_val: "{{ trigger.to_state.state | float(0) }}"
        old_max: "{{ states('input_number.peak_power_forecast_current_quarter_max') | float(0) }}"
    - service: input_number.set_value
      target:
        entity_id: input_number.peak_power_forecast_current_quarter_max
      data:
        value: "{{ [old_max, new_val] | max }}"

  mode: queued

- alias: Peak power forecast: detect quarter reset
  description: Detect quarter rollover when current average demand drops
  trigger:
    - platform: state
      entity_id: sensor.utility_meter_current_average_demand

  condition:
    - condition: template
      value_template: >
        {{
          trigger.from_state is not none
          and trigger.to_state is not none
          and trigger.from_state.state not in ['unknown', 'unavailable', 'none', '']
          and trigger.to_state.state not in ['unknown', 'unavailable', 'none', '']
        }}

    - condition: template
      value_template: >
        {% set old_val = trigger.from_state.state | float(0) %}
        {% set new_val = trigger.to_state.state | float(0) %}
        {{ old_val > 0 and new_val < old_val }}

  action:
    - service: input_number.set_value
      target:
        entity_id: input_number.peak_power_forecast_previous_quarter_final
      data:
        value: "{{ states('input_number.peak_power_forecast_current_quarter_max') | float(0) }}"

    - service: input_datetime.set_datetime
      target:
        entity_id: input_datetime.peak_power_forecast_last_reset
      data:
        datetime: "{{ now().strftime('%Y-%m-%d %H:%M:%S') }}"

    - delay: "00:00:03"

    - service: input_number.set_value
      target:
        entity_id: input_number.peak_power_forecast_current_quarter_max
      data:
        value: 0

  mode: single

- alias: Peak power forecast: store projected prediction
  description: Store the last good final forecast when telemetry is valid
  trigger:
    - platform: state
      entity_id:
        - sensor.peak_power_forecast_final
        - sensor.utility_meter_current_average_demand

  condition:
    - condition: template
      value_template: >
        {% set raw_state_obj = states.sensor.utility_meter_current_average_demand %}
        {% set raw_state = states('sensor.utility_meter_current_average_demand') %}
        {{
          raw_state_obj is not none
          and raw_state not in ['unknown', 'unavailable', 'none', '']
          and (as_timestamp(now()) - as_timestamp(raw_state_obj.last_updated, 0) < 40)
        }}

  action:
    - service: input_number.set_value
      target:
        entity_id: input_number.peak_power_forecast_last_good_prediction
      data:
        value: "{{ states('sensor.peak_power_forecast_final') | float(0) }}"

  mode: restart

- alias: Peak power forecast: zero-quarter fallback reset
  description: Force quarter reset when current average demand stays zero for a full quarter
  trigger:
    - platform: time_pattern
      minutes: "/15"
      seconds: "5"

  condition:
    - condition: template
      value_template: >
        {{ states('sensor.utility_meter_current_average_demand') | float(0) == 0 }}

  action:
    - service: input_number.set_value
      target:
        entity_id: input_number.peak_power_forecast_previous_quarter_final
      data:
        value: 0

    - service: input_datetime.set_datetime
      target:
        entity_id: input_datetime.peak_power_forecast_last_reset
      data:
        datetime: "{{ now().strftime('%Y-%m-%d %H:%M:%S') }}"

    - service: input_number.set_value
      target:
        entity_id: input_number.peak_power_forecast_current_quarter_max
      data:
        value: 0

  mode: single
```

---

## Behavior Summary

### Normal quarter with positive import

- `current_average_demand` ramps up through the quarter;
- `current_quarter_max` mirrors it and acts as a handover bridge;
- when the meter resets, `previous_quarter_final` is set to the old `current_quarter_max`;
- `minutes_elapsed` restarts from the actual detected reset timestamp;
- `projected_final` estimates the end value of the current quarter;
- `final` blends previous-quarter confidence and current-quarter information.

### Stale telemetry

- if the source sensor becomes stale, `final` holds the `last_good_prediction` rather than collapsing.

### Zero-import / PV-dominated quarters

- if the meter remains zero for a full quarter, the `zero-quarter fallback reset` forces:
  - `previous_quarter_final = 0`
  - `current_quarter_max = 0`
  - `last_reset = now`
- this prevents the previous quarter final from sticking at an old positive value.

---

## Why `current_quarter_max` is kept

Although the live meter sensor is monotonic within a quarter, `current_quarter_max` is retained because it acts as a **handover bridge across the reset moment**.

Without it, a brief quarter-boundary race condition can cause `peak_power_forecast_final` to dip to zero before the reset automation has updated the previous quarter final and reset timestamp.

So while this helper may appear redundant during normal operation, it is still valuable for robustness.

---

## Planned Future Direction

The YAML implementation is the current working reference version.

The intended future direction is a **custom Home Assistant integration** with:

- UI installation through HACS;
- a config flow that asks the user to select the source sensor;
- no manual creation of helpers, automations, or template sensors by the end user;
- the forecast logic implemented internally in Python.

Potential future improvements include:

- replacing the simple extrapolation formula with a slope-based estimator over recent samples;
- cleaner internal state handling;
- diagnostic entities;
- easier installation for non-technical users.

---

## Functional Requirements for a Future Integration

A future integration should:

1. allow the user to select the source quarter-average sensor through the UI;
2. expose at least:
   - `Peak power forecast: final`
   - optionally `Peak power forecast: projected final`
3. detect quarter resets from the source sensor’s value drop;
4. handle zero quarters robustly;
5. handle stale telemetry robustly;
6. avoid false quarter-boundary dips or spikes;
7. not require manual helper or automation creation by the user.

---

## Non-Functional Requirements

- robust quarter-boundary behavior;
- readable and maintainable implementation;
- easy install path for less technical users;
- compatibility with Home Assistant custom integration conventions;
- future-ready for HACS distribution.

---

## Notes for Future Implementation

When porting this YAML logic to Python/custom integration form, preserve these lessons learned:

- use the meter reset itself as the source of truth for quarter rollover;
- keep a bridge across the reset moment;
- separate the ideas of:
  - previous quarter memory,
  - current quarter trend,
  - stale telemetry holding;
- do not blindly let projected values dominate at the very start of the quarter;
- treat full-zero quarters as a special case.
