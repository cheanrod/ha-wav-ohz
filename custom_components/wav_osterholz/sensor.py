"""Sensor platform for the WAV Osterholz integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import WavOsterholzConfigEntry
from .const import (
    CONF_METER_SIZE,
    CONF_MUNICIPALITY,
    CURRENCY_PER_CUBIC_METER,
    CURRENCY_PER_MONTH,
    DEFAULT_METER_SIZE,
    DOMAIN,
    METER_SIZES,
    MUNICIPALITIES,
    NO_DRINKING_WATER_MUNICIPALITIES,
    SEPTIC_MUNICIPALITIES,
)
from .coordinator import WavOsterholzCoordinator
from .parser import Fee, FeeSchedule

# Sensor states are the gross amounts -- what a household actually pays. The net
# amount is exposed as an attribute for anyone doing their own VAT arithmetic.


def _water_base_fee(schedule: FeeSchedule, meter_size: str) -> Fee | None:
    return schedule.water_base_fees.get(meter_size)


def _wastewater_base_fee(schedule: FeeSchedule, meter_size: str) -> Fee | None:
    return schedule.wastewater_base_fees.get(meter_size)


def _wastewater_price(schedule: FeeSchedule, municipality: str) -> Fee | None:
    return schedule.wastewater_prices.get(municipality)


def _fee_attrs(fee: Fee | None, valid_from: str | None) -> dict[str, Any]:
    """Standard attributes for a single fee."""
    attrs: dict[str, Any] = {}
    # Wastewater carries no VAT, so a net amount equal to the state would only
    # be noise; it is worth showing only where VAT actually applies.
    if fee is not None and fee.net != fee.gross:
        attrs["price_net"] = fee.net
    if valid_from is not None:
        attrs["valid_from"] = valid_from
    return attrs


def _sum(*fees: Fee | None) -> float | None:
    """Add gross amounts, returning None if any component is missing."""
    if any(fee is None for fee in fees):
        return None
    return round(sum(fee.gross for fee in fees if fee is not None), 4)


@dataclass(frozen=True, kw_only=True)
class WavSensorEntityDescription(SensorEntityDescription):
    """Describes a WAV Osterholz sensor."""

    value_fn: Callable[[FeeSchedule, str, str], float | None]
    attrs_fn: Callable[[FeeSchedule, str, str], dict[str, Any]] = field(
        default=lambda schedule, municipality, meter_size: {}
    )
    # Whether this sensor applies to the configured municipality at all.
    applies_to: Callable[[str], bool] = field(default=lambda municipality: True)


SENSORS: tuple[WavSensorEntityDescription, ...] = (
    WavSensorEntityDescription(
        key="water_price",
        translation_key="water_price",
        native_unit_of_measurement=CURRENCY_PER_CUBIC_METER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        icon="mdi:water",
        applies_to=lambda municipality: municipality
        not in NO_DRINKING_WATER_MUNICIPALITIES,
        value_fn=lambda schedule, municipality, meter_size: (
            schedule.water_price.gross if schedule.water_price else None
        ),
        attrs_fn=lambda schedule, municipality, meter_size: _fee_attrs(
            schedule.water_price, schedule.water_price_valid_from
        ),
    ),
    WavSensorEntityDescription(
        key="water_base_fee",
        translation_key="water_base_fee",
        native_unit_of_measurement=CURRENCY_PER_MONTH,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        icon="mdi:water-outline",
        applies_to=lambda municipality: municipality
        not in NO_DRINKING_WATER_MUNICIPALITIES,
        value_fn=lambda schedule, municipality, meter_size: (
            fee.gross if (fee := _water_base_fee(schedule, meter_size)) else None
        ),
        attrs_fn=lambda schedule, municipality, meter_size: {
            **_fee_attrs(
                _water_base_fee(schedule, meter_size),
                schedule.water_base_fee_valid_from,
            ),
            "meter_size": METER_SIZES.get(meter_size, meter_size),
        },
    ),
    WavSensorEntityDescription(
        key="submeter_base_fee",
        translation_key="submeter_base_fee",
        native_unit_of_measurement=CURRENCY_PER_MONTH,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        icon="mdi:sprinkler-variant",
        entity_registry_enabled_default=False,
        applies_to=lambda municipality: municipality
        not in NO_DRINKING_WATER_MUNICIPALITIES,
        value_fn=lambda schedule, municipality, meter_size: (
            schedule.submeter_base_fee.gross if schedule.submeter_base_fee else None
        ),
        attrs_fn=lambda schedule, municipality, meter_size: _fee_attrs(
            schedule.submeter_base_fee, schedule.submeter_valid_from
        ),
    ),
    WavSensorEntityDescription(
        key="wastewater_price",
        translation_key="wastewater_price",
        native_unit_of_measurement=CURRENCY_PER_CUBIC_METER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        icon="mdi:pipe-disconnected",
        value_fn=lambda schedule, municipality, meter_size: (
            fee.gross if (fee := _wastewater_price(schedule, municipality)) else None
        ),
        attrs_fn=lambda schedule, municipality, meter_size: {
            **_fee_attrs(
                _wastewater_price(schedule, municipality),
                schedule.wastewater_valid_from,
            ),
            "municipality": MUNICIPALITIES.get(municipality, municipality),
        },
    ),
    WavSensorEntityDescription(
        key="wastewater_base_fee",
        translation_key="wastewater_base_fee",
        native_unit_of_measurement=CURRENCY_PER_MONTH,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        icon="mdi:pipe",
        value_fn=lambda schedule, municipality, meter_size: (
            fee.gross if (fee := _wastewater_base_fee(schedule, meter_size)) else None
        ),
        attrs_fn=lambda schedule, municipality, meter_size: {
            **_fee_attrs(
                _wastewater_base_fee(schedule, meter_size),
                schedule.wastewater_valid_from,
            ),
            "meter_size": METER_SIZES.get(meter_size, meter_size),
        },
    ),
    # The headline sensor: what one cubic metre of tap water really costs once
    # it has been drunk and drained again. Multiply your water meter by this.
    WavSensorEntityDescription(
        key="total_price",
        translation_key="total_price",
        native_unit_of_measurement=CURRENCY_PER_CUBIC_METER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        icon="mdi:cash-multiple",
        applies_to=lambda municipality: municipality
        not in NO_DRINKING_WATER_MUNICIPALITIES,
        value_fn=lambda schedule, municipality, meter_size: _sum(
            schedule.water_price, _wastewater_price(schedule, municipality)
        ),
        attrs_fn=lambda schedule, municipality, meter_size: {
            "water_price": (
                schedule.water_price.gross if schedule.water_price else None
            ),
            "wastewater_price": (
                fee.gross if (fee := _wastewater_price(schedule, municipality)) else None
            ),
        },
    ),
    WavSensorEntityDescription(
        key="total_base_fee",
        translation_key="total_base_fee",
        native_unit_of_measurement=CURRENCY_PER_MONTH,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        icon="mdi:cash-clock",
        applies_to=lambda municipality: municipality
        not in NO_DRINKING_WATER_MUNICIPALITIES,
        value_fn=lambda schedule, municipality, meter_size: _sum(
            _water_base_fee(schedule, meter_size),
            _wastewater_base_fee(schedule, meter_size),
        ),
        attrs_fn=lambda schedule, municipality, meter_size: {
            "water_base_fee": (
                fee.gross if (fee := _water_base_fee(schedule, meter_size)) else None
            ),
            "wastewater_base_fee": (
                fee.gross
                if (fee := _wastewater_base_fee(schedule, meter_size))
                else None
            ),
            "meter_size": METER_SIZES.get(meter_size, meter_size),
        },
    ),
    WavSensorEntityDescription(
        key="septic_pit_price",
        translation_key="septic_pit_price",
        native_unit_of_measurement=CURRENCY_PER_CUBIC_METER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        icon="mdi:tanker-truck",
        entity_registry_enabled_default=False,
        applies_to=lambda municipality: municipality in SEPTIC_MUNICIPALITIES,
        value_fn=lambda schedule, municipality, meter_size: (
            schedule.septic_pit_price.gross if schedule.septic_pit_price else None
        ),
    ),
    WavSensorEntityDescription(
        key="septic_plant_price",
        translation_key="septic_plant_price",
        native_unit_of_measurement=CURRENCY_PER_CUBIC_METER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        icon="mdi:tanker-truck",
        entity_registry_enabled_default=False,
        applies_to=lambda municipality: municipality in SEPTIC_MUNICIPALITIES,
        value_fn=lambda schedule, municipality, meter_size: (
            schedule.septic_plant_price.gross if schedule.septic_plant_price else None
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WavOsterholzConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensors for a config entry."""
    coordinator = entry.runtime_data
    municipality = entry.data[CONF_MUNICIPALITY]

    async_add_entities(
        WavOsterholzSensor(coordinator, entry, description)
        for description in SENSORS
        if description.applies_to(municipality)
    )


class WavOsterholzSensor(CoordinatorEntity[WavOsterholzCoordinator], SensorEntity):
    """A single fee published by the WAV Osterholz."""

    _attr_has_entity_name = True
    entity_description: WavSensorEntityDescription

    def __init__(
        self,
        coordinator: WavOsterholzCoordinator,
        entry: WavOsterholzConfigEntry,
        description: WavSensorEntityDescription,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"WAV Osterholz ({MUNICIPALITIES.get(entry.data[CONF_MUNICIPALITY])})",
            manufacturer="Wasser- und Abwasserverband Osterholz",
            model="Gebührenübersicht",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://wav-osterholz.de/gebuehren/",
        )

    @property
    def _municipality(self) -> str:
        return self._entry.data[CONF_MUNICIPALITY]

    @property
    def _meter_size(self) -> str:
        return self._entry.options.get(CONF_METER_SIZE, DEFAULT_METER_SIZE)

    @property
    def native_value(self) -> float | None:
        """Return the fee."""
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(
            self.coordinator.data, self._municipality, self._meter_size
        )

    @property
    def available(self) -> bool:
        """Only report available while this particular fee is on the page."""
        return super().available and self.native_value is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the net amount, validity date and other context."""
        if self.coordinator.data is None:
            return None
        attrs = self.entity_description.attrs_fn(
            self.coordinator.data, self._municipality, self._meter_size
        )
        return {key: value for key, value in attrs.items() if value is not None} or None
