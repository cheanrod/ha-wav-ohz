"""The WAV Osterholz water fee integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import WavOsterholzCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]

type WavOsterholzConfigEntry = ConfigEntry[WavOsterholzCoordinator]


async def async_setup_entry(
    hass: HomeAssistant, entry: WavOsterholzConfigEntry
) -> bool:
    """Set up WAV Osterholz from a config entry."""
    coordinator = WavOsterholzCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: WavOsterholzConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_reload_entry(
    hass: HomeAssistant, entry: WavOsterholzConfigEntry
) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)
