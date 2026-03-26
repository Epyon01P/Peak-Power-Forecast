"""Constants for the Peak Power Forecast integration."""

from datetime import timedelta

DOMAIN = "peak_power_forecast"

CONF_SOURCE_SENSOR = "source_sensor"
CONF_CUMULATIVE_ENERGY_SENSOR = "cumulative_energy_sensor"
CONF_INPUT_MODE = "input_mode"
CONF_FORECAST_MODE = "forecast_mode"
CONF_STALE_TIMEOUT = "stale_telemetry_timeout"
CONF_MONTHLY_PEAK_SENSOR = "monthly_peak_sensor"
CONF_WARNING_LEVEL = "warning_level_kw"
CONF_CRITICAL_LEVEL = "critical_level_kw"
CONF_SETUP_PATH = "setup_path"

DEFAULT_NAME = "Peak Power Forecast"

INPUT_MODE_DIRECT = "direct"
INPUT_MODE_CUMULATIVE = "cumulative_energy"
DEFAULT_INPUT_MODE = INPUT_MODE_DIRECT

# Forecast mode stored values (options / internal)
FORECAST_MODE_CONSERVATIVE = "conservative"
FORECAST_MODE_BALANCED = "balanced"
FORECAST_MODE_RESPONSIVE = "responsive"

FORECAST_MODE_RAMP_MINUTES: dict[str, float] = {
    FORECAST_MODE_CONSERVATIVE: 7.5,
    FORECAST_MODE_BALANCED: 5.0,
    FORECAST_MODE_RESPONSIVE: 3.0,
}

DEFAULT_FORECAST_MODE = FORECAST_MODE_BALANCED
DEFAULT_STALE_TIMEOUT_SEC = 40

DEFAULT_WARNING_LEVEL_KW = 3.0
DEFAULT_CRITICAL_LEVEL_KW = 4.0

QUARTER_MINUTES = 15.0
ZERO_QUARTER_FALLBACK = timedelta(minutes=15)

ENERGY_UNIT_WH = "Wh"
ENERGY_UNIT_KWH = "kWh"

SENSOR_KEY_FORECAST = "forecast"
SENSOR_KEY_STATUS = "status"
SENSOR_KEY_COLOR = "color"

# Status entity states (stable for automations)
STATE_GOOD = "Good"
STATE_WARNING = "Warning"
STATE_CRITICAL = "Critical"
