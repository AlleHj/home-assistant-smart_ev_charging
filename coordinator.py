# File version: 2025-05-29 0.1.20
import logging
from datetime import timedelta
from typing import Any, cast, Callable
import math
import asyncio

from homeassistant.core import HomeAssistant, Event, CALLBACK_TYPE
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.entity_registry import (
    async_get as async_get_entity_registry,
    EntityRegistry,
)
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.const import (
    STATE_ON,
    STATE_OFF,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    SERVICE_TURN_ON,
    SERVICE_TURN_OFF,
    ATTR_ENTITY_ID,
    UnitOfPower,
    UnitOfEnergy,
)
import homeassistant.util.dt as dt_util

from .const import (
    DOMAIN,
    CONF_CHARGER_DEVICE,
    CONF_STATUS_SENSOR,
    CONF_PRICE_SENSOR,
    CONF_SURCHARGE_HELPER,
    CONF_TIME_SCHEDULE_ENTITY,
    CONF_HOUSE_POWER_SENSOR,
    CONF_SOLAR_PRODUCTION_SENSOR,
    CONF_SOLAR_SCHEDULE_ENTITY,
    CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR,
    CONF_EV_POWER_SENSOR,
    CONF_SCAN_INTERVAL, # Behöll denna om den används någon annanstans, men scan_interval_seconds används i init
    CONF_CHARGER_ENABLED_SWITCH_ID,
    CONF_EV_SOC_SENSOR,
    CONF_TARGET_SOC_LIMIT,
    ENTITY_ID_SUFFIX_SMART_ENABLE_SWITCH,
    ENTITY_ID_SUFFIX_MAX_PRICE_NUMBER,
    ENTITY_ID_SUFFIX_ENABLE_SOLAR_CHARGING_SWITCH,
    ENTITY_ID_SUFFIX_SOLAR_BUFFER_NUMBER,
    ENTITY_ID_SUFFIX_MIN_SOLAR_CHARGE_CURRENT_A_NUMBER,
    CONF_DEBUG_LOGGING,
)

_LOGGER = logging.getLogger(f"custom_components.{DOMAIN}")

VOLTAGE_PHASE_NEUTRAL = 230
VOLTAGE_PHASE_PHASE = 400
SQRT_3 = math.sqrt(3)
DEFAULT_MIN_SOLAR_CURRENT_A_FALLBACK = 6.0
EASEE_ABSOLUTE_MIN_AMPS = 6
INITIAL_SETUP_DELAY_SECONDS = 5


class SmartEVChargingCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to manage Smart EV Charging logic."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        config: dict[str, Any],
        scan_interval_seconds: float, # bytt från config.get(CONF_SCAN_INTERVAL)
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval_seconds),
        )
        self.config_entry = entry
        self.hass = hass
        # self.config är en blandning av entry.data och entry.options, där options har företräde.
        # Detta hanteras i __init__.py när koordinatorn skapas.
        self.config: dict[str, Any] = config

        self.debug_logging_enabled = self.config.get(CONF_DEBUG_LOGGING, False)
        _LOGGER.debug(
            "Koordinator __init__ använder config: %s (Debug-loggning: %s)",
            # self.config, # Undvik att logga hela config om den innehåller känslig info
            {k: v for k, v in self.config.items() if k != "password_om_det_finns"}, # Exempel på filtrering
            self.debug_logging_enabled,
        )

        # Hämta konfigurationsvärden. De kan vara None om de är valfria och inte satta.
        self.charger_device_id: str | None = self.config.get(CONF_CHARGER_DEVICE)
        self.status_sensor_id: str | None = self.config.get(CONF_STATUS_SENSOR)
        self.charger_enabled_switch_id: str | None = self.config.get(
            CONF_CHARGER_ENABLED_SWITCH_ID
        )
        self.price_sensor_id: str | None = self.config.get(CONF_PRICE_SENSOR)
        self.surcharge_helper_id: str | None = self.config.get(CONF_SURCHARGE_HELPER)
        self.time_schedule_entity_id: str | None = self.config.get(
            CONF_TIME_SCHEDULE_ENTITY
        )
        self.house_power_sensor_id: str | None = self.config.get(
            CONF_HOUSE_POWER_SENSOR
        )
        self.solar_production_sensor_id: str | None = self.config.get(
            CONF_SOLAR_PRODUCTION_SENSOR
        )
        self.solar_schedule_entity_id: str | None = self.config.get(
            CONF_SOLAR_SCHEDULE_ENTITY
        )
        self.charger_max_current_limit_sensor_id: str | None = self.config.get( # Kan vara None
            CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR
        )
        self.ev_power_sensor_id: str | None = self.config.get(CONF_EV_POWER_SENSOR)

        self.ev_soc_sensor_id: str | None = self.config.get(CONF_EV_SOC_SENSOR)
        self.target_soc_limit: float | None = self.config.get(CONF_TARGET_SOC_LIMIT)

        _LOGGER.debug(
            "SoC Config i koordinatorns __init__: ev_soc_sensor_id='%s', target_soc_limit=%s (Typ: %s)",
            self.ev_soc_sensor_id,
            self.target_soc_limit,
            type(self.target_soc_limit),
        )
        _LOGGER.debug(
            "Price sensor ID i koordinatorns __init__: %s", self.price_sensor_id
        )
        _LOGGER.debug(
            "Surcharge helper ID i koordinatorns __init__: %s", self.surcharge_helper_id
        )

        # Interna entiteter (skapas av denna integration)
        self.smart_enable_switch_entity_id: str | None = None
        self.max_price_entity_id: str | None = None
        self.solar_enable_switch_entity_id: str | None = None
        self.solar_buffer_entity_id: str | None = None
        self.min_solar_charge_current_entity_id: str | None = None

        # Tillståndsvariabler
        self.current_session_energy_kwh: float = 0.0
        self.current_session_cost_sek: float = 0.0
        self.session_start_time_utc: str | None = None # ISO format sträng

        self.active_control_mode_internal: str | None = None # "PRIS_TID", "SOLENERGI", eller None
        self.active_control_mode: str | None = None # För sensorn, kan vara "AV"
        self.is_smart_charging_controlled_now: bool = False
        self._last_charger_status: str | None = None
        self._proactive_pause_done_this_connection: bool = False
        self._internal_entities_resolved: bool = False
        self.last_commanded_solar_amps: float = 0.0 # Senast kommenderad ström i SOLENERGI-läge

        # Event listeners
        self._status_listener_remover: Callable[[], None] | None = None
        self._price_listener_remover: Callable[[], None] | None = None
        self._solar_production_listener_remover: Callable[[], None] | None = None
        self._ev_soc_listener_remover: Callable[[], None] | None = None
        self._initial_delay_done: bool = False # Fördröjning vid första uppstart

        _LOGGER.info(
            "SmartEVCharging Coordinator initialiserad med scan_interval: %.1f sekunder.",
            scan_interval_seconds,
        )

    async def _setup_listeners(self) -> None:
        """Sätter upp state listeners för relevanta entiteter."""
        # Ta bort eventuella befintliga listeners först
        if self._status_listener_remover: self._status_listener_remover()
        if self._price_listener_remover: self._price_listener_remover()
        if self._solar_production_listener_remover: self._solar_production_listener_remover()
        if self._ev_soc_listener_remover: self._ev_soc_listener_remover()

        # Listener för laddarens status
        if self.status_sensor_id:
            self._status_listener_remover = async_track_state_change_event(
                self.hass, [self.status_sensor_id], self._handle_charger_status_change
            )
            _LOGGER.info("State listener för laddarstatus (%s) är nu aktiv.", self.status_sensor_id)
        else:
            _LOGGER.warning("status_sensor_id ej definierad, kan ej sätta upp listener för laddarstatus.")

        # Listener för elpris
        if self.price_sensor_id:
            self._price_listener_remover = async_track_state_change_event(
                self.hass, [self.price_sensor_id], self._handle_price_change
            )
            _LOGGER.info("State listener för prissensor (%s) är nu aktiv.", self.price_sensor_id)
        else:
            _LOGGER.warning("price_sensor_id ej definierad, kan ej sätta upp listener för pris.")

        # Listener för solproduktion (om konfigurerad)
        if self.solar_production_sensor_id:
            self._solar_production_listener_remover = async_track_state_change_event(
                self.hass, [self.solar_production_sensor_id], self._handle_solar_production_change
            )
            _LOGGER.info("State listener för solproduktionssensor (%s) är nu aktiv.", self.solar_production_sensor_id)
        else:
            _LOGGER.debug("solar_production_sensor_id ej definierad, sätter ej upp listener för solproduktion.")

        # Listener för bilens SoC (om konfigurerad)
        if self.ev_soc_sensor_id:
            self._ev_soc_listener_remover = async_track_state_change_event(
                self.hass, [self.ev_soc_sensor_id], self._handle_ev_soc_change
            )
            _LOGGER.info("State listener för EV SoC-sensor (%s) är nu aktiv.", self.ev_soc_sensor_id)
        elif self.config.get(CONF_EV_SOC_SENSOR): # Om den var konfigurerad men self.ev_soc_sensor_id är None (bör inte hända)
            _LOGGER.warning("ev_soc_sensor_id var konfigurerad men kunde inte användas för listener.")


    async def _remove_listeners(self) -> None:
        """Tar bort alla aktiva state listeners."""
        if self._status_listener_remover:
            self._status_listener_remover()
            self._status_listener_remover = None
            _LOGGER.info("State listener för laddarstatus borttagen.")
        if self._price_listener_remover:
            self._price_listener_remover()
            self._price_listener_remover = None
            _LOGGER.info("State listener för prissensor borttagen.")
        if self._solar_production_listener_remover:
            self._solar_production_listener_remover()
            self._solar_production_listener_remover = None
            _LOGGER.info("State listener för solproduktionssensor borttagen.")
        if self._ev_soc_listener_remover:
            self._ev_soc_listener_remover()
            self._ev_soc_listener_remover = None
            _LOGGER.info("State listener för EV SoC-sensor borttagen.")

    # Event handlers (_handle_charger_status_change, etc.) förblir oförändrade

    async def _handle_charger_status_change(self, event: Event) -> None:
        new_state_obj = event.data.get("new_state")
        if not new_state_obj:
            return
        new_status = new_state_obj.state
        entity_id = event.data.get("entity_id")
        _LOGGER.debug(
            "Charger status listener: %s ändrades till: %s", entity_id, new_status
        )
        if not self._internal_entities_resolved:
            _LOGGER.debug(
                "Charger status listener: Interne entiteter inte redo, ignorerar."
            )
            return

        is_smart_on_state = self.hass.states.get(self.smart_enable_switch_entity_id)
        is_solar_on_state = self.hass.states.get(self.solar_enable_switch_entity_id)

        is_smart_on = is_smart_on_state and is_smart_on_state.state == STATE_ON
        is_solar_on = is_solar_on_state and is_solar_on_state.state == STATE_ON
        any_smart_mode_globally_on = is_smart_on or is_solar_on

        if not any_smart_mode_globally_on:
            _LOGGER.debug(
                "Charger listener: Inget smartläge aktivt, ignorerar %s.", new_status
            )
            return

        action_taken_by_listener = False
        if (
            new_status == "ready_to_charge"
            and not self._proactive_pause_done_this_connection
        ):
            await self._execute_assert_control_and_pause(
                f"Charger status listener: Status '{new_status}'. Smartläge aktivt."
            )
            action_taken_by_listener = True
        elif new_status == "disconnected":
            _LOGGER.debug(
                "Charger listener: Status 'disconnected'. Återställer flaggor."
            )
            self._proactive_pause_done_this_connection = False
            if self.is_smart_charging_controlled_now:
                self.is_smart_charging_controlled_now = False
            if self.active_control_mode_internal == "SOLENERGI":
                self.last_commanded_solar_amps = 0.0
            self.active_control_mode_internal = None
            action_taken_by_listener = True
        elif (
            self.is_smart_charging_controlled_now
            and self.active_control_mode_internal is not None
            and new_status
            not in ["charging", "disconnected", STATE_UNAVAILABLE, STATE_UNKNOWN]
        ):
            _LOGGER.info(
                "Charger status listener: Extern avstängning/paus trolig. Förväntade 'charging' (avsett läge: %s) men fick status '%s'. Återställer kontrollflaggor.",
                self.active_control_mode_internal,
                new_status,
            )
            self.is_smart_charging_controlled_now = False
            self._proactive_pause_done_this_connection = False # Viktigt att denna också återställs
            if self.active_control_mode_internal == "SOLENERGI":
                self.last_commanded_solar_amps = 0.0
            self.active_control_mode_internal = None
            action_taken_by_listener = True

        if action_taken_by_listener:
            _LOGGER.debug(
                "Charger status listener vidtog åtgärd, begär omedelbar coordinator refresh."
            )
            await self.async_request_refresh()

    async def _handle_price_change(self, event: Event) -> None:
        new_state_obj = event.data.get("new_state")
        old_state_obj = event.data.get("old_state")
        if (
            not new_state_obj
            or not old_state_obj
            or new_state_obj.state == old_state_obj.state
        ):
            # _LOGGER.debug("Price listener: Ingen prisändring.") # Kan bli för mycket loggar
            return
        _LOGGER.info(
            "Price sensor listener: %s ändrades från %s till %s. Begär omedelbar omvärdering.",
            event.data.get("entity_id"),
            old_state_obj.state if old_state_obj else "None",
            new_state_obj.state,
        )
        await self.async_request_refresh()

    async def _handle_solar_production_change(self, event: Event) -> None:
        new_state_obj = event.data.get("new_state")
        old_state_obj = event.data.get("old_state")
        if (
            not new_state_obj
            or not old_state_obj
            or new_state_obj.state == old_state_obj.state
        ):
            return # Ingen ändring

        entity_id = event.data.get("entity_id")
        # Kontrollera om solenergiläget är aktivt (via dess switch)
        is_solar_switch_on_state = self.hass.states.get(
            self.solar_enable_switch_entity_id # Säkerställ att detta ID är satt
        )
        if is_solar_switch_on_state and is_solar_switch_on_state.state == STATE_ON:
            _LOGGER.info(
                "Solar production listener: %s ändrades. Begär omedelbar omvärdering.",
                entity_id,
            )
            await self.async_request_refresh()
        else:
            _LOGGER.debug(
                "Solar production listener: Ändring på %s, men solenergiläge ej aktivt. Ignorerar.",
                entity_id,
            )

    async def _handle_ev_soc_change(self, event: Event) -> None:
        new_state_obj = event.data.get("new_state")
        old_state_obj = event.data.get("old_state")
        if (
            not new_state_obj
            or not old_state_obj
            or new_state_obj.state == old_state_obj.state
        ):
            return # Ingen ändring

        entity_id = event.data.get("entity_id")
        # Kontrollera om SoC-kontroll är fullt konfigurerad
        if self.ev_soc_sensor_id and self.target_soc_limit is not None:
            _LOGGER.info(
                "EV SoC listener: %s ändrades från %s till %s. Begär omedelbar omvärdering.",
                entity_id,
                old_state_obj.state if old_state_obj else "None",
                new_state_obj.state,
            )
            await self.async_request_refresh()
        else:
            _LOGGER.debug(
                "EV SoC listener: Ändring på %s, men SoC-kontroll ej fullt konfigurerad (sensor: %s, limit: %s). Ignorerar.",
                entity_id,
                self.ev_soc_sensor_id,
                self.target_soc_limit,
            )

    async def _resolve_internal_entities(self) -> bool:
        """Matchar interna entitets-ID:n (switchar, nummer) som skapas av denna integration."""
        if self._internal_entities_resolved:
            # Om redan lösta, säkerställ att listeners är uppsatta (kan ha tagits bort/inte satts pga tidig körning)
            if not (self._status_listener_remover or self._price_listener_remover or self._solar_production_listener_remover or self._ev_soc_listener_remover):
                 await self._setup_listeners()
            return True

        _LOGGER.debug("Koordinator: _resolve_internal_entities STARTAR.")
        try:
            ent_reg: EntityRegistry = async_get_entity_registry(self.hass)
            # Unika ID:n baseras på config_entry.entry_id + suffix
            self.smart_enable_switch_entity_id = ent_reg.async_get_entity_id("switch", DOMAIN, f"{self.config_entry.entry_id}_{ENTITY_ID_SUFFIX_SMART_ENABLE_SWITCH}")
            self.max_price_entity_id = ent_reg.async_get_entity_id("number", DOMAIN, f"{self.config_entry.entry_id}_{ENTITY_ID_SUFFIX_MAX_PRICE_NUMBER}")
            self.solar_enable_switch_entity_id = ent_reg.async_get_entity_id("switch", DOMAIN, f"{self.config_entry.entry_id}_{ENTITY_ID_SUFFIX_ENABLE_SOLAR_CHARGING_SWITCH}")
            self.solar_buffer_entity_id = ent_reg.async_get_entity_id("number", DOMAIN, f"{self.config_entry.entry_id}_{ENTITY_ID_SUFFIX_SOLAR_BUFFER_NUMBER}")
            self.min_solar_charge_current_entity_id = ent_reg.async_get_entity_id("number", DOMAIN, f"{self.config_entry.entry_id}_{ENTITY_ID_SUFFIX_MIN_SOLAR_CHARGE_CURRENT_A_NUMBER}")

            _LOGGER.info(
                "Interna Entity IDs: SmartEnable:%s, MaxPrice:%s, SolarEnable:%s, SolarBuffer:%s, MinSolarCurrent:%s",
                self.smart_enable_switch_entity_id, self.max_price_entity_id,
                self.solar_enable_switch_entity_id, self.solar_buffer_entity_id,
                self.min_solar_charge_current_entity_id
            )

            if not all([
                self.smart_enable_switch_entity_id, self.max_price_entity_id,
                self.solar_enable_switch_entity_id, self.solar_buffer_entity_id,
                self.min_solar_charge_current_entity_id
            ]):
                _LOGGER.warning("Ett eller flera interna ID:n ej redo under _resolve_internal_entities. Försöker igen nästa cykel.")
                self._internal_entities_resolved = False
                return False

            self._internal_entities_resolved = True
            _LOGGER.debug("Koordinator: Interna ID:n OK.")
            await self._setup_listeners() # Sätt upp listeners när ID:n är bekräftade
            return True
        except Exception as e: # Generell felhantering
            _LOGGER.error("Fel i _resolve_internal_entities: %s", e, exc_info=True)
            self._internal_entities_resolved = False
            return False


    async def _async_first_refresh(self) -> None:
        """Körs en gång när koordinatorn startar för första gången."""
        _LOGGER.debug("Koordinator: _async_first_refresh STARTAR. Explicit återställning av initialt tillstånd.")

        if not self._initial_delay_done:
            _LOGGER.info("Smart EV Charging Koordinator: Väntar %s sekunder för att andra entiteter ska initialiseras...", INITIAL_SETUP_DELAY_SECONDS)
            await asyncio.sleep(INITIAL_SETUP_DELAY_SECONDS)
            _LOGGER.info("Smart EV Charging Koordinator: Fördröjning klar, fortsätter med första refresh.")
            self._initial_delay_done = True

        # Återställ interna tillståndsvariabler för en ren start
        self.active_control_mode_internal = None
        self.active_control_mode = None # Detta kommer att visas som "AV" i sensorn
        self.is_smart_charging_controlled_now = False
        self.last_commanded_solar_amps = 0.0
        self._proactive_pause_done_this_connection = False

        # Försök att lösa interna entiteter och sätta upp listeners
        await self._resolve_internal_entities()

        # Hämta initial laddarstatus om möjligt
        if self.status_sensor_id:
            self._last_charger_status = self._get_entity_state(self.status_sensor_id)
            _LOGGER.debug("Initial laddarstatus (från %s): %s", self.status_sensor_id, self._last_charger_status)
        else:
            self._last_charger_status = STATE_UNKNOWN # Eller None, beroende på hur det hanteras
            _LOGGER.warning("status_sensor_id är inte satt, kan inte initiera _last_charger_status.")

        _LOGGER.debug("Koordinator: _async_first_refresh AVSLUTAD.")
        # DataUpdateCoordinator kommer automatiskt att anropa _async_update_data efter detta.

    # _call_easee_service, _prev_is_solar_reset, etc. förblir oförändrade
    async def _call_easee_service(
        self, service_name: str, action: str | None = None, current: int | None = None
    ) -> bool:
        if not self.charger_device_id:
            _LOGGER.error("Charger device ID ej konfigurerat.")
            return False
        service_data = {"device_id": self.charger_device_id}
        if action:
            service_data["action_command"] = action
        if current is not None:
            service_data["current"] = current
        _LOGGER.debug(
            "Förbereder anrop till easee.%s med data: %s", service_name, service_data
        )
        try:
            await self.hass.services.async_call(
                "easee", service_name, service_data, blocking=False # False för att inte blockera koordinatorn
            )
            _LOGGER.info("ANROPAT easee.%s med data %s", service_name, service_data)
            return True
        except Exception as e:
            _LOGGER.error(
                "Fel vid anrop av easee.%s med data %s: %s",
                service_name,
                service_data,
                e,
            )
            return False

    def _prev_is_solar_reset(
        self,
        previous_intended_mode: str | None,
        log_leaving: bool = False,
        new_intended_mode: str | None = None,
    ) -> None:
        if (
            previous_intended_mode == "SOLENERGI"
            and self.last_commanded_solar_amps != 0.0
        ):
            log_msg = "Nollställer last_commanded_solar_amps (var %.1fA) pga %s" % (
                self.last_commanded_solar_amps,
                "lämnar SOLENERGI" if log_leaving else "solvillkor ej uppfyllda",
            )
            if log_leaving and new_intended_mode:
                log_msg += " (nytt avsett läge: %s)" % new_intended_mode
            _LOGGER.debug(log_msg)
            self.last_commanded_solar_amps = 0.0

    async def _execute_assert_control_and_pause(self, reason_log_msg: str):
        _LOGGER.debug("Kör _execute_assert_control_and_pause pga: %s", reason_log_msg)
        await self._call_easee_service(
            service_name="action_command", action="override_schedule"
        )
        await self._call_easee_service(service_name="action_command", action="pause")
        self.is_smart_charging_controlled_now = True
        self._proactive_pause_done_this_connection = True
        _LOGGER.debug("_execute_assert_control_and_pause slutförd.")

    async def _execute_stop_charging(
        self,
        current_charger_status: str | None, # Kan vara None om status_sensor_id är None
        previous_intended_mode: str | None,
        reason_log_msg: str,
    ):
        _LOGGER.debug(
            "Kör _execute_stop_charging (status: %s, föregående avsett läge: %s) pga: %s",
            current_charger_status,
            previous_intended_mode,
            reason_log_msg,
        )
        stoppable_statuses = [
            "charging",
            "paused",
            "charging_paused_by_smartcharging", # Antagande om Easee status
            "awaiting_start",
            "ready_to_charge",
        ]
        if current_charger_status in stoppable_statuses:
            await self._call_easee_service(
                service_name="action_command", action="pause"
            )
        else:
            _LOGGER.info(
                "Laddaren ej i stoppbart läge (status: '%s'), PAUSE skickas ej av _execute_stop_charging.",
                current_charger_status or "Okänd",
            )

        # Dynamic limit lämnas oförändrad vid paus/stopp härifrån,
        # då ett annat läge kan ta över eller manuell styrning.
        # Om det är SOLENERGI som stoppas, nollställ last_commanded_solar_amps.
        self._prev_is_solar_reset(previous_intended_mode) # Hanterar nollställning av last_commanded_solar_amps
        self.is_smart_charging_controlled_now = False
        _LOGGER.debug("_execute_stop_charging slutförd.")

    async def _execute_start_or_adjust_charging(
        self,
        target_amps: int,
        current_charger_status: str | None, # Kan vara None
        previous_intended_mode: str | None,
        new_intended_mode: str | None, # Bör vara "PRIS_TID" eller "SOLENERGI"
        reason_log_msg: str,
    ) -> bool:
        _LOGGER.debug(
            "Kör _execute_start_or_adjust_charging (mål: %sA, status: %s, avsett nytt läge: %s) pga: %s",
            target_amps,
            current_charger_status or "Okänd",
            new_intended_mode,
            reason_log_msg,
        )

        send_dynamic_limit_update = True
        if new_intended_mode == "SOLENERGI":
            if int(self.last_commanded_solar_amps) == target_amps:
                _LOGGER.debug(
                    "Solenergi: Nyberäknad målamperetal (%sA) är samma som senast kommenderad (%.0fA). set_charger_dynamic_limit skickas ej.",
                    target_amps, self.last_commanded_solar_amps,
                )
                send_dynamic_limit_update = False

        if send_dynamic_limit_update:
            _LOGGER.info("Sätter dynamisk laddgräns till %sA.", target_amps)
            limit_sent_successfully = await self._call_easee_service(
                service_name="set_charger_dynamic_limit", current=target_amps
            )
            if limit_sent_successfully and new_intended_mode == "SOLENERGI":
                self.last_commanded_solar_amps = float(target_amps)
                _LOGGER.debug("Uppdaterade last_commanded_solar_amps till: %.1fA", self.last_commanded_solar_amps)
        elif new_intended_mode == "SOLENERGI": # Om limit ej skickades men det är solenergi
            _LOGGER.info("Dynamisk laddgräns för solenergi är oförändrad på %sA. Ingen uppdatering skickas.", int(self.last_commanded_solar_amps))

        charging_initiated_or_active = False
        # Ny session om kontroll inte var aktiv, läget byts, eller om laddaren inte laddade trots kontroll.
        is_new_session_or_control_reassert = (
            not self.is_smart_charging_controlled_now or
            previous_intended_mode != new_intended_mode or
            (self.is_smart_charging_controlled_now and current_charger_status != "charging")
        )

        if is_new_session_or_control_reassert and current_charger_status != "disconnected":
            _LOGGER.info(
                "Ny session/lägesbyte (%s till %s, status: %s). Nollställer sessionsdata och skickar override_schedule.",
                previous_intended_mode or "Ingen", new_intended_mode or "Ingen", current_charger_status or "Okänd"
            )
            self.current_session_energy_kwh = 0.0
            self.current_session_cost_sek = 0.0
            self.session_start_time_utc = dt_util.utcnow().isoformat()
            await self._call_easee_service(service_name="action_command", action="override_schedule")
        elif is_new_session_or_control_reassert and current_charger_status == "disconnected":
             _LOGGER.info("Ny session/lägesbyte men laddare 'disconnected'. Nollställer sessionsdata, skickar ej override.")
             self.current_session_energy_kwh = 0.0
             self.current_session_cost_sek = 0.0
             self.session_start_time_utc = dt_util.utcnow().isoformat()


        startable_statuses = ["ready_to_charge", "awaiting_start", "paused", "charging_paused_by_smartcharging"]
        if current_charger_status in startable_statuses:
            await self._call_easee_service(service_name="action_command", action="start")
            charging_initiated_or_active = True
        elif current_charger_status == "charging":
            _LOGGER.info("Laddaren laddar redan. Dynamisk limit är satt/justerad till %sA.", target_amps)
            charging_initiated_or_active = True
        elif current_charger_status == "disconnected":
            _LOGGER.info("Laddaren är 'disconnected'. Start-kommando skickas ej. Väntar på anslutning. Dynamisk limit förberedd till %sA.", target_amps)
        else: # Andra statusar, t.ex. error, car_connected_no_power
            _LOGGER.info("Laddaren är i status '%s'. Start-kommando skickas ej. Dynamisk limit förberedd till %sA.", current_charger_status or "Okänd", target_amps)

        # Säkerställ att last_commanded_solar_amps är korrekt även om limit inte skickades
        if charging_initiated_or_active and new_intended_mode == "SOLENERGI":
            if not send_dynamic_limit_update and float(target_amps) != self.last_commanded_solar_amps:
                 self.last_commanded_solar_amps = float(target_amps)
                 _LOGGER.debug("Uppdaterade last_commanded_solar_amps (efter start, limit var samma) till: %.1fA", self.last_commanded_solar_amps)
        elif new_intended_mode == "SOLENERGI" and not charging_initiated_or_active and self.last_commanded_solar_amps != 0.0 :
             _LOGGER.debug("Solenergi avsågs men startade/fortsatte inte. Nollställer last_commanded_solar_amps från %.1fA.", self.last_commanded_solar_amps)
             self.last_commanded_solar_amps = 0.0 # Om solenergi inte kunde starta/fortsätta, nollställ.

        self.is_smart_charging_controlled_now = True # Vi har nu tagit kontroll (eller försökt)
        _LOGGER.debug("_execute_start_or_adjust_charging slutförd. Laddning initierad/aktiv: %s", charging_initiated_or_active)
        return charging_initiated_or_active

    async def _async_update_data(self) -> dict[str, Any]:
        """Huvudlogik för att utvärdera och styra laddning."""
        _LOGGER.debug("--- Koordinator _async_update_data START ---")

        if not self._internal_entities_resolved:
            if not await self._resolve_internal_entities():
                _LOGGER.warning("_async_update_data: Interna entiteter är ännu inte tillgängliga. Försöker igen nästa cykel.")
                # Returnera nuvarande data eller ett standardvärde om self.data är None
                return self.data if self.data else self._current_coordinator_data("Väntar på interna entiteter.")


        current_charger_status = self._get_entity_state(self.status_sensor_id)
        # Hantera om extern part stängt av laddning
        if self.is_smart_charging_controlled_now and \
           self.active_control_mode_internal is not None and \
           current_charger_status not in ["charging", "disconnected", STATE_UNAVAILABLE, STATE_UNKNOWN]:
            _LOGGER.info(
                "Loop-detektering: Möjlig extern avstängning/paus. Förväntade 'charging' (avsett läge: %s) men status är '%s'. Återställer kontroll.",
                self.active_control_mode_internal, current_charger_status
            )
            self.is_smart_charging_controlled_now = False
            self._proactive_pause_done_this_connection = False # Återställ så att proaktiv paus kan ske igen
            if self.active_control_mode_internal == "SOLENERGI": self.last_commanded_solar_amps = 0.0
            self.active_control_mode_internal = None
            # Omedelbar omvärdering kan vara bra här, men var försiktig med loopar.
            # self.hass.async_create_task(self.async_request_refresh()) # Kan skapa täta anrop
            return self._current_coordinator_data(f"Extern avstängning/paus vid status {current_charger_status}. Omvärderar.")


        # Hämta alla nödvändiga värden från Home Assistant states och attribut
        charger_main_enabled_state = self._get_entity_state(self.charger_enabled_switch_id)
        is_smart_charging_switch_on = self._get_entity_state(self.smart_enable_switch_entity_id) == STATE_ON
        is_price_time_schedule_active = self._is_schedule_active(self.time_schedule_entity_id)
        is_solar_charging_switch_on = self._get_entity_state(self.solar_enable_switch_entity_id) == STATE_ON
        is_solar_schedule_active = self._is_schedule_active(self.solar_schedule_entity_id)
        max_price_allowed = self._get_number_value(self.max_price_entity_id, float("inf"))
        solar_buffer_w = self._get_number_value(self.solar_buffer_entity_id, 0.0)
        min_solar_current_a = self._get_number_value(self.min_solar_charge_current_entity_id, DEFAULT_MIN_SOLAR_CURRENT_A_FALLBACK)
        spot_price_kr = self._get_spot_price_in_kr(self.price_sensor_id)
        current_total_price_for_cost = self._calculate_total_price(spot_price_kr, self.surcharge_helper_id)
        solar_production_w = self._get_power_value(self.solar_production_sensor_id)
        house_consumption_w = self._get_power_value(self.house_power_sensor_id)
        ev_power_w = self._get_power_value(self.ev_power_sensor_id) if self.ev_power_sensor_id else 0.0
        if ev_power_w is None: ev_power_w = 0.0 # Säkerställ att det är en float

        # *** START ÄNDRING FÖR AttributeError ***
        charger_max_limit_a_sensor_state = None
        if self.charger_max_current_limit_sensor_id: # Kontrollera om ID är satt
            charger_max_limit_a_sensor_state = self.hass.states.get(
                self.charger_max_current_limit_sensor_id
            )
        # *** SLUT ÄNDRING FÖR AttributeError ***

        try:
            charger_hw_max_current_a = (
                float(charger_max_limit_a_sensor_state.state)
                if charger_max_limit_a_sensor_state and \
                   charger_max_limit_a_sensor_state.state not in [STATE_UNAVAILABLE, STATE_UNKNOWN] and \
                   charger_max_limit_a_sensor_state.state is not None # Extra check för None state
                else 16.0 # Fallback till 16A om sensor saknas, är otillgänglig eller har ogiltigt värde
            )
        except (ValueError, TypeError):
            _LOGGER.warning(
                "Kunde inte tolka laddboxens max strömgräns från sensor %s (värde: %s), använder fallback %sA.",
                self.charger_max_current_limit_sensor_id,
                charger_max_limit_a_sensor_state.state if charger_max_limit_a_sensor_state else "Okänd",
                16.0
            )
            charger_hw_max_current_a = 16.0


        # Logga indata (lazy formatting)
        if _LOGGER.isEnabledFor(logging.DEBUG):
            spot_price_kr_str = "%.2f" % spot_price_kr if spot_price_kr is not None else "N/A"
            current_total_price_for_cost_str = "%.2f" % current_total_price_for_cost if current_total_price_for_cost is not None else "N/A"
            solar_prod_str = "%.0f" % solar_production_w if solar_production_w is not None else "N/A"
            house_cons_str = "%.0f" % house_consumption_w if house_consumption_w is not None else "N/A"
            _LOGGER.debug(
                "Indata: Status: %s, HuvudSwitch: %s, PrisLaddPå: %s, PrisSchema: %s, MaxSpotPris: %.2f, AktSpotPris: %s, AktTotalPrisKostn: %s, SolLaddPå: %s, SolSchema: %s, SolBuffer: %.0fW, SolProd: %sW, HusFörbr: %sW, EVLaddEff: %.0fW, MaxLaddboxA: %.1fA, MinSolA: %.1fA, is_controlled: %s, proactive_done: %s",
                current_charger_status, charger_main_enabled_state, is_smart_charging_switch_on,
                is_price_time_schedule_active, max_price_allowed, spot_price_kr_str,
                current_total_price_for_cost_str, is_solar_charging_switch_on, is_solar_schedule_active,
                solar_buffer_w, solar_prod_str, house_cons_str, ev_power_w, charger_hw_max_current_a,
                min_solar_current_a, self.is_smart_charging_controlled_now, self._proactive_pause_done_this_connection
            )

        any_smart_mode_globally_enabled_by_switch = is_smart_charging_switch_on or is_solar_charging_switch_on

        # Proaktiv kontrolltagning och hantering av huvudswitch
        if any_smart_mode_globally_enabled_by_switch:
            if charger_main_enabled_state == STATE_OFF and self.charger_enabled_switch_id:
                _LOGGER.info("Huvudswitch (%s) AV men smartläge aktivt. Slår PÅ.", self.charger_enabled_switch_id)
                await self.hass.services.async_call("switch", SERVICE_TURN_ON, {ATTR_ENTITY_ID: self.charger_enabled_switch_id}, blocking=False) # ändrat till non-blocking
                # Begär en refresh direkt för att omvärdera med switchen på.
                self.hass.async_create_task(self.async_request_refresh())
                return self._current_coordinator_data("Huvudswitch aktiverad, omvärderar.")

            # Fallback för proaktiv paus om state listener missat/inte hunnit
            if current_charger_status in ["ready_to_charge", "awaiting_start"] and \
               not self._proactive_pause_done_this_connection and \
               charger_main_enabled_state == STATE_ON and \
               not self.is_smart_charging_controlled_now :
                await self._execute_assert_control_and_pause(f"Proaktiv kontrolltagning (loop fallback, status: {current_charger_status})")

        self._last_charger_status = current_charger_status # Spara nuvarande status för nästa cykel

        # Beslutslogik
        target_charge_current_a: float = 0.0
        should_charge_flag = False
        reason_for_action = "Inga aktiva smartlägen uppfyller villkor."
        previous_intended_active_control_mode = self.active_control_mode_internal
        new_intended_active_control_mode: str | None = None

        # 1. SoC-gränskontroll (Högst prioritet)
        soc_limit_prevents_charging = False
        if self.ev_soc_sensor_id and self.target_soc_limit is not None:
            soc_state_str = self._get_entity_state(self.ev_soc_sensor_id)
            if soc_state_str not in [STATE_UNKNOWN, STATE_UNAVAILABLE] and soc_state_str is not None:
                try:
                    current_soc = float(soc_state_str)
                    _LOGGER.debug("SoC Check: Current SoC=%.1f%%, Target SoC Limit=%.1f%%", current_soc, self.target_soc_limit)
                    if current_soc >= self.target_soc_limit:
                        soc_limit_prevents_charging = True
                        reason_for_action = f"Laddningsgräns nådd ({current_soc:.1f}% >= {self.target_soc_limit:.1f}%). Ingen laddning."
                        _LOGGER.info(reason_for_action)
                except (ValueError, TypeError):
                    _LOGGER.warning("Kunde inte konvertera SoC-värde '%s' från %s till float.", soc_state_str, self.ev_soc_sensor_id)
            else:
                _LOGGER.info("SoC-sensor %s är %s. Kan inte utföra SoC-kontroll.", self.ev_soc_sensor_id, soc_state_str or "None")

        # Om SoC-gräns hindrar, hoppa över övrig logik för att starta laddning
        if soc_limit_prevents_charging:
            should_charge_flag = False
            self.active_control_mode_internal = None # Inget aktivt kontrolläge
            # Om vi var i solenergiläge, nollställ last_commanded_solar_amps
            self._prev_is_solar_reset(previous_intended_active_control_mode, log_leaving=True, new_intended_mode="AV (SoC)")
        else:
            # 2. Pris/Tid-styrd Smartladdning (Andra prioritet)
            price_time_reason_intermediate: str | None = None
            if is_smart_charging_switch_on:
                if is_price_time_schedule_active:
                    if spot_price_kr is not None and spot_price_kr <= max_price_allowed:
                        new_intended_active_control_mode = "PRIS_TID"
                        target_charge_current_a = charger_hw_max_current_a
                        should_charge_flag = True
                        price_time_reason_intermediate = f"Pris/Tid OK (Spot {spot_price_kr:.2f}kr <= Max {max_price_allowed:.2f}kr). Mål: {target_charge_current_a:.0f}A."
                    elif spot_price_kr is None:
                        price_time_reason_intermediate = f"Pris/Tid: Spotpris saknas (Max: {max_price_allowed:.2f}kr)."
                    else: # Spotpris är för högt
                        price_time_reason_intermediate = f"Pris/Tid: Spotpris ({spot_price_kr:.2f}kr) för högt (Max: {max_price_allowed:.2f}kr)."
                else: # Schema ej aktivt
                    price_time_reason_intermediate = f"Pris/Tid: Schema ({self.time_schedule_entity_id or 'ej definierat'}) ej aktivt."

                _LOGGER.info("Utvärdering (Pris/Tid): %s", price_time_reason_intermediate)
                if not should_charge_flag: # Om Pris/Tid inte resulterade i laddning
                    reason_for_action = price_time_reason_intermediate
                    # Om vi lämnar solenergi pga att pris/tid nu är aktivt (men kanske inte laddar pga pris)
                    self._prev_is_solar_reset(previous_intended_active_control_mode, log_leaving=True, new_intended_mode="PRIS_TID (ej aktiv)")


            # 3. Solenergiladdning (Tredje prioritet, om Pris/Tid inte är aktivt)
            solar_reason_intermediate: str | None = None
            if not should_charge_flag and is_solar_charging_switch_on: # Om Pris/Tid inte vill ladda OCH sol-switch är på
                if is_solar_schedule_active:
                    if solar_production_w is not None and house_consumption_w is not None:
                        # Dämpad beräkning av överskott
                        ev_offset_for_solar_calc = 0.0
                        if self.active_control_mode_internal == "SOLENERGI" and self.is_smart_charging_controlled_now and current_charger_status == "charging":
                             # Använd senast kommenderad ström för att uppskatta EV-effekt, om vi redan är i sol-läge och laddar
                            ev_offset_for_solar_calc = self.last_commanded_solar_amps * VOLTAGE_PHASE_PHASE * SQRT_3 # 3-fas antagande

                        other_house_w = house_consumption_w - ev_offset_for_solar_calc
                        available_w = solar_production_w - other_house_w - solar_buffer_w
                        _LOGGER.debug(
                            "Sol (dämpad): Sol=%.0fW, HusSens=%.0fW, EVOffsetSol=%.0fW, AnnatHus=%.0fW, Buffer=%.0fW, Tillgängligt=%.0fW",
                            solar_production_w, house_consumption_w, ev_offset_for_solar_calc, other_house_w, solar_buffer_w, available_w
                        )

                        min_power_w_for_solar = SQRT_3 * VOLTAGE_PHASE_PHASE * min_solar_current_a
                        if available_w >= min_power_w_for_solar:
                            calc_amps_from_solar = available_w / (SQRT_3 * VOLTAGE_PHASE_PHASE)
                            effective_amps_solar = max(0, min(calc_amps_from_solar, charger_hw_max_current_a))
                            target_amps_solar_final = math.floor(effective_amps_solar)

                            if target_amps_solar_final >= min_solar_current_a and target_amps_solar_final >= EASEE_ABSOLUTE_MIN_AMPS :
                                new_intended_active_control_mode = "SOLENERGI"
                                should_charge_flag = True
                                target_charge_current_a = float(target_amps_solar_final)
                                solar_reason_intermediate = f"Solenergi: Laddar med överskott ({target_amps_solar_final:.0f}A)."
                            else:
                                solar_reason_intermediate = f"Solenergi: Beräknad ström ({target_amps_solar_final:.0f}A) under min ({min_solar_current_a:.0f}A eller Easee min {EASEE_ABSOLUTE_MIN_AMPS}A)."
                                self._prev_is_solar_reset(previous_intended_active_control_mode, new_intended_mode="AV")
                        else: # Otillräckligt överskott
                            solar_reason_intermediate = f"Solenergi: Otillräckligt överskott ({available_w:.0f}W < {min_power_w_for_solar:.0f}W)."
                            self._prev_is_solar_reset(previous_intended_active_control_mode, new_intended_mode="AV")
                    elif solar_production_w is None: solar_reason_intermediate = "Solenergi: Solproduktion saknas."; self._prev_is_solar_reset(previous_intended_active_control_mode, new_intended_mode="AV")
                    elif house_consumption_w is None: solar_reason_intermediate = "Solenergi: Husförbrukning saknas."; self._prev_is_solar_reset(previous_intended_active_control_mode, new_intended_mode="AV")
                else: # Sol-schema ej aktivt
                    solar_reason_intermediate = f"Solenergi: Schema ({self.solar_schedule_entity_id or 'ej definierat'}) ej aktivt."
                    self._prev_is_solar_reset(previous_intended_active_control_mode, new_intended_mode="AV")

                _LOGGER.info("Utvärdering (Solenergi): %s", solar_reason_intermediate)
                if not should_charge_flag: # Om Solenergi inte resulterade i laddning
                    reason_for_action = solar_reason_intermediate

            # Om vi byter FRÅN solenergi till PRIS_TID (även om PRIS_TID inte aktivt laddar)
            if previous_intended_active_control_mode == "SOLENERGI" and new_intended_active_control_mode == "PRIS_TID":
                 self._prev_is_solar_reset(previous_intended_active_control_mode, log_leaving=True, new_intended_mode="PRIS_TID")


            # Om inget smartläge är PÅslaget
            if not is_smart_charging_switch_on and not is_solar_charging_switch_on:
                reason_for_action = "Inga smarta laddningslägen (Pris/Tid eller Sol) är aktiverade."
                self._prev_is_solar_reset(previous_intended_active_control_mode, log_leaving=True, new_intended_mode="AV")


            # Uppdatera anledning om laddning ska ske
            if should_charge_flag:
                if new_intended_active_control_mode == "PRIS_TID": reason_for_action = price_time_reason_intermediate or reason_for_action
                elif new_intended_active_control_mode == "SOLENERGI": reason_for_action = solar_reason_intermediate or reason_for_action

            self.active_control_mode_internal = new_intended_active_control_mode


        _LOGGER.info(
            "Laddningsbeslut (Avsikt): %s. Avsett läge: %s. Målström: %.1fA. SkaLadda: %s",
            reason_for_action, self.active_control_mode_internal, target_charge_current_a, should_charge_flag
        )

        # Utför åtgärder baserat på beslut
        current_control_state_at_command_start = self.is_smart_charging_controlled_now
        charging_actually_started_or_continued = False

        if self.charger_device_id: # Säkerställ att vi har en laddare att styra
            if should_charge_flag:
                current_target_amps = int(target_charge_current_a)
                # Dubbelkolla att målstömmen inte är för låg för Easee, särskilt för solenergi.
                if new_intended_active_control_mode == "SOLENERGI" and current_target_amps < EASEE_ABSOLUTE_MIN_AMPS:
                    _LOGGER.warning(
                        "Solenergi: Målström %sA < %sA (Easee min). Stoppar istället för att starta/justera.",
                        current_target_amps, EASEE_ABSOLUTE_MIN_AMPS
                    )
                    if current_control_state_at_command_start: # Om vi trodde vi laddade
                        await self._execute_stop_charging(current_charger_status, previous_intended_active_control_mode, f"Solenergi målström {current_target_amps}A för låg.")
                    self.active_control_mode_internal = None # Inget aktivt läge om vi inte kan ladda
                    self._prev_is_solar_reset(previous_intended_active_control_mode, new_intended_mode="AV") # Nollställ solar amps
                else:
                    charging_actually_started_or_continued = await self._execute_start_or_adjust_charging(
                        current_target_amps, current_charger_status,
                        previous_intended_active_control_mode, self.active_control_mode_internal,
                        reason_for_action
                    )
            else: # should_charge_flag är False
                if current_control_state_at_command_start: # Om vi tidigare styrde laddningen
                    await self._execute_stop_charging(current_charger_status, previous_intended_active_control_mode, reason_for_action)
                # Reaktivt stopp: Om vi inte styrde, men smartläge är på OCH laddaren laddar ändå
                elif not current_control_state_at_command_start and \
                     current_charger_status == "charging" and \
                     any_smart_mode_globally_enabled_by_switch:
                    _LOGGER.warning("REAKTIV STOPP: Laddare 'charging' trots att smartläge är aktivt och villkor för laddning ej uppfyllda. Tar kontroll och pausar.")
                    await self._execute_assert_control_and_pause("Reaktivt stopp pga oönskad laddning.")
                # Om alla smart-switchar är AV, och huvudswitchen är PÅ, stäng av huvudswitchen.
                elif not any_smart_mode_globally_enabled_by_switch and \
                     charger_main_enabled_state == STATE_ON and \
                     self.charger_enabled_switch_id:
                    _LOGGER.info("Alla smarta funktioner är AV. Huvudswitch (%s) är PÅ. Försöker pausa laddning och stänger sedan av huvudswitch.", self.charger_enabled_switch_id)
                    if current_charger_status in ["charging", "paused", "ready_to_charge", "awaiting_start"]:
                        await self._call_easee_service("action_command", "pause")
                    await self.hass.services.async_call("switch", SERVICE_TURN_OFF, {ATTR_ENTITY_ID: self.charger_enabled_switch_id}, blocking=False)
                    # Återställ interna tillstånd eftersom vi aktivt stänger av
                    self.is_smart_charging_controlled_now = False
                    self.active_control_mode_internal = None
                    self.last_commanded_solar_amps = 0.0
                    self._proactive_pause_done_this_connection = False


        # Uppdatera sensor för aktivt styrningsläge
        final_sensor_active_control_mode: str | None = None
        current_charger_status_for_sensor_check = self._get_entity_state(self.status_sensor_id) # Hämta färsk status

        if self.is_smart_charging_controlled_now and \
           current_charger_status_for_sensor_check == "charging" and \
           charging_actually_started_or_continued : # Och laddning faktiskt startade/fortsatte denna cykel
            final_sensor_active_control_mode = self.active_control_mode_internal

        # Jämför med föregående värde på sensorn för att se om loggning behövs
        current_display_mode_in_sensor = self.data.get("active_control_mode") if self.data else "AV"
        new_display_mode_for_sensor = final_sensor_active_control_mode if final_sensor_active_control_mode else "AV"

        if current_display_mode_in_sensor != new_display_mode_for_sensor:
            _LOGGER.info(
                "Sensor 'Aktivt Styrningsläge' ändras från '%s' till '%s'. (is_controlled: %s, status: %s, intended_mode: %s, charging_active_this_cycle: %s)",
                current_display_mode_in_sensor, new_display_mode_for_sensor,
                self.is_smart_charging_controlled_now, current_charger_status_for_sensor_check,
                self.active_control_mode_internal, charging_actually_started_or_continued
            )
        self.active_control_mode = final_sensor_active_control_mode


        # Ackumulera sessionsdata om vi styr och laddar
        if self.is_smart_charging_controlled_now and \
           current_charger_status_for_sensor_check == "charging" and \
           ev_power_w is not None and ev_power_w > 0:
            if self.update_interval: # Säkerställ att update_interval är satt
                dt_seconds = self.update_interval.total_seconds()
                energy_added_this_interval_kwh = (ev_power_w / 1000.0) * (dt_seconds / 3600.0)
                self.current_session_energy_kwh += energy_added_this_interval_kwh

                price_for_cost_calc = 0.0 # Endast Pris/Tid-läget ackumulerar kostnad baserat på totalpris
                if self.active_control_mode == "PRIS_TID" and current_total_price_for_cost is not None:
                    price_for_cost_calc = current_total_price_for_cost
                self.current_session_cost_sek += (energy_added_this_interval_kwh * price_for_cost_calc)

                if _LOGGER.isEnabledFor(logging.DEBUG): # Undvik onödig strängformatering
                    _LOGGER.debug(
                        "Sessionsdata: Energi ackumulerad=%.3fkWh (+%.4fkWh), Kostnad ackumulerad=%.2fSEK. EV Effekt: %.0fW. Totalpris: %.2f kr/kWh.",
                        self.current_session_energy_kwh, energy_added_this_interval_kwh,
                        self.current_session_cost_sek, ev_power_w,
                        current_total_price_for_cost if current_total_price_for_cost is not None else 0.0
                    )
        elif not (self.is_smart_charging_controlled_now and current_charger_status_for_sensor_check == "charging"):
            _LOGGER.debug(
                "Ingen ackumulering av sessionsdata: is_controlled_now=%s, charger_status=%s",
                self.is_smart_charging_controlled_now, current_charger_status_for_sensor_check
            )

        _LOGGER.debug(
            "Tillstånd EFTER logik: is_controlled_now=%s, Sensor Mode=%s, Intended Mode=%s, SolarAmps=%.1fA, ProactiveDone=%s",
            self.is_smart_charging_controlled_now, self.active_control_mode, self.active_control_mode_internal,
            self.last_commanded_solar_amps, self._proactive_pause_done_this_connection
        )
        _LOGGER.debug("--- Koordinator _async_update_data SLUT ---")
        return self._current_coordinator_data(reason_for_action)

    # Resten av hjälpfunktionerna (_get_spot_price_in_kr, etc.) förblir oförändrade

    def _get_spot_price_in_kr(self, spot_price_entity_id: str | None) -> float | None:
        if not spot_price_entity_id:
            _LOGGER.debug("Spotprissensor-ID saknas.")
            return None
        spot_price_state_obj = self.hass.states.get(spot_price_entity_id)
        if spot_price_state_obj is None or spot_price_state_obj.state in [
            STATE_UNAVAILABLE,
            STATE_UNKNOWN,
        ]:
            # Använd _get_entity_state för konsekvent loggning av otillgängliga entiteter
            self._get_entity_state(spot_price_entity_id)
            # _LOGGER.debug("Spotprissensor %s är %s eller None.", spot_price_entity_id, spot_price_state_obj.state if spot_price_state_obj else "None")
            return None
        try:
            price_val = float(spot_price_state_obj.state)
            unit = str(spot_price_state_obj.attributes.get("unit_of_measurement", "")).lower()
            # currency_code = str(spot_price_state_obj.attributes.get("currency", "")).lower() # Används ej aktivt f.n.

            if _LOGGER.isEnabledFor(logging.DEBUG): # Undvik onödig strängformatering
                 _LOGGER.debug(
                    "Spotpris: Värde=%.4f, Enhet='%s' från sensor %s",
                    price_val, unit, spot_price_entity_id
                )

            if "/mwh" in unit: # EUR/MWh, SEK/MWh etc.
                price_per_kwh = price_val / 1000.0
                # Omvandla öre/MWh till kr/kWh (indirekt, om enheten innehåller "öre")
                return (price_per_kwh / 100.0) if "öre" in unit or "ore" in unit else price_per_kwh
            if "öre/kwh" in unit or "ore/kwh" in unit: # öre/kWh
                return price_val / 100.0
            # Anta att det är kr/kWh om ingen öre/MWh-logik träffat
            if any(u in unit for u in ["sek/kwh", "nok/kwh", "dkk/kwh", "eur/kwh", "kr/kwh", "/kwh"]):
                return price_val
            # Om enheten bara är en valuta, anta att det är per kWh.
            if unit in ["sek", "nok", "dkk", "eur", "kr"]:
                _LOGGER.warning("Spotprissensor %s har enhet '%s' utan '/kWh'. Antar att värdet är per kWh i angiven valuta.", spot_price_entity_id, unit)
                return price_val

            _LOGGER.warning("Okänd enhet '%s' för spotprissensor %s. Försöker tolka värdet som det är, kan ge felaktig beräkning.", unit if unit else "saknas", spot_price_entity_id)
            return price_val # Fallback, kan vara fel men bättre än inget om det är numeriskt.

        except (ValueError, TypeError):
            _LOGGER.warning("Kunde inte konvertera spotpris '%s' från %s.", spot_price_state_obj.state, spot_price_entity_id)
            return None

    def _calculate_total_price(
        self, spot_price_kr_val: float | None, surcharge_entity_id: str | None
    ) -> float | None:
        """Beräknar totalt pris inklusive påslag."""
        surcharge_kr_per_kwh = self._get_surcharge_in_kr_kwh(surcharge_entity_id) # Denna är redan i kr/kWh

        if spot_price_kr_val is None:
            _LOGGER.debug("Spotpris (kr/kWh) saknas för totalprisberäkning.")
            return None

        total_price = spot_price_kr_val + surcharge_kr_per_kwh
        return round(total_price, 3) # Avrunda till 3 decimaler

    def _get_surcharge_in_kr_kwh(self, surcharge_entity_id: str | None) -> float:
        """Hämtar och normaliserar påslag till kr/kWh."""
        if not surcharge_entity_id:
            _LOGGER.debug("Påslags-ID saknas, antar 0.0 kr/kWh.")
            return 0.0

        surcharge_state_obj = self.hass.states.get(surcharge_entity_id)
        if surcharge_state_obj is None or surcharge_state_obj.state in [STATE_UNAVAILABLE, STATE_UNKNOWN]:
            self._get_entity_state(surcharge_entity_id) # För loggning av otillgänglighet
            # _LOGGER.debug("Påslagsentitet %s är %s, antar 0.0 kr/kWh.", surcharge_entity_id, surcharge_state_obj.state if surcharge_state_obj else "None")
            return 0.0

        try:
            val = float(surcharge_state_obj.state)
            unit = str(surcharge_state_obj.attributes.get("unit_of_measurement", "")).lower()
            if _LOGGER.isEnabledFor(logging.DEBUG):
                _LOGGER.debug("Påslag: Värde=%.4f, Enhet='%s' från entitet %s", val, unit, surcharge_entity_id)

            if "öre/kwh" in unit or "ore/kwh" in unit:
                return val / 100.0
            # Anta kr/kWh om enheten innehåller kr eller valuta/kWh
            elif any(u in unit for u in ["sek/kwh", "nok/kwh", "dkk/kwh", "eur/kwh", "kr/kwh", "/kwh"]):
                return val
            elif unit in ["sek", "nok", "dkk", "eur", "kr"]: # Bara valuta, anta per kWh
                 _LOGGER.warning("Påslagsentitet %s har enhet '%s' utan '/kWh'. Antar kr/kWh.", surcharge_entity_id, unit)
                 return val
            else: # Okänd eller ingen enhet
                if unit and unit != "": _LOGGER.warning("Okänd enhet '%s' för påslagsentitet %s. Antar kr/kWh.", unit, surcharge_entity_id)
                elif not unit: _LOGGER.info("Påslagsentitet %s saknar enhet. Antar kr/kWh.", surcharge_entity_id)
                return val # Returnera värdet som det är, kan vara fel om enhet är t.ex. öre.
        except (ValueError, TypeError):
            _LOGGER.warning("Kunde inte konvertera påslagsvärde '%s' från %s, antar 0.0 kr/kWh.", surcharge_state_obj.state, surcharge_entity_id)
            return 0.0

    def _is_schedule_active(self, schedule_entity_id: str | None) -> bool:
        """Kontrollerar om ett schema är aktivt. Returnerar True om inget schema är definierat."""
        if not schedule_entity_id:
            return True # Inget schema = alltid "aktivt" ur detta perspektiv
        state = self._get_entity_state(schedule_entity_id)
        is_active = state == STATE_ON
        _LOGGER.debug("Schema %s är aktivt: %s (status: %s)", schedule_entity_id, is_active, state or "Okänd")
        return is_active

    def _get_entity_state(self, entity_id: str | None) -> str | None:
        """Hämtar tillstånd för en entitet och loggar varnande om den inte hittas eller är otillgänglig."""
        if not entity_id:
            # _LOGGER.debug("Försökte hämta state för None entity_id.") # Kan vara för mycket loggar
            return None

        state_obj = self.hass.states.get(entity_id)

        # Hantera loggning för entiteter som inte hittas eller är otillgängliga (för att minska loggspam)
        log_attr_not_found = f"_logged_not_found_{entity_id.replace('.', '_')}"
        log_attr_unavailable = f"_logged_unavailable_{entity_id.replace('.', '_')}"

        if state_obj is None:
            if not getattr(self, log_attr_not_found, False):
                _LOGGER.warning("Entitet %s hittades INTE i Home Assistant.", entity_id)
                setattr(self, log_attr_not_found, True)
            return STATE_UNKNOWN # Eller None, beroende på hur det ska hanteras vidare
        else: # Entiteten hittades
            if hasattr(self, log_attr_not_found): # Om vi tidigare loggat "not_found"
                _LOGGER.info("Entitet %s är nu HITTAD (tidigare ej hittad). Status: %s.", entity_id, state_obj.state)
                delattr(self, log_attr_not_found)

            if state_obj.state in [STATE_UNAVAILABLE, STATE_UNKNOWN]:
                if not getattr(self, log_attr_unavailable, False):
                    _LOGGER.warning("Entitet %s är %s.", entity_id, state_obj.state)
                    setattr(self, log_attr_unavailable, True)
            else: # Entiteten är tillgänglig och har ett "bra" state
                if hasattr(self, log_attr_unavailable): # Om vi tidigare loggat "unavailable"
                    _LOGGER.info("Entitet %s är nu TILLGÄNGLIG (tidigare %s). Status: %s.", entity_id, getattr(self, log_attr_unavailable, "otillgänglig"), state_obj.state)
                    delattr(self, log_attr_unavailable)
            return state_obj.state

    def _get_number_value(self, entity_id: str | None, default_value: float) -> float:
        """Hämtar ett numeriskt värde från en entitet (oftast input_number)."""
        if not entity_id:
            return default_value

        state_str = self._get_entity_state(entity_id) # Använder vår wrapper för state-hämtning

        if state_str in [STATE_UNKNOWN, STATE_UNAVAILABLE] or state_str is None:
            _LOGGER.debug("Nummerentitet %s är %s, använder default %s.", entity_id, state_str or "None", default_value)
            return default_value
        try:
            return float(state_str)
        except (ValueError, TypeError):
            _LOGGER.warning("Kunde inte konvertera nummervärde '%s' från %s, använder default %s.", state_str, entity_id, default_value)
            return default_value

    def _get_power_value(self, entity_id: str | None) -> float | None:
        """Hämtar effektvärde från en sensor och normaliserar till Watt."""
        if not entity_id:
            return None # Ingen sensor, inget värde

        state_obj = self.hass.states.get(entity_id) # Behöver state_obj för attribut
        state_str = self._get_entity_state(entity_id) # Använder vår wrapper, men behöver attribut från state_obj

        if state_str in [STATE_UNKNOWN, STATE_UNAVAILABLE] or state_str is None or state_obj is None:
            # Loggning sköts av _get_entity_state om sensorn är otillgänglig
            return None

        try:
            val = float(state_obj.state) # Använd state_obj.state för att vara säker
            unit = cast(str, state_obj.attributes.get("unit_of_measurement", "")).lower()

            if unit in (UnitOfPower.KILO_WATT, "kw"):
                return val * 1000.0
            if unit in (UnitOfPower.WATT, "w"):
                return val

            # Om enhet saknas eller är okänd, anta Watt om värdet är numeriskt.
            _LOGGER.warning("Okänd eller saknad enhet ('%s') för effektsensor %s (värde: %s). Antar Watt.", unit, entity_id, val)
            return val
        except (ValueError, TypeError):
            _LOGGER.warning("Kunde inte konvertera effektvärde '%s' från %s.", state_obj.state, entity_id)
            return None

    def _current_coordinator_data(self, reason: str | None = None) -> dict[str, Any]:
        """Returnerar aktuell data som koordinatorn tillhandahåller till sensorer etc."""
        data = {
            "session_energy_kwh": round(self.current_session_energy_kwh, 3),
            "session_cost_sek": round(self.current_session_cost_sek, 2),
            "active_control_mode": self.active_control_mode if self.active_control_mode else "AV",
            "session_start_time_utc": self.session_start_time_utc,
            "debug_logging_enabled": self.debug_logging_enabled, # Inkludera för eventuell framtida användning
        }
        if reason: # Lägg bara till anledning om den finns
            data["should_charge_reason"] = reason
        return data