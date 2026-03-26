"""Config flow for Peak Power Forecast."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT, Platform
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_CRITICAL_LEVEL,
    CONF_FORECAST_MODE,
    CONF_INPUT_MODE,
    CONF_MONTHLY_PEAK_SENSOR,
    CONF_SETUP_PATH,
    CONF_SOURCE_SENSOR,
    CONF_STALE_TIMEOUT,
    CONF_WARNING_LEVEL,
    DEFAULT_CRITICAL_LEVEL_KW,
    DEFAULT_FORECAST_MODE,
    DEFAULT_INPUT_MODE,
    DEFAULT_NAME,
    DEFAULT_STALE_TIMEOUT_SEC,
    DEFAULT_WARNING_LEVEL_KW,
    DOMAIN,
    ENERGY_UNIT_KWH,
    ENERGY_UNIT_WH,
    FORECAST_MODE_BALANCED,
    FORECAST_MODE_CONSERVATIVE,
    FORECAST_MODE_RESPONSIVE,
    INPUT_MODE_CUMULATIVE,
    INPUT_MODE_DIRECT,
)


def _forecast_mode_selector() -> selector.SelectSelector:
    """Mode list uses translation_key `forecast_mode` (see translations/*.json)."""
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[
                FORECAST_MODE_CONSERVATIVE,
                FORECAST_MODE_BALANCED,
                FORECAST_MODE_RESPONSIVE,
            ],
            mode=selector.SelectSelectorMode.DROPDOWN,
            translation_key="forecast_mode",
        )
    )


def _input_mode_selector(translation_key: str) -> selector.SelectSelector:
    """Selector for choosing direct vs cumulative fallback input mode."""
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[INPUT_MODE_DIRECT, INPUT_MODE_CUMULATIVE],
            mode=selector.SelectSelectorMode.DROPDOWN,
            translation_key=translation_key,
        )
    )


def _normalize_monthly_peak_entity(user_input: dict[str, Any]) -> str:
    """Store '' when unset so options stay JSON-friendly."""
    raw = user_input.get(CONF_MONTHLY_PEAK_SENSOR)
    if raw in (None, "", "unavailable", "unknown"):
        return ""
    return str(raw).strip()


def _safe_float_option(
    options: dict[str, Any], key: str, default: float
) -> float:
    """Coerce stored option to float without crashing the options form."""
    raw = options.get(key, default)
    if raw is None:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _normalize_entity_id(value: Any) -> str:
    """Normalize optional entity_id from selector values."""
    if value in (None, "", "unknown", "unavailable"):
        return ""
    return str(value).strip()


def _validate_numeric_sensor(
    hass, entity_id: str
) -> str | None:
    """Validate that an entity exists and has a numeric state."""
    state = hass.states.get(entity_id)
    if state is None:
        return "sensor_not_found"
    try:
        float(state.state)
    except ValueError:
        return "sensor_not_numeric"
    return None


def _validate_cumulative_sensor(
    hass, entity_id: str
) -> str | None:
    """Validate cumulative energy fallback sensor requirements."""
    state = hass.states.get(entity_id)
    if state is None:
        return "cumulative_sensor_not_found"
    try:
        float(state.state)
    except ValueError:
        return "cumulative_sensor_not_numeric"

    unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
    if unit not in {ENERGY_UNIT_WH, ENERGY_UNIT_KWH}:
        return "cumulative_sensor_unsupported_unit"

    device_class = state.attributes.get("device_class")
    if device_class is not None and device_class != "energy":
        return "cumulative_sensor_wrong_device_class"

    state_class = state.attributes.get("state_class")
    if state_class is not None and state_class not in {"total", "total_increasing"}:
        return "cumulative_sensor_wrong_state_class"

    return None


def _safe_int_option(options: dict[str, Any], key: str, default: int) -> int:
    """Coerce stored option to int without crashing the options form."""
    raw = options.get(key, default)
    if raw is None:
        return default
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return default


class PeakPowerForecastConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the integration."""

    VERSION = 1
    _pending_source_sensor: str | None = None
    _pending_input_mode: str | None = None

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the options flow handler."""
        return PeakPowerForecastOptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Single setup step with mode-aware sensor validation."""
        errors: dict[str, str] = {}

        if user_input is not None:
            setup_path = user_input[CONF_SETUP_PATH]
            source_sensor = _normalize_entity_id(user_input.get(CONF_SOURCE_SENSOR))

            if setup_path == INPUT_MODE_DIRECT:
                if not source_sensor:
                    errors["base"] = "source_sensor_required"
                else:
                    err = _validate_numeric_sensor(self.hass, source_sensor)
                    if err is not None:
                        errors["base"] = err
            else:
                if not source_sensor:
                    errors["base"] = "source_sensor_required"
                else:
                    err = _validate_cumulative_sensor(self.hass, source_sensor)
                    if err is not None:
                        errors["base"] = err

            if not errors:
                self._pending_source_sensor = source_sensor
                self._pending_input_mode = setup_path
                return await self.async_step_setup_limits()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SOURCE_SENSOR): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain=Platform.SENSOR,
                        )
                    ),
                    vol.Required(CONF_SETUP_PATH, default=INPUT_MODE_DIRECT): _input_mode_selector(
                        "setup_path"
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_setup_limits(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Second setup step: ask warning/critical thresholds explicitly."""
        errors: dict[str, str] = {}

        if self._pending_source_sensor is None or self._pending_input_mode is None:
            return await self.async_step_user()

        if user_input is not None:
            try:
                warn_kw = float(user_input[CONF_WARNING_LEVEL])
                crit_kw = float(user_input[CONF_CRITICAL_LEVEL])
            except (TypeError, ValueError, KeyError):
                errors["base"] = "invalid_threshold"
            else:
                if warn_kw <= 0 or crit_kw <= 0:
                    errors["base"] = "invalid_threshold"
                elif warn_kw >= crit_kw:
                    errors["base"] = "warning_not_below_critical"

            if not errors:
                selected_unique_id = self._pending_source_sensor
                await self.async_set_unique_id(selected_unique_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=DEFAULT_NAME,
                    data={
                        CONF_INPUT_MODE: self._pending_input_mode,
                        CONF_SOURCE_SENSOR: self._pending_source_sensor,
                    },
                    options={
                        CONF_INPUT_MODE: self._pending_input_mode,
                        CONF_FORECAST_MODE: DEFAULT_FORECAST_MODE,
                        CONF_STALE_TIMEOUT: DEFAULT_STALE_TIMEOUT_SEC,
                        CONF_MONTHLY_PEAK_SENSOR: "",
                        CONF_WARNING_LEVEL: warn_kw,
                        CONF_CRITICAL_LEVEL: crit_kw,
                    },
                )

        return self.async_show_form(
            step_id="setup_limits",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_WARNING_LEVEL, default=DEFAULT_WARNING_LEVEL_KW
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0.1,
                            max=50.0,
                            step=0.01,
                            mode=selector.NumberSelectorMode.BOX,
                            unit_of_measurement="kW",
                        )
                    ),
                    vol.Required(
                        CONF_CRITICAL_LEVEL, default=DEFAULT_CRITICAL_LEVEL_KW
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0.1,
                            max=50.0,
                            step=0.01,
                            mode=selector.NumberSelectorMode.BOX,
                            unit_of_measurement="kW",
                        )
                    ),
                }
            ),
            errors=errors,
        )


class PeakPowerForecastOptionsFlow(config_entries.OptionsFlow):
    """Handle integration options for both input modes and thresholds."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Store config entry passed by Home Assistant."""
        self.config_entry = config_entry

    async def async_step_init(  # type: ignore[override]
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Manage integration options form."""

        errors: dict[str, str] = {}
        entry = self.config_entry
        options = dict(entry.options or {})
        data = dict(entry.data or {})

        if user_input is not None:
            input_mode = user_input[CONF_INPUT_MODE]
            source_sensor = _normalize_entity_id(user_input.get(CONF_SOURCE_SENSOR))
            stale_raw = user_input[CONF_STALE_TIMEOUT]

            if input_mode == INPUT_MODE_DIRECT:
                if not source_sensor:
                    errors["base"] = "source_sensor_required"
                else:
                    err = _validate_numeric_sensor(self.hass, source_sensor)
                    if err is not None:
                        errors["base"] = err
            else:
                if not source_sensor:
                    errors["base"] = "source_sensor_required"
                else:
                    err = _validate_cumulative_sensor(self.hass, source_sensor)
                    if err is not None:
                        errors["base"] = err

            try:
                stale_sec = int(stale_raw)
            except (TypeError, ValueError):
                errors["base"] = "invalid_stale_timeout"
            else:
                if stale_sec < 5 or stale_sec > 600:
                    errors["base"] = "invalid_stale_timeout"

            try:
                warn_kw = float(user_input[CONF_WARNING_LEVEL])
                crit_kw = float(user_input[CONF_CRITICAL_LEVEL])
            except (TypeError, ValueError, KeyError):
                errors["base"] = "invalid_threshold"
            else:
                if warn_kw <= 0 or crit_kw <= 0:
                    errors["base"] = "invalid_threshold"
                elif warn_kw >= crit_kw:
                    errors["base"] = "warning_not_below_critical"

            if not errors:
                selected_unique_id = source_sensor
                for ha_entry in self.hass.config_entries.async_entries(DOMAIN):
                    if (
                        ha_entry.entry_id != entry.entry_id
                        and ha_entry.unique_id == selected_unique_id
                    ):
                        errors["base"] = "duplicate_source"

            if not errors:
                self.hass.config_entries.async_update_entry(
                    entry,
                    data={
                        CONF_INPUT_MODE: input_mode,
                        CONF_SOURCE_SENSOR: source_sensor,
                    },
                    unique_id=selected_unique_id,
                )
                return self.async_create_entry(
                    title="",
                    data={
                        CONF_INPUT_MODE: input_mode,
                        CONF_FORECAST_MODE: user_input[CONF_FORECAST_MODE],
                        CONF_STALE_TIMEOUT: int(stale_raw),
                        # Keep any previously stored monthly peak option,
                        # but do not expose it in the options UI.
                        CONF_MONTHLY_PEAK_SENSOR: options.get(CONF_MONTHLY_PEAK_SENSOR, ""),
                        CONF_WARNING_LEVEL: float(user_input[CONF_WARNING_LEVEL]),
                        CONF_CRITICAL_LEVEL: float(user_input[CONF_CRITICAL_LEVEL]),
                    },
                )

        mode_default_raw = data.get(
            CONF_INPUT_MODE, options.get(CONF_INPUT_MODE, DEFAULT_INPUT_MODE)
        )
        mode_default = (
            mode_default_raw
            if mode_default_raw in {INPUT_MODE_DIRECT, INPUT_MODE_CUMULATIVE}
            else DEFAULT_INPUT_MODE
        )
        source_default = data.get(CONF_SOURCE_SENSOR, "")
        if isinstance(source_default, str) and source_default.strip():
            source_key = vol.Optional(CONF_SOURCE_SENSOR, default=source_default)
        else:
            source_key = vol.Optional(CONF_SOURCE_SENSOR)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_INPUT_MODE,
                    default=mode_default,
                ): _input_mode_selector("input_mode"),
                source_key: selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=Platform.SENSOR)
                ),
                vol.Required(
                    CONF_FORECAST_MODE,
                    default=options.get(CONF_FORECAST_MODE, DEFAULT_FORECAST_MODE),
                ): _forecast_mode_selector(),
                vol.Required(
                    CONF_WARNING_LEVEL,
                    default=_safe_float_option(
                        options, CONF_WARNING_LEVEL, DEFAULT_WARNING_LEVEL_KW
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0.1,
                        max=50.0,
                        step=0.01,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="kW",
                    )
                ),
                vol.Required(
                    CONF_CRITICAL_LEVEL,
                    default=_safe_float_option(
                        options, CONF_CRITICAL_LEVEL, DEFAULT_CRITICAL_LEVEL_KW
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0.1,
                        max=50.0,
                        step=0.01,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="kW",
                    )
                ),
                vol.Required(
                    CONF_STALE_TIMEOUT,
                    default=_safe_int_option(
                        options, CONF_STALE_TIMEOUT, DEFAULT_STALE_TIMEOUT_SEC
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=5,
                        max=600,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="s",
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
        )
