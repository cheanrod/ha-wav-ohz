"""Data update coordinator for the WAV Osterholz integration."""

from __future__ import annotations

import logging

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, FEES_URL, UPDATE_INTERVAL
from .parser import FeePageError, FeeSchedule, parse_fee_page

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)


class WavOsterholzCoordinator(DataUpdateCoordinator[FeeSchedule]):
    """Fetch and parse the WAV Osterholz fee page once a day."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
            config_entry=entry,
        )
        self._session = async_get_clientsession(hass)

    async def _async_update_data(self) -> FeeSchedule:
        """Fetch the fee page and parse it."""
        try:
            response = await self._session.get(FEES_URL, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            html = await response.text()
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Error fetching {FEES_URL}: {err}") from err
        except TimeoutError as err:
            raise UpdateFailed(f"Timeout fetching {FEES_URL}") from err

        # Parsing is pure CPU work on a ~60 kB document; keep it off the event
        # loop so a pathological page cannot stall Home Assistant.
        try:
            return await self.hass.async_add_executor_job(parse_fee_page, html)
        except FeePageError as err:
            raise UpdateFailed(str(err)) from err
