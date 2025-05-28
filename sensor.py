# File version: 2025-05-29 0.1.10
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
import homeassistant.util.dt as dt_util

from .const import (
    DOMAIN,
    DEFAULT_NAME,
    ENTITY_ID_SUFFIX_SESSION_ENERGY_SENSOR,
    ENTITY_ID_SUFFIX_SESSION_COST_SENSOR,
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
            "Koordinatorn är inte tillgänglig för sensor-setup! Kontrollera __init__.py och koordinatorns initiering."
        )
        return

    sensors_to_add = [
        SmartChargingSessionEnergySensor(config_entry, coordinator),
        SmartChargingSessionCostSensor(config_entry, coordinator),
        ActiveControlModeSensor(config_entry, coordinator),
    ]
    async_add_entities(sensors_to_add, False)
    _LOGGER.debug("SENSOR PLATFORM: %s sensorer tillagda.", len(sensors_to_add))


class SmartChargingBaseSensor(
    CoordinatorEntity[SmartEVChargingCoordinator], SensorEntity
):
    """Basklass för sensorer i denna integration som använder DataUpdateCoordinator."""

    def __init__(
        self,
        config_entry: ConfigEntry,
        coordinator: SmartEVChargingCoordinator,
        sensor_type_suffix: str,
    ) -> None:
        """Initialiserar bassensorn."""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._attr_unique_id = f"{config_entry.entry_id}_{sensor_type_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry.entry_id)},
            name=DEFAULT_NAME,
            manufacturer="AllehJ Integrationer",
            model="Smart EV Charger Control",
            entry_type="service",
        )


class SmartChargingSessionEnergySensor(SmartChargingBaseSensor):
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "kWh"
    _attr_icon = "mdi:lightning-bolt"

    def __init__(
        self, config_entry: ConfigEntry, coordinator: SmartEVChargingCoordinator
    ) -> None:
        super().__init__(
            config_entry, coordinator, ENTITY_ID_SUFFIX_SESSION_ENERGY_SENSOR
        )
        self._attr_name = f"{DEFAULT_NAME} Session Energi"
        self._attr_native_value: float | None = 0.0
        self._attr_last_reset: dt_util.dt.datetime | None = dt_util.utcnow()
        _LOGGER.info("%s initialiserad", self.name)
        # Ta bort: self._handle_coordinator_update() # Anropas automatiskt av CoordinatorEntity

    @callback
    def _handle_coordinator_update(self) -> None:
        """Hanterar datauppdateringar från koordinatorn."""
        if self.coordinator.data:
            new_value = self.coordinator.data.get("session_energy_kwh", 0.0)
            session_start_str = self.coordinator.data.get("session_start_time_utc")

            if session_start_str:
                new_last_reset = dt_util.parse_datetime(session_start_str)
                if self._attr_last_reset != new_last_reset:
                    self._attr_last_reset = new_last_reset
            elif self._attr_last_reset is None:
                self._attr_last_reset = dt_util.utcnow()

            self._attr_native_value = new_value
            _LOGGER.debug(
                "%s uppdaterad: Värde=%.3f kWh, LastReset=%s",
                self.name,
                new_value,
                self._attr_last_reset,
            )
        else:
            self._attr_native_value = 0.0
        if self.hass:
            self.async_write_ha_state()


class SmartChargingSessionCostSensor(SmartChargingBaseSensor):
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "SEK"
    _attr_icon = "mdi:cash"

    def __init__(
        self, config_entry: ConfigEntry, coordinator: SmartEVChargingCoordinator
    ) -> None:
        super().__init__(
            config_entry, coordinator, ENTITY_ID_SUFFIX_SESSION_COST_SENSOR
        )
        self._attr_name = f"{DEFAULT_NAME} Session Kostnad"
        self._attr_native_value: float | None = 0.0
        self._attr_last_reset: dt_util.dt.datetime | None = dt_util.utcnow()
        _LOGGER.info("%s initialiserad", self.name)
        # Ta bort: self._handle_coordinator_update()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Hanterar datauppdateringar från koordinatorn."""
        if self.coordinator.data:
            new_value = self.coordinator.data.get("session_cost_sek", 0.0)
            session_start_str = self.coordinator.data.get("session_start_time_utc")

            if session_start_str:
                new_last_reset = dt_util.parse_datetime(session_start_str)
                if self._attr_last_reset != new_last_reset:
                    self._attr_last_reset = new_last_reset
            elif self._attr_last_reset is None:
                self._attr_last_reset = dt_util.utcnow()

            self._attr_native_value = new_value
            _LOGGER.debug(
                "%s uppdaterad: Värde=%.2f %s, LastReset=%s",
                self.name,
                new_value,
                self._attr_native_unit_of_measurement,
                self._attr_last_reset,
            )
        else:
            self._attr_native_value = 0.0
        if self.hass:
            self.async_write_ha_state()


class ActiveControlModeSensor(SmartChargingBaseSensor):
    _attr_icon = "mdi:robot-happy-outline"

    def __init__(
        self, config_entry: ConfigEntry, coordinator: SmartEVChargingCoordinator
    ) -> None:
        super().__init__(
            config_entry, coordinator, ENTITY_ID_SUFFIX_ACTIVE_CONTROL_MODE_SENSOR
        )
        self._attr_name = f"{DEFAULT_NAME} Aktivt Styrningsläge"
        self._attr_native_value: str = STATE_UNKNOWN
        _LOGGER.info("%s initialiserad", self.name)
        # Ta bort: self._handle_coordinator_update()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Hanterar datauppdateringar från koordinatorn."""
        if self.coordinator.data:
            new_value = str(self.coordinator.data.get("active_control_mode", "AV"))
            self._attr_native_value = new_value
            _LOGGER.debug("%s uppdaterad: Värde='%s'", self.name, new_value)
        else:
            self._attr_native_value = "AV"
        if self.hass:
            self.async_write_ha_state()
