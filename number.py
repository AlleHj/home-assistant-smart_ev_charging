# File version: 2025-05-18.3
import logging
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode, RestoreNumber
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceInfo

from .const import (
    DOMAIN, DEFAULT_NAME, 
    ENTITY_ID_SUFFIX_MAX_PRICE_NUMBER, 
    ENTITY_ID_SUFFIX_SOLAR_BUFFER_NUMBER,
    ENTITY_ID_SUFFIX_MIN_SOLAR_CHARGE_CURRENT_A_NUMBER # <--- LADE TILL SUFFIX
)

_LOGGER = logging.getLogger(__name__)

DEFAULT_MAX_PRICE = 1.5
MIN_PRICE = 0.0
MAX_PRICE = 10.0
PRICE_STEP = 0.01

DEFAULT_SOLAR_BUFFER = 50
MIN_SOLAR_BUFFER = 0
MAX_SOLAR_BUFFER = 2000
SOLAR_BUFFER_STEP = 10

DEFAULT_MIN_SOLAR_CURRENT_A = 6 # <--- NY KONSTANT
MIN_SOLAR_CURRENT_A = 1
MAX_SOLAR_CURRENT_A = 16 # Max vad de flesta laddare/bilar kan ta på lägsta effekt per fas.
SOLAR_CURRENT_A_STEP = 1

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the number platform for Smart EV Charging."""
    entities_to_add = [
        MaxPriceNumberEntity(config_entry),
        SolarSurplusBufferNumberEntity(config_entry),
        MinSolarChargeCurrentNumberEntity(config_entry) # <--- LADE TILL DEN NYA ENTITETEN
    ]
    async_add_entities(entities_to_add, True)

class MaxPriceNumberEntity(RestoreNumber, NumberEntity):
    # ... (ingen ändring i denna klass) ...
    _attr_should_poll = False
    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry
        self._attr_unique_id = f"{config_entry.entry_id}_{ENTITY_ID_SUFFIX_MAX_PRICE_NUMBER}"
        self._attr_name = f"{DEFAULT_NAME} Max Elpris"
        self._attr_native_min_value = MIN_PRICE
        self._attr_native_max_value = MAX_PRICE
        self._attr_native_step = PRICE_STEP
        self._attr_native_unit_of_measurement = "SEK/kWh"
        self._attr_mode = NumberMode.BOX
        self._attr_icon = "mdi:currency-usd"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry.entry_id)}, name=DEFAULT_NAME, manufacturer="Din Tillverkare", model="Smart EV Charger Control", entry_type="service"
        )
        self._attr_native_value: float | None = None
        _LOGGER.info("%s initialiserad", self.name)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_number_data = await self.async_get_last_number_data()
        if last_number_data is not None: self._attr_native_value = last_number_data.native_value
        elif self._attr_native_value is None: self._attr_native_value = DEFAULT_MAX_PRICE
        _LOGGER.debug("Värde för %s satt/återställt till: %s", self.unique_id, self._attr_native_value)

    async def async_set_native_value(self, value: float) -> None:
        if value is None: return
        if self._attr_native_min_value <= value <= self._attr_native_max_value:
            self._attr_native_value = value
            self.async_write_ha_state()
            _LOGGER.info("%s satt till: %s SEK/kWh", self.name, value)
        else: _LOGGER.warning("Ogiltigt värde för %s: %s", self.name, value)

class SolarSurplusBufferNumberEntity(RestoreNumber, NumberEntity):
    # ... (ingen ändring i denna klass) ...
    _attr_should_poll = False
    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry
        self._attr_unique_id = f"{config_entry.entry_id}_{ENTITY_ID_SUFFIX_SOLAR_BUFFER_NUMBER}"
        self._attr_name = f"{DEFAULT_NAME} Solenergi Buffer"
        self._attr_native_min_value = MIN_SOLAR_BUFFER
        self._attr_native_max_value = MAX_SOLAR_BUFFER
        self._attr_native_step = SOLAR_BUFFER_STEP
        self._attr_native_unit_of_measurement = "W"
        self._attr_mode = NumberMode.BOX
        self._attr_icon = "mdi:solar-power-variant-outline"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry.entry_id)}, name=DEFAULT_NAME, manufacturer="Din Tillverkare", model="Smart EV Charger Control", entry_type="service"
        )
        self._attr_native_value: float | None = None
        _LOGGER.info("%s initialiserad", self.name)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_number_data = await self.async_get_last_number_data()
        if last_number_data is not None: self._attr_native_value = last_number_data.native_value
        elif self._attr_native_value is None: self._attr_native_value = DEFAULT_SOLAR_BUFFER
        _LOGGER.debug("Värde för %s satt/återställt till: %s", self.unique_id, self._attr_native_value)

    async def async_set_native_value(self, value: float) -> None:
        if value is None: return
        if self._attr_native_min_value <= value <= self._attr_native_max_value:
            self._attr_native_value = value
            self.async_write_ha_state()
            _LOGGER.info("%s satt till: %s W", self.name, value)
        else: _LOGGER.warning("Ogiltigt värde för %s: %s", self.name, value)

class MinSolarChargeCurrentNumberEntity(RestoreNumber, NumberEntity): # <--- NY KLASS
    """Number entity to set the minimum solar charging current in Amperes."""
    _attr_should_poll = False

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize the number entity."""
        self._config_entry = config_entry
        
        self._attr_unique_id = f"{config_entry.entry_id}_{ENTITY_ID_SUFFIX_MIN_SOLAR_CHARGE_CURRENT_A_NUMBER}"
        self._attr_name = f"{DEFAULT_NAME} Minsta Laddström Solenergi"
        
        self._attr_native_min_value = MIN_SOLAR_CURRENT_A
        self._attr_native_max_value = MAX_SOLAR_CURRENT_A
        self._attr_native_step = SOLAR_CURRENT_A_STEP
        self._attr_native_unit_of_measurement = "A" # Ampere
        self._attr_mode = NumberMode.BOX 
        self._attr_icon = "mdi:current-ac"
        
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry.entry_id)},
            name=DEFAULT_NAME,
            manufacturer="Din Tillverkare",
            model="Smart EV Charger Control",
            entry_type="service",
        )
        
        self._attr_native_value: float | None = None
        _LOGGER.info("%s initialiserad", self.name)

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()
        last_number_data = await self.async_get_last_number_data()
        if last_number_data is not None:
            self._attr_native_value = last_number_data.native_value
        elif self._attr_native_value is None: # Om inget återställt värde och inget tidigare värde
            self._attr_native_value = DEFAULT_MIN_SOLAR_CURRENT_A # Sätt till standardvärde
        _LOGGER.debug("Värde för %s satt/återställt till: %s A", self.unique_id, self._attr_native_value)

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        if value is None: return
            
        if self._attr_native_min_value <= value <= self._attr_native_max_value:
            self._attr_native_value = value
            self.async_write_ha_state()
            _LOGGER.info("%s satt till: %s A", self.name, value)
        else:
            _LOGGER.warning(
                "Försökte sätta ogiltigt värde för %s: %s. Tillåtet intervall: %s-%s A.",
                self.name, value, self._attr_native_min_value, self._attr_native_max_value
            )