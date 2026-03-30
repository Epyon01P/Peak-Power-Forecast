"""Peak Power Forecast integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import PeakPowerForecastCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up integration from YAML (not used)."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Peak Power Forecast from a config entry."""
    coordinator = PeakPowerForecastCoordinator(hass, entry)
    await coordinator.async_initialize()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    entry.async_on_unload(entry.add_update_listener(_async_reload_on_entry_update))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_reload_on_entry_update(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload when options (or entry) change so runtime options take effect."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False

    coordinator: PeakPowerForecastCoordinator | None = hass.data[DOMAIN].pop(
        entry.entry_id, None
    )
    if coordinator is not None:
        await coordinator.async_shutdown()

    if not hass.data[DOMAIN]:
        hass.data.pop(DOMAIN)

    return True
