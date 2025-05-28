# File version: 2025-05-18.6
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
import homeassistant.util.dt as dt_util # För att parsa last_reset tid

from .const import (
    DOMAIN, DEFAULT_NAME,
    ENTITY_ID_SUFFIX_SESSION_ENERGY_SENSOR,
    ENTITY_ID_SUFFIX_SESSION_COST_SENSOR,
    ENTITY_ID_SUFFIX_ACTIVE_CONTROL_MODE_SENSOR,
)
from .coordinator import SmartEVChargingCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SmartEVChargingCoordinator | None = hass.data[DOMAIN][config_entry.entry_id].get("coordinator")
    if not coordinator:
        _LOGGER.error("Koordinatorn är inte tillgänglig för sensor-setup! Kontrollera __init__.py.")
        return

    sensors_to_add = [
        SmartChargingSessionEnergySensor(config_entry, coordinator),
        SmartChargingSessionCostSensor(config_entry, coordinator),
        ActiveControlModeSensor(config_entry, coordinator),
        # DebugCoordinatorStateSensor(config_entry, coordinator, "should_charge_reason", "Anledning Laddningsbeslut"),
    ]
    async_add_entities(sensors_to_add, False)


class SmartChargingBaseSensor(CoordinatorEntity[SmartEVChargingCoordinator], SensorEntity):
    def __init__(self, config_entry: ConfigEntry, coordinator: SmartEVChargingCoordinator, sensor_type_suffix: str) -> None:
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._attr_unique_id = f"{config_entry.entry_id}_{sensor_type_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry.entry_id)},
            name=DEFAULT_NAME, manufacturer="Din Tillverkare", model="Smart EV Charger Control", entry_type="service"
        )

class SmartChargingSessionEnergySensor(SmartChargingBaseSensor):
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL # <--- ÄNDRAD FRÅN TOTAL_INCREASING TILL TOTAL
    _attr_native_unit_of_measurement = "kWh"
    _attr_icon = "mdi:lightning-bolt"

    def __init__(self, config_entry: ConfigEntry, coordinator: SmartEVChargingCoordinator) -> None:
        super().__init__(config_entry, coordinator, ENTITY_ID_SUFFIX_SESSION_ENERGY_SENSOR)
        self._attr_name = f"{DEFAULT_NAME} Session Energi"
        self._attr_native_value: float | None = 0.0 # Starta på 0
        self._attr_last_reset: dt_util.dt.datetime | None = None # Initiera last_reset
        _LOGGER.info("SmartChargingSessionEnergySensor initialiserad: %s", self.name)
        # self._handle_coordinator_update() # Anropas automatiskt av CoordinatorEntity vid första uppdateringen

    @callback
    def _handle_coordinator_update(self) -> None:
        if self.coordinator.data:
            self._attr_native_value = self.coordinator.data.get("session_energy_kwh", 0.0)
            session_start_str = self.coordinator.data.get("session_start_time_utc")
            if session_start_str:
                self._attr_last_reset = dt_util.parse_datetime(session_start_str)
            else:
                # Om ingen session pågår, kanske last_reset ska vara nuvarande tid eller None?
                # För TOTAL_INCREASING bör den bara ändras när en ny "mätperiod" startar.
                # Om det inte finns en session_start_time, kanske vi inte ska ändra last_reset.
                pass 
        else:
            self._attr_native_value = 0.0
        self.async_write_ha_state()

class SmartChargingSessionCostSensor(SmartChargingBaseSensor):
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "SEK"
    _attr_icon = "mdi:cash"

    def __init__(self, config_entry: ConfigEntry, coordinator: SmartEVChargingCoordinator) -> None:
        super().__init__(config_entry, coordinator, ENTITY_ID_SUFFIX_SESSION_COST_SENSOR)
        self._attr_name = f"{DEFAULT_NAME} Session Kostnad"
        self._attr_native_value: float | None = 0.0
        self._attr_last_reset: dt_util.dt.datetime | None = None
        _LOGGER.info("SmartChargingSessionCostSensor initialiserad: %s", self.name)

    @callback
    def _handle_coordinator_update(self) -> None:
        if self.coordinator.data:
            self._attr_native_value = self.coordinator.data.get("session_cost_sek", 0.0)
            session_start_str = self.coordinator.data.get("session_start_time_utc")
            if session_start_str:
                self._attr_last_reset = dt_util.parse_datetime(session_start_str)
        else:
            self._attr_native_value = 0.0
        self.async_write_ha_state()

class ActiveControlModeSensor(SmartChargingBaseSensor):
    _attr_icon = "mdi:robot-happy-outline"
    def __init__(self, config_entry: ConfigEntry, coordinator: SmartEVChargingCoordinator) -> None:
        super().__init__(config_entry, coordinator, ENTITY_ID_SUFFIX_ACTIVE_CONTROL_MODE_SENSOR)
        self._attr_name = f"{DEFAULT_NAME} Aktivt Styrningsläge"
        self._attr_native_value: str = STATE_UNKNOWN
        _LOGGER.info("%s initialiserad", self.name)

    @callback
    def _handle_coordinator_update(self) -> None:
        if self.coordinator.data:
            self._attr_native_value = str(self.coordinator.data.get("active_control_mode", "AV"))
        else:
            self._attr_native_value = "AV"
        self.async_write_ha_state()