"""Config flow for the WAV Osterholz integration."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
    ConfigEntry,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CONF_METER_SIZE,
    CONF_MUNICIPALITY,
    DEFAULT_METER_SIZE,
    DOMAIN,
    FEES_URL,
    METER_SIZES,
    MUNICIPALITIES,
)
from .parser import FeePageError, parse_fee_page

_LOGGER = logging.getLogger(__name__)


def _select(options: dict[str, str]) -> SelectSelector:
    """Build a dropdown selector for a key/label mapping.

    The labels are proper nouns (municipalities) and meter designations, so they
    are the same in every language and are passed through verbatim.
    """
    return SelectSelector(
        SelectSelectorConfig(
            options=[
                SelectOptionDict(value=value, label=label)
                for value, label in options.items()
            ],
            mode=SelectSelectorMode.DROPDOWN,
        )
    )


def _schema(municipality: str | None, meter_size: str) -> vol.Schema:
    """Build the form schema, pre-filling the current values."""
    fields: dict[Any, Any] = {}
    if municipality is None:
        fields[vol.Required(CONF_MUNICIPALITY)] = _select(MUNICIPALITIES)
    fields[vol.Required(CONF_METER_SIZE, default=meter_size)] = _select(METER_SIZES)
    return vol.Schema(fields)


async def _async_validate_page(hass: HomeAssistant) -> None:
    """Confirm the fee page is reachable and parsable before creating an entry."""
    session = async_get_clientsession(hass)
    response = await session.get(FEES_URL, timeout=aiohttp.ClientTimeout(total=30))
    response.raise_for_status()
    html = await response.text()
    await hass.async_add_executor_job(parse_fee_page, html)


class WavOsterholzConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial setup."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the municipality and water meter size."""
        errors: dict[str, str] = {}

        if user_input is not None:
            municipality = user_input[CONF_MUNICIPALITY]
            await self.async_set_unique_id(municipality)
            self._abort_if_unique_id_configured()

            try:
                await _async_validate_page(self.hass)
            except (aiohttp.ClientError, TimeoutError):
                errors["base"] = "cannot_connect"
            except FeePageError:
                errors["base"] = "cannot_parse"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during setup")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=MUNICIPALITIES[municipality],
                    data={CONF_MUNICIPALITY: municipality},
                    options={CONF_METER_SIZE: user_input[CONF_METER_SIZE]},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_schema(None, DEFAULT_METER_SIZE),
            errors=errors,
            description_placeholders={"url": FEES_URL},
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> WavOsterholzOptionsFlow:
        """Return the options flow."""
        return WavOsterholzOptionsFlow()


class WavOsterholzOptionsFlow(OptionsFlow):
    """Allow the water meter size to be changed after setup."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self.config_entry.options.get(CONF_METER_SIZE, DEFAULT_METER_SIZE)
        return self.async_show_form(
            step_id="init",
            data_schema=_schema(
                self.config_entry.data[CONF_MUNICIPALITY], current
            ),
        )
