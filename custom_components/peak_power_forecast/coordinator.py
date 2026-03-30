"""Coordinator that owns all runtime forecast state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, State
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_CRITICAL_LEVEL,
    CONF_FORECAST_MODE,
    CONF_INPUT_MODE,
    CONF_MONTHLY_PEAK_SENSOR,
    CONF_SOURCE_SENSOR,
    CONF_STALE_TIMEOUT,
    CONF_WARNING_LEVEL,
    DEFAULT_CRITICAL_LEVEL_KW,
    DEFAULT_FORECAST_MODE,
    DEFAULT_INPUT_MODE,
    DEFAULT_STALE_TIMEOUT_SEC,
    DEFAULT_WARNING_LEVEL_KW,
    DOMAIN,
    ENERGY_UNIT_WH,
    ENERGY_UNIT_KWH,
    FORECAST_MODE_RAMP_MINUTES,
    INPUT_MODE_CUMULATIVE,
    INPUT_MODE_DIRECT,
    QUARTER_MINUTES,
    SENSOR_KEY_COLOR,
    SENSOR_KEY_FORECAST,
    SENSOR_KEY_PROJECTED,
    SENSOR_KEY_STATUS,
    STATE_GOOD,
    ZERO_QUARTER_FALLBACK,
)
from .forecast import (
    compute_final,
    compute_projected,
    cumulative_delta_to_current_avg_kw,
    detect_reset,
    energy_to_kwh,
    floor_to_quarter,
)
from .visual import (
    effective_critical_threshold,
    forecast_to_color_hex,
    forecast_to_status,
    format_optional_float,
)

_LOGGER = logging.getLogger(__name__)
_DIRECT_RESET_MIN_INTERVAL = timedelta(minutes=10)


@dataclass
class RuntimeState:
    """Mutable state that must survive every sample update."""

    previous_quarter_final: float = 0.0
    current_quarter_max: float = 0.0
    last_good_prediction: float = 0.0
    last_source_value: float | None = None
    last_reset_ts: datetime | None = None
    last_update_ts: datetime | None = None
    last_non_zero_ts: datetime | None = None
    cumulative_quarter_start_kwh: float | None = None
    cumulative_quarter_start_ts: datetime | None = None
    prior_sample_minutes: float | None = None
    prior_sample_value: float | None = None


class PeakPowerForecastCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Stateful forecast coordinator driven by source sensor updates."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN)
        self.entry = entry
        self.input_mode: str = entry.data.get(CONF_INPUT_MODE, DEFAULT_INPUT_MODE)
        # Single selected input sensor; in older entries fallback may still be in
        # CONF_CUMULATIVE_ENERGY_SENSOR, so keep a compatibility fallback.
        self.source_sensor: str = entry.data.get(CONF_SOURCE_SENSOR, "") or entry.data.get(
            "cumulative_energy_sensor", ""
        )
        self.runtime = RuntimeState()
        self._unsub_source: Any = None
        self._unsub_monthly: Any = None
        self._last_forecast: float = 0.0
        self._last_projected: float = 0.0
        self.data = {
            SENSOR_KEY_FORECAST: 0.0,
            SENSOR_KEY_PROJECTED: 0.0,
            SENSOR_KEY_STATUS: STATE_GOOD,
            SENSOR_KEY_COLOR: "#22C55E",
        }

    def _confidence_ramp_minutes(self) -> float:
        """Minutes until confidence reaches 1 (blend fully trusts projection)."""
        mode = self.entry.options.get(CONF_FORECAST_MODE, DEFAULT_FORECAST_MODE)
        return FORECAST_MODE_RAMP_MINUTES.get(
            mode, FORECAST_MODE_RAMP_MINUTES[DEFAULT_FORECAST_MODE]
        )

    def _stale_threshold(self) -> timedelta:
        """Max age since last valid sample before treating telemetry as stale."""
        sec = int(
            self.entry.options.get(CONF_STALE_TIMEOUT, DEFAULT_STALE_TIMEOUT_SEC)
        )
        return timedelta(seconds=max(1, sec))

    def _configured_thresholds_kw(self) -> tuple[float, float]:
        """Return (warning_kw, critical_kw) from options."""
        opts = self.entry.options or {}
        w = float(opts.get(CONF_WARNING_LEVEL, DEFAULT_WARNING_LEVEL_KW))
        c = float(opts.get(CONF_CRITICAL_LEVEL, DEFAULT_CRITICAL_LEVEL_KW))
        return w, c

    def _monthly_peak_entity_id(self) -> str:
        """Optional entity reporting current calendar-month peak (kW)."""
        raw = (self.entry.options or {}).get(CONF_MONTHLY_PEAK_SENSOR, "")
        return raw if isinstance(raw, str) else ""

    def _read_monthly_peak_kw(self) -> float | None:
        """Last known monthly peak from configured sensor, if valid."""
        eid = self._monthly_peak_entity_id()
        if not eid:
            return None
        state = self.hass.states.get(eid)
        if state is None:
            return None
        parsed = self._state_to_float(state.state)
        return format_optional_float(parsed)

    def _publish_forecast_bundle(self, forecast: float, projected: float) -> None:
        """Publish blended forecast, raw extrapolation, and derived status/color."""
        self._last_forecast = forecast
        self._last_projected = projected
        warn_kw, crit_cfg_kw = self._configured_thresholds_kw()
        monthly = self._read_monthly_peak_kw()
        crit_eff = effective_critical_threshold(
            configured_critical=crit_cfg_kw,
            monthly_peak_value=monthly,
        )
        status = forecast_to_status(
            forecast, warning=warn_kw, critical_effective=crit_eff
        )
        color = forecast_to_color_hex(
            forecast, warning=warn_kw, critical_effective=crit_eff
        )
        self.async_set_updated_data(
            {
                SENSOR_KEY_FORECAST: forecast,
                SENSOR_KEY_PROJECTED: projected,
                SENSOR_KEY_STATUS: status,
                SENSOR_KEY_COLOR: color,
            }
        )

    async def async_initialize(self) -> None:
        """Set baseline timestamps and subscribe to source sensor updates."""
        now = datetime.now(UTC)
        self.runtime.last_reset_ts = (
            floor_to_quarter(now)
            if self.input_mode == INPUT_MODE_CUMULATIVE
            else now
        )
        self.runtime.last_non_zero_ts = now

        state = self.hass.states.get(self.source_sensor)
        if state is not None:
            if self.input_mode == INPUT_MODE_DIRECT:
                value = self._state_to_float(state.state)
                if value is not None:
                    self.runtime.last_source_value = value
                    self.runtime.current_quarter_max = value
                    if value > 0:
                        self.runtime.last_non_zero_ts = now
                    self.runtime.last_update_ts = now
                    self._recompute(value, self._minutes_elapsed(now), stale=False)
            else:
                energy_kwh = self._state_to_energy_kwh(state)
                if energy_kwh is not None:
                    q_start = floor_to_quarter(now)
                    self.runtime.cumulative_quarter_start_ts = q_start
                    self.runtime.cumulative_quarter_start_kwh = energy_kwh
                    self.runtime.last_reset_ts = q_start
                    self.runtime.last_update_ts = now
                    self._recompute(0.0, self._minutes_elapsed(now), stale=False)

        self._unsub_source = async_track_state_change_event(
            self.hass,
            [self.source_sensor],
            self._async_handle_source_event,
        )
        self._attach_monthly_listener()

    def _attach_monthly_listener(self) -> None:
        """Subscribe to optional monthly peak sensor updates."""
        if self._unsub_monthly is not None:
            self._unsub_monthly()
            self._unsub_monthly = None
        mp = self._monthly_peak_entity_id()
        if mp:
            self._unsub_monthly = async_track_state_change_event(
                self.hass,
                [mp],
                self._async_handle_monthly_event,
            )

    async def async_shutdown(self) -> None:
        """Unsubscribe listeners."""
        if self._unsub_source is not None:
            self._unsub_source()
            self._unsub_source = None
        if self._unsub_monthly is not None:
            self._unsub_monthly()
            self._unsub_monthly = None

    async def _async_handle_monthly_event(
        self, _event: Event[EventStateChangedData]
    ) -> None:
        """Recompute status/color when monthly peak reference changes."""
        self._publish_forecast_bundle(self._last_forecast, self._last_projected)

    async def _async_handle_source_event(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle each source sensor state change event."""
        new_state = event.data.get("new_state")
        if new_state is None:
            return

        now = datetime.now(UTC)
        stale = self._is_stale(now)

        if self.input_mode == INPUT_MODE_DIRECT:
            value = self._state_to_float(new_state.state)
            if value is None:
                self._publish_hold_state()
                return

            self._handle_new_sample_direct(value, now)
            self._recompute(value, self._minutes_elapsed(now), stale=stale)
            self.runtime.last_update_ts = now
            self.runtime.last_source_value = value
            return

        energy_kwh = self._state_to_energy_kwh(new_state)
        if energy_kwh is None:
            self._publish_hold_state()
            return

        effective_avg, minutes_elapsed = self._normalize_cumulative_sample(energy_kwh, now)
        self._recompute(effective_avg, minutes_elapsed, stale=stale)
        self.runtime.last_update_ts = now
        self.runtime.last_source_value = effective_avg

    def _handle_new_sample_direct(self, value: float, now: datetime) -> None:
        """Update runtime state from one valid direct-mode sample."""
        if self._is_direct_quarter_reset(value, now):
            # Last sample before reset is the quarter's final running average (may be below in-quarter max).
            prev_final = self.runtime.last_source_value
            self.runtime.previous_quarter_final = (
                prev_final
                if prev_final is not None
                else self.runtime.current_quarter_max
            )
            self.runtime.last_reset_ts = now
            self.runtime.current_quarter_max = value
            self.runtime.prior_sample_minutes = None
            self.runtime.prior_sample_value = None

        self.runtime.current_quarter_max = max(self.runtime.current_quarter_max, value)

        if value > 0:
            self.runtime.last_non_zero_ts = now
        elif (
            self.runtime.last_non_zero_ts is not None
            and now - self.runtime.last_non_zero_ts >= ZERO_QUARTER_FALLBACK
        ):
            self.runtime.previous_quarter_final = 0.0
            self.runtime.current_quarter_max = 0.0
            self.runtime.last_reset_ts = now
            self.runtime.last_non_zero_ts = now
            self.runtime.prior_sample_minutes = None
            self.runtime.prior_sample_value = None

    def _is_direct_quarter_reset(self, value: float, now: datetime) -> bool:
        """Return True when a direct sensor sample indicates a new quarter."""
        if not detect_reset(self.runtime.last_source_value, value):
            return False
        if self.runtime.last_reset_ts is None:
            return True
        # Avoid false resets when net demand decreases inside a quarter.
        return (now - self.runtime.last_reset_ts) >= _DIRECT_RESET_MIN_INTERVAL

    def _normalize_cumulative_sample(
        self, energy_kwh: float, now: datetime
    ) -> tuple[float, float]:
        """Convert cumulative-energy input to effective current-average demand."""
        quarter_start = floor_to_quarter(now)

        if self.runtime.cumulative_quarter_start_ts != quarter_start:
            # Wall-clock quarter roll: previous final is last effective_avg, not its in-quarter max.
            prev_final = self.runtime.last_source_value
            self.runtime.previous_quarter_final = (
                prev_final
                if prev_final is not None
                else self.runtime.current_quarter_max
            )
            self.runtime.current_quarter_max = 0.0
            self.runtime.last_reset_ts = quarter_start
            self.runtime.cumulative_quarter_start_ts = quarter_start
            self.runtime.cumulative_quarter_start_kwh = energy_kwh
            self.runtime.prior_sample_minutes = None
            self.runtime.prior_sample_value = None

        if self.runtime.cumulative_quarter_start_kwh is None:
            self.runtime.cumulative_quarter_start_kwh = energy_kwh

        baseline = self.runtime.cumulative_quarter_start_kwh
        if energy_kwh < baseline:
            # Meter reset or rollover in the source sensor: restart baseline safely.
            self.runtime.cumulative_quarter_start_kwh = energy_kwh
            baseline = energy_kwh

        delta_kwh = max(0.0, energy_kwh - baseline)
        minutes_elapsed = max(
            0.0, min((now - quarter_start).total_seconds() / 60.0, QUARTER_MINUTES)
        )
        effective_avg = cumulative_delta_to_current_avg_kw(delta_kwh, minutes_elapsed)

        self.runtime.current_quarter_max = max(self.runtime.current_quarter_max, effective_avg)
        if effective_avg > 0:
            self.runtime.last_non_zero_ts = now

        return effective_avg, minutes_elapsed

    def _recompute(self, value: float, minutes_elapsed: float, *, stale: bool) -> None:
        """Compute projected (internal) and final forecast; publish bundle."""
        projected = compute_projected(
            current_value=value,
            previous_quarter_final=self.runtime.previous_quarter_final,
            current_quarter_max=self.runtime.current_quarter_max,
            minutes_elapsed=minutes_elapsed,
            prior_minutes=self.runtime.prior_sample_minutes,
            prior_value=self.runtime.prior_sample_value,
        )
        final = compute_final(
            stale=stale,
            minutes_elapsed=minutes_elapsed,
            confidence_ramp_minutes=self._confidence_ramp_minutes(),
            current_value=value,
            previous_quarter_final=self.runtime.previous_quarter_final,
            current_quarter_max=self.runtime.current_quarter_max,
            projected=projected,
            last_good_prediction=self.runtime.last_good_prediction,
        )

        if not stale:
            self.runtime.last_good_prediction = final

        self.runtime.prior_sample_minutes = minutes_elapsed
        self.runtime.prior_sample_value = value

        self._publish_forecast_bundle(final, projected)

    def _publish_hold_state(self) -> None:
        """Publish a resilient fallback state during invalid telemetry."""
        held = max(
            self.runtime.last_good_prediction,
            self.runtime.previous_quarter_final,
        )
        self._publish_forecast_bundle(held, self._last_projected)

    def _minutes_elapsed(self, now: datetime) -> float:
        """Return elapsed minutes in current meter quarter, clamped to [0, 15]."""
        if self.runtime.last_reset_ts is None:
            return 0.0
        elapsed = (now - self.runtime.last_reset_ts).total_seconds() / 60.0
        return max(0.0, min(elapsed, QUARTER_MINUTES))

    def _is_stale(self, now: datetime) -> bool:
        """Return True if the previous valid update is too old."""
        if self.runtime.last_update_ts is None:
            return False
        return (now - self.runtime.last_update_ts) > self._stale_threshold()

    @staticmethod
    def _state_to_float(state: str) -> float | None:
        """Parse a HA state to float, returning None for non-numeric states."""
        if state in {"unknown", "unavailable", "none", ""}:
            return None
        try:
            return float(state)
        except ValueError:
            return None

    def _state_to_energy_kwh(self, state: State) -> float | None:
        """Parse a cumulative energy state as kWh, supporting Wh and kWh only."""
        numeric = self._state_to_float(state.state)
        if numeric is None:
            return None

        unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        if unit not in {ENERGY_UNIT_KWH, ENERGY_UNIT_WH}:
            return None

        try:
            return energy_to_kwh(numeric, str(unit))
        except ValueError:
            return None
