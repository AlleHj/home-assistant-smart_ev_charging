# File version: 2025-06-05 0.2.0
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.const import STATE_UNKNOWN
# import homeassistant.util.dt as dt_util # Behövs inte längre här

from .const import (
    DOMAIN,
    DEFAULT_NAME,
    # ENTITY_ID_SUFFIX_SESSION_ENERGY_SENSOR, # Borttagen
    # ENTITY_ID_SUFFIX_SESSION_COST_SENSOR, # Borttagen
    ENTITY_ID_SUFFIX_ACTIVE_CONTROL_MODE_SENSOR,
)
from .coordinator import SmartEVChargingCoordinator

_LOGGER = logging.getLogger(f"custom_components.{DOMAIN}")


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Konfigurerar sensorplattformen för Smart EV Charging."""
    _LOGGER.debug("SENSOR PLATFORM: async_setup_entry startar.")
    coordinator_data = hass.data.get(DOMAIN, {}).get(config_entry.entry_id, {})
    coordinator: SmartEVChargingCoordinator | None = coordinator_data.get("coordinator")

    if not coordinator:
        _LOGGER.error(
            "Koordinatorn är inte tillgänglig för sensor-setup! Detta bör inte hända."
        )
        return

    entities_to_add = [
        ActiveControlModeSensor(config_entry, coordinator),
        # SessionEnergySensor och SessionCostSensor tas bort
    ]
    async_add_entities(entities_to_add)
    _LOGGER.debug("SENSOR PLATFORM: %s entiteter tillagda.", len(entities_to_add))


class SmartChargingBaseSensor(
    CoordinatorEntity[SmartEVChargingCoordinator], SensorEntity
):
    """Basklass för sensorer i Smart EV Charging."""

    def __init__(
        self,
        config_entry: ConfigEntry,
        coordinator: SmartEVChargingCoordinator,
        entity_suffix: str,
    ) -> None:
        """Initialisera bassensorn."""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._attr_unique_id = f"{config_entry.entry_id}_{entity_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry.entry_id)},
            name=DEFAULT_NAME,
            manufacturer="Custom Component",
            model="Smart EV Charging",
            entry_type="service",  # DeviceEntryType.SERVICE är korrekt enum, men sträng accepteras.
        )

    @property
    def available(self) -> bool:
        """Returnerar true om koordinatorn är tillgänglig och har data."""
        return (
            super().available
            and self.coordinator.last_update_success
            and self.coordinator.data is not None
        )


# Klasserna SessionEnergySensor och SessionCostSensor tas bort helt.


class ActiveControlModeSensor(SmartChargingBaseSensor):
    """Sensor som visar det aktiva styrningsläget."""

    _attr_icon = "mdi:robot-happy-outline"  # Eller mdi:auto-mode

    def __init__(
        self, config_entry: ConfigEntry, coordinator: SmartEVChargingCoordinator
    ) -> None:
        """Initialisera sensorn för aktivt styrningsläge."""
        super().__init__(
            config_entry, coordinator, ENTITY_ID_SUFFIX_ACTIVE_CONTROL_MODE_SENSOR
        )
        self._attr_name = f"{DEFAULT_NAME} Aktivt Styrningsläge"
        self._attr_native_value: str = STATE_UNKNOWN  # Initialt värde
        _LOGGER.info("%s initialiserad", self.name)
        # Uppdatera initialt värde vid start
        self._handle_coordinator_update()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Hanterar datauppdateringar från koordinatorn."""
        if self.coordinator.data:
            new_value = str(
                self.coordinator.data.get("active_control_mode", STATE_UNKNOWN)
            )
            if self._attr_native_value != new_value:
                self._attr_native_value = new_value
                _LOGGER.debug("%s uppdaterad: Värde=%s", self.name, new_value)
                if self.hass:  # Säkerställ att hass är tillgängligt (ska vara det efter added_to_hass)
                    self.async_write_ha_state()
        elif (
            self._attr_native_value != STATE_UNKNOWN
        ):  # Om data saknas, sätt till okänd
            self._attr_native_value = STATE_UNKNOWN
            _LOGGER.debug("%s uppdaterad: Data saknas, Värde=Okänd", self.name)
            if self.hass:
                self.async_write_ha_state()
