# File version: 2025-06-05 0.2.0
import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.const import STATE_ON, STATE_OFF

from .const import (
    DOMAIN, DEFAULT_NAME,
    ENTITY_ID_SUFFIX_SMART_ENABLE_SWITCH,
    ENTITY_ID_SUFFIX_ENABLE_SOLAR_CHARGING_SWITCH
)

_LOGGER = logging.getLogger(f"custom_components.{DOMAIN}") # Använd komponent-specifik logger

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the switch platform for Smart EV Charging."""
    _LOGGER.debug("SWITCH PLATFORM: async_setup_entry startar.")
    try:
        smart_switch = SmartChargingEnableSwitch(config_entry)
        _LOGGER.debug("SWITCH PLATFORM: SmartChargingEnableSwitch skapad: %s", smart_switch.name)

        solar_switch = EnableSolarSurplusChargingSwitch(config_entry)
        _LOGGER.debug("SWITCH PLATFORM: EnableSolarSurplusChargingSwitch skapad: %s", solar_switch.name)

        entities_to_add = [smart_switch, solar_switch]
        async_add_entities(entities_to_add, True) # True för att återställa tillstånd
        _LOGGER.debug("SWITCH PLATFORM: async_add_entities har anropats för %s entiteter.", len(entities_to_add))
    except Exception as e:
        _LOGGER.error("SWITCH PLATFORM: Fel under async_setup_entry: %s", e, exc_info=True)


class SmartChargingBaseSwitch(SwitchEntity, RestoreEntity):
    """Base class for restorable switches in this integration."""
    _attr_should_poll = False # Vi förlitar oss på att HA anropar turn_on/off och återställning

    def __init__(self, config_entry: ConfigEntry, entity_id_suffix: str, name_suffix: str, default_icon: str | None = None, default_state_on: bool = False) -> None:
        """Initialize the base switch."""
        self._config_entry = config_entry
        self._attr_is_on = default_state_on # Standard PÅ/AV-läge vid första start utan sparat tillstånd

        self._attr_unique_id = f"{config_entry.entry_id}_{entity_id_suffix}"
        self._attr_name = f"{DEFAULT_NAME} {name_suffix}"
        if default_icon:
            self._attr_icon = default_icon

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry.entry_id)},
            name=DEFAULT_NAME,
            manufacturer="AllehJ Integrationer",
            model="Smart EV Charger Control",
            entry_type="service"
        )
        _LOGGER.debug("%s initialiserad med unique_id: %s. Initialt _attr_is_on: %s", self.name, self.unique_id, self._attr_is_on)

    async def async_added_to_hass(self) -> None:
        """Körs när entiteten läggs till i Home Assistant. Återställ tidigare tillstånd."""
        await super().async_added_to_hass() # Viktigt anrop till basklassen RestoreEntity

        last_state: State | None = await self.async_get_last_state()

        _LOGGER.debug("RestoreState för %s (unique_id: %s): last_state är %s",
                        self.name, self.unique_id, last_state.state if last_state else "None")

        if last_state is not None and last_state.state is not None:
            if last_state.state == STATE_ON:
                self._attr_is_on = True
            elif last_state.state == STATE_OFF:
                self._attr_is_on = False
            else:
                _LOGGER.warning("Oväntat sparat tillstånd '%s' för %s (%s), använder default: %s.",
                                last_state.state, self.name, self.unique_id, self._attr_is_on)
                # self._attr_is_on behåller sitt defaultvärde från __init__
        else:
            _LOGGER.debug("Inget giltigt sparat tillstånd hittades för %s (%s), använder default: %s",
                            self.name, self.unique_id, self._attr_is_on)
        # Ingen async_write_ha_state() här, det sköts av HA när den läser initialt tillstånd

    @property
    def is_on(self) -> bool | None:
        """Return true if switch is on."""
        return self._attr_is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        if not self._attr_is_on:
            self._attr_is_on = True
            self.async_write_ha_state() # Meddela HA om ändringen
            _LOGGER.info("%s ställd till PÅ", self.name)
        else:
            _LOGGER.debug("%s var redan PÅ, ingen åtgärd.", self.name)


    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        if self._attr_is_on:
            self._attr_is_on = False
            self.async_write_ha_state() # Meddela HA om ändringen
            _LOGGER.info("%s ställd till AV", self.name)
        else:
            _LOGGER.debug("%s var redan AV, ingen åtgärd.", self.name)


class SmartChargingEnableSwitch(SmartChargingBaseSwitch):
    """Switch to enable/disable general smart charging (price/time based)."""
    def __init__(self, config_entry: ConfigEntry) -> None:
        super().__init__(
            config_entry,
            ENTITY_ID_SUFFIX_SMART_ENABLE_SWITCH,
            "Smart Laddning Aktiv", # Tydligare namn
            "mdi:auto-mode",
            default_state_on=False # Standard AV
        )

class EnableSolarSurplusChargingSwitch(SmartChargingBaseSwitch):
    """Switch to enable/disable solar surplus charging mode."""
    def __init__(self, config_entry: ConfigEntry) -> None:
        super().__init__(
            config_entry,
            ENTITY_ID_SUFFIX_ENABLE_SOLAR_CHARGING_SWITCH,
            "Aktivera Solenergiladdning", # Tydligare namn
            "mdi:solar-panel-large",
            default_state_on=False # Standard AV
        )