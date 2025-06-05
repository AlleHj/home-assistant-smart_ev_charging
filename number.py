# File version: 2025-06-05 0.2.0
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
    ENTITY_ID_SUFFIX_MIN_SOLAR_CHARGE_CURRENT_A_NUMBER
)

_LOGGER = logging.getLogger(f"custom_components.{DOMAIN}") # Använd komponent-specifik logger

DEFAULT_MAX_PRICE = 1.5
MIN_PRICE = 0.0
MAX_PRICE = 10.0
PRICE_STEP = 0.01

DEFAULT_SOLAR_BUFFER = 50
MIN_SOLAR_BUFFER = 0
MAX_SOLAR_BUFFER = 2000
SOLAR_BUFFER_STEP = 10

DEFAULT_MIN_SOLAR_CURRENT_A = 6
MIN_SOLAR_CURRENT_A = 1 # Minsta möjliga för de flesta system är 6A, men tillåt lägre för flexibilitet.
MAX_SOLAR_CURRENT_A = 16
SOLAR_CURRENT_A_STEP = 1

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the number platform for Smart EV Charging."""
    _LOGGER.debug("NUMBER PLATFORM: async_setup_entry startar.")
    entities_to_add = [
        MaxPriceNumberEntity(config_entry),
        SolarSurplusBufferNumberEntity(config_entry),
        MinSolarChargeCurrentNumberEntity(config_entry)
    ]
    async_add_entities(entities_to_add, True) # True för att indikera att entiteterna ska återställas
    _LOGGER.debug("NUMBER PLATFORM: %s entiteter tillagda.", len(entities_to_add))

class MaxPriceNumberEntity(RestoreNumber, NumberEntity):
    _attr_should_poll = False
    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry
        self._attr_unique_id = f"{config_entry.entry_id}_{ENTITY_ID_SUFFIX_MAX_PRICE_NUMBER}"
        self._attr_name = f"{DEFAULT_NAME} Max Elpris"
        self._attr_native_min_value = MIN_PRICE
        self._attr_native_max_value = MAX_PRICE
        self._attr_native_step = PRICE_STEP
        self._attr_native_unit_of_measurement = "SEK/kWh" # Antag SEK, enheten kan behöva vara mer dynamisk
        self._attr_mode = NumberMode.BOX
        self._attr_icon = "mdi:currency-usd"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry.entry_id)}, name=DEFAULT_NAME, manufacturer="AllehJ Integrationer", model="Smart EV Charger Control", entry_type="service"
        )
        self._attr_native_value: float | None = None # Initiera som None
        _LOGGER.info("%s initialiserad", self.name)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_number_data = await self.async_get_last_number_data()
        if last_number_data is not None and last_number_data.native_value is not None:
            self._attr_native_value = last_number_data.native_value
            _LOGGER.debug("Återställt värde för %s till: %s", self.unique_id, self._attr_native_value)
        elif self._attr_native_value is None: # Om inget återställt och inte satt i init
            self._attr_native_value = DEFAULT_MAX_PRICE
            _LOGGER.debug("Inget sparat värde för %s, sätter till default: %s", self.unique_id, self._attr_native_value)
        # self.async_write_ha_state() # Behövs inte här, sker vid set_native_value eller om HA begär det

    async def async_set_native_value(self, value: float) -> None:
        if value is None:
            _LOGGER.warning("Försökte sätta None-värde för %s, ignorerar.", self.name)
            return

        if self._attr_native_min_value <= value <= self._attr_native_max_value:
            self._attr_native_value = round(value, len(str(PRICE_STEP).split('.')[-1]) if '.' in str(PRICE_STEP) else 0) # Avrunda till stegprecision
            self.async_write_ha_state()
            _LOGGER.info("%s satt till: %s %s", self.name, self._attr_native_value, self._attr_native_unit_of_measurement)
        else: _LOGGER.warning("Ogiltigt värde för %s: %s. Tillåtet intervall: %s-%s.", self.name, value, self._attr_native_min_value, self._attr_native_max_value)

class SolarSurplusBufferNumberEntity(RestoreNumber, NumberEntity):
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
            identifiers={(DOMAIN, config_entry.entry_id)}, name=DEFAULT_NAME, manufacturer="AllehJ Integrationer", model="Smart EV Charger Control", entry_type="service"
        )
        self._attr_native_value: float | None = None
        _LOGGER.info("%s initialiserad", self.name)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_number_data = await self.async_get_last_number_data()
        if last_number_data is not None and last_number_data.native_value is not None:
            self._attr_native_value = last_number_data.native_value
            _LOGGER.debug("Återställt värde för %s till: %s", self.unique_id, self._attr_native_value)
        elif self._attr_native_value is None:
            self._attr_native_value = DEFAULT_SOLAR_BUFFER
            _LOGGER.debug("Inget sparat värde för %s, sätter till default: %s", self.unique_id, self._attr_native_value)

    async def async_set_native_value(self, value: float) -> None:
        if value is None:
            _LOGGER.warning("Försökte sätta None-värde för %s, ignorerar.", self.name)
            return
        if self._attr_native_min_value <= value <= self._attr_native_max_value:
            self._attr_native_value = round(value / SOLAR_BUFFER_STEP) * SOLAR_BUFFER_STEP # Säkerställ att det är en jämn multipel av steget
            self.async_write_ha_state()
            _LOGGER.info("%s satt till: %s %s", self.name, self._attr_native_value, self._attr_native_unit_of_measurement)
        else: _LOGGER.warning("Ogiltigt värde för %s: %s. Tillåtet intervall: %s-%s.", self.name, value, self._attr_native_min_value, self._attr_native_max_value)

class MinSolarChargeCurrentNumberEntity(RestoreNumber, NumberEntity):
    _attr_should_poll = False
    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry
        self._attr_unique_id = f"{config_entry.entry_id}_{ENTITY_ID_SUFFIX_MIN_SOLAR_CHARGE_CURRENT_A_NUMBER}"
        self._attr_name = f"{DEFAULT_NAME} Minsta Laddström Solenergi"
        self._attr_native_min_value = MIN_SOLAR_CURRENT_A
        self._attr_native_max_value = MAX_SOLAR_CURRENT_A
        self._attr_native_step = SOLAR_CURRENT_A_STEP
        self._attr_native_unit_of_measurement = "A"
        self._attr_mode = NumberMode.BOX
        self._attr_icon = "mdi:current-ac"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry.entry_id)}, name=DEFAULT_NAME, manufacturer="AllehJ Integrationer", model="Smart EV Charger Control", entry_type="service"
        )
        self._attr_native_value: float | None = None
        _LOGGER.info("%s initialiserad", self.name)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_number_data = await self.async_get_last_number_data()
        if last_number_data is not None and last_number_data.native_value is not None:
            self._attr_native_value = last_number_data.native_value
            _LOGGER.debug("Återställt värde för %s till: %s", self.unique_id, self._attr_native_value)
        elif self._attr_native_value is None:
            self._attr_native_value = DEFAULT_MIN_SOLAR_CURRENT_A
            _LOGGER.debug("Inget sparat värde för %s, sätter till default: %s", self.unique_id, self._attr_native_value)

    async def async_set_native_value(self, value: float) -> None:
        if value is None:
            _LOGGER.warning("Försökte sätta None-värde för %s, ignorerar.", self.name)
            return
        if self._attr_native_min_value <= value <= self._attr_native_max_value:
            self._attr_native_value = round(value / SOLAR_CURRENT_A_STEP) * SOLAR_CURRENT_A_STEP
            self.async_write_ha_state()
            _LOGGER.info("%s satt till: %s %s", self.name, self._attr_native_value, self._attr_native_unit_of_measurement)
        else: _LOGGER.warning("Ogiltigt värde för %s: %s. Tillåtet intervall: %s-%s A.", self.name, value, self._attr_native_min_value, self._attr_native_max_value)