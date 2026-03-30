"""Sensor entities for Peak Power Forecast."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    SENSOR_KEY_COLOR,
    SENSOR_KEY_FORECAST,
    SENSOR_KEY_PROJECTED,
    SENSOR_KEY_STATUS,
)
from .coordinator import PeakPowerForecastCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Peak Power Forecast sensors from config entry."""
    coordinator: PeakPowerForecastCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            PeakPowerForecastSensor(coordinator, entry),
            PeakPowerForecastProjectedSensor(coordinator, entry),
            PeakPowerForecastStatusSensor(coordinator, entry),
            PeakPowerForecastColorSensor(coordinator, entry),
        ]
    )


class PeakPowerForecastSensor(
    CoordinatorEntity[PeakPowerForecastCoordinator], SensorEntity
):
    """Peak Power Forecast main sensor (kW)."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_translation_key = "peak_power_forecast"
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: PeakPowerForecastCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{SENSOR_KEY_FORECAST}"

    @property
    def suggested_object_id(self) -> str | None:
        """Prefer stable entity_id `sensor.peak_power_forecast` when not taken."""
        return "peak_power_forecast"

    @property
    def native_value(self) -> float | None:
        """Return the current forecast from the coordinator."""
        if self.coordinator.data is None:
            return None
        val = self.coordinator.data.get(SENSOR_KEY_FORECAST)
        return float(val) if val is not None else None


class PeakPowerForecastProjectedSensor(
    CoordinatorEntity[PeakPowerForecastCoordinator], SensorEntity
):
    """End-of-quarter extrapolation from current average only (before blend)."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_translation_key = "peak_power_forecast_projected"
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: PeakPowerForecastCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{SENSOR_KEY_PROJECTED}"

    @property
    def suggested_object_id(self) -> str | None:
        return "peak_power_forecast_projected"

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data is None:
            return None
        val = self.coordinator.data.get(SENSOR_KEY_PROJECTED)
        return float(val) if val is not None else None


class PeakPowerForecastStatusSensor(
    CoordinatorEntity[PeakPowerForecastCoordinator], SensorEntity
):
    """Good / Warning / Critical derived from forecast vs thresholds."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_translation_key = "peak_power_forecast_status"

    def __init__(
        self,
        coordinator: PeakPowerForecastCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{SENSOR_KEY_STATUS}"

    @property
    def suggested_object_id(self) -> str | None:
        return "peak_power_forecast_status"

    @property
    def native_value(self) -> str | None:
        if self.coordinator.data is None:
            return None
        raw = self.coordinator.data.get(SENSOR_KEY_STATUS)
        return str(raw) if raw is not None else None


class PeakPowerForecastColorSensor(
    CoordinatorEntity[PeakPowerForecastCoordinator], SensorEntity
):
    """Hex color (#RRGGBB) for dashboards / ESPHome; hidden from default UI."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_translation_key = "peak_power_forecast_color"
    _attr_entity_registry_visible_default = False

    def __init__(
        self,
        coordinator: PeakPowerForecastCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{SENSOR_KEY_COLOR}"

    @property
    def suggested_object_id(self) -> str | None:
        return "peak_power_forecast_color"

    @property
    def native_value(self) -> str | None:
        if self.coordinator.data is None:
            return None
        raw = self.coordinator.data.get(SENSOR_KEY_COLOR)
        return str(raw) if raw is not None else None
