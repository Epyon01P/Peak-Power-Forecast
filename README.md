# Peak Power Forecast

[![GitHub Release](https://img.shields.io/github/v/release/Epyon01P/Peak-Power-Forecast)](https://github.com/Epyon01P/Peak-Power-Forecast/releases)
[![GitHub Issues](https://img.shields.io/github/issues/Epyon01P/Peak-Power-Forecast)](https://github.com/Epyon01P/Peak-Power-Forecast/issues)
[![Downloads](https://img.shields.io/github/downloads/Epyon01P/Peak-Power-Forecast/total)](https://github.com/Epyon01P/Peak-Power-Forecast/releases)

Custom Home Assistant integration to forecast quarter-hourly peak power consumption based on DSMR (P1) digital meter data. It helps manage capacity tariffs (e.g. in Flanders) and avoid high peak charges.

Instead of extrapolating a monotonically increasing peak consumption sensor that resets every 15 minutes (creating a sawtooth profile), this integration provides a sensor that continuously forecasts the final peak power value of the current quarter hour. It does so based on previous consumption patterns and extrapolation of current usage, gradually giving more confidence to the latter as the quarter hour passes on.

The peak power forecast is both given as a numeric value and as a color gradient, going from green to red. This gives users immediate insight into whether there is still “room” to turn on additional devices, or whether they should reduce consumption to avoid a high peak at the end of the current quarter hour.

This integration also has a companion ESPHome project called [Peak Power Indicator](https://github.com/Epyon01P/Peak-Power-Indicator): an unobtrusive LED indicator that physically shows the forecast color gradient in realtime (green → amber → red).

## Requirements

- Home Assistant Core `2024.6.0` or later
- HACS installed
- One input sensor:
  - **Current average demand sensor** with unit `kW` or `W` (preferred mode), or
  - **Cumulative energy sensor** with unit `Wh` or `kWh` (fallback mode)

## Features

- Peak power forecast and projected end-of-quarter value
- Simple status indication (`Good`, `Warning`, `Critical`)
- Color indicator with smooth two-step gradient for dashboards and LEDs
- Forecast mode tuning
- Configurable warning/critical thresholds
- Configurable stale telemetry timeout
- Local operation only (no cloud dependency)

## Install

1. Open HACS in Home Assistant.
2. Go to **Integrations -> Custom repositories**.
3. Add `https://github.com/Epyon01P/Peak-Power-Forecast` as category **Integration**.
4. Search for and install **Peak Power Forecast** from the HACS store.
5. Restart Home Assistant.

## Setup

1. Go to **Settings -> Devices & Services -> Add Integration**.
2. Search for **Peak Power Forecast**.
3. Select **one input sensor** and choose input mode:
   - `Current average demand sensor (preferred mode)`
   - `Cumulative energy sensor (fallback method)`
4. Set warning and critical levels.

### Input Modes

- **Current average demand sensor (preferred mode)**  
  The selected sensor already represents the quarter-average demand so far in `kW`, and resets each quarter. 
  This sensor should be included in most DSMR P1 integrations (e.g. in HomeWizard it's called `sensor.p1_meter_gemiddeld_verbruik`, in the [plan-d dongle](https://github.com/plan-d-io/P1-dongle) it's `sensor.current_average_demand`).

- **Cumulative energy sensor (fallback method)**  
  The selected sensor is cumulative (`Wh`/`kWh`).  
  Use this option if you do not have a sensor tracking the quarter hourly peak demand, but do have a sensor tracking the total energy consumption of the grid. The integration will then derive current quarter-average demand from the energy delta within fixed wall-clock quarter boundaries (`hh:00`, `hh:15`, `hh:30`, `hh:45`).

### Forecast and Alert Settings

- **Forecast mode**  
  Controls how quickly the forecast adapts to the current quarter
  - **Conservative**: confidence reaches 1 in 7.5 min
  - **Balanced**: confidence reaches 1 in 5 min (default)
  - **Responsive**: confidence reaches 1 in 3 min

- **Warning level**  
  Threshold (kW) where forecast status changes from `Good` to `Warning`.

- **Critical level**  
  Threshold (kW) where forecast status changes to `Critical`.

- **Stale telemetry timeout**  
  Number of seconds without fresh sensor updates before the integration switches to resilient stale handling.

## Forecast Method (How It Works)

0. Normalizes input to an internal effective current average demand signal (only when using the fallback method).
1. Tracks previous quarter final value and current quarter behavior.
2. Computes projected end value of current quarter from current average demand plus short-term trend extrapolation.
3. Blends projected value with previous quarter final value using the forecast-mode confidence ramp.
4. Applies resilient stale handling during telemetry gaps.

## Status and Color Behavior

- `Good` if forecast < warning
- `Warning` if warning <= forecast < effective critical
- `Critical` if forecast >= effective critical

Color sensor output (for LED companion button):
- Green edge: `#39FF14`
- Warning edge: `#FFC400`
- Red edge: `#FF4B33`
- Linear RGB interpolation in two ranges: green → warning, then warning → red

## Important note on timing (DSMR mode)

When using a **current average demand sensor**, quarter-hour boundaries are determined by the **digital meter itself**, not by Home Assistant.

This means the reset moments (every ~15 minutes) may be slightly out of sync with the Home Assistant system clock. As a result, you may occasionally observe small timing offsets in graphs or forecast behavior around quarter boundaries.

This is expected behavior and does not affect the correctness of the forecast.

## Entities

| Entity id | Description |
| --------- | ----------- |
| `sensor.peak_power_forecast` | Forecast of final quarter-hour average demand (kW). |
| `sensor.peak_power_forecast_projected` | Raw projected end-of-quarter value from extrapolation (before confidence blending). |
| `sensor.peak_power_forecast_status` | `Good` / `Warning` / `Critical`. |
| `sensor.peak_power_forecast_color` | Hex color output for dashboards/LED integrations. |

## Localization

UI strings are available in English, Dutch, French, and German.
