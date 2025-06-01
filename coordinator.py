# File version: 2025-05-31 0.1.40 (Ny version efter korrigering)
import logging
from datetime import timedelta, datetime
from typing import Any, cast, Callable
import math
import asyncio

from homeassistant.core import HomeAssistant, Event, CALLBACK_TYPE, callback
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
    CONF_CHARGER_DYNAMIC_CURRENT_SENSOR,
    CONF_EV_POWER_SENSOR,
    CONF_SCAN_INTERVAL,
    CONF_CHARGER_ENABLED_SWITCH_ID,
    CONF_EV_SOC_SENSOR,
    CONF_TARGET_SOC_LIMIT,
    ENTITY_ID_SUFFIX_SMART_ENABLE_SWITCH,
    ENTITY_ID_SUFFIX_MAX_PRICE_NUMBER,
    ENTITY_ID_SUFFIX_ENABLE_SOLAR_CHARGING_SWITCH,
    ENTITY_ID_SUFFIX_SOLAR_BUFFER_NUMBER,
    ENTITY_ID_SUFFIX_MIN_SOLAR_CHARGE_CURRENT_A_NUMBER,
    ENTITY_ID_SUFFIX_ACTIVE_CONTROL_MODE_SENSOR,
    EASEE_SERVICE_SET_DYNAMIC_CURRENT,
    EASEE_SERVICE_PAUSE_CHARGING,
    EASEE_SERVICE_RESUME_CHARGING,
    EASEE_STATUS_DISCONNECTED,
    EASEE_STATUS_AWAITING_START,
    EASEE_STATUS_READY_TO_CHARGE,
    EASEE_STATUS_CHARGING,
    EASEE_STATUS_PAUSED,
    EASEE_STATUS_COMPLETED,
    EASEE_STATUS_ERROR,
    EASEE_STATUS_OFFLINE,
    CONTROL_MODE_PRICE_TIME,
    CONTROL_MODE_SOLAR_SURPLUS,
    CONTROL_MODE_MANUAL,
    MIN_CHARGE_CURRENT_A,
    MAX_CHARGE_CURRENT_A_HW_DEFAULT,
    POWER_MARGIN_W,
    SOLAR_SURPLUS_DELAY_SECONDS,
    PHASES,
    VOLTAGE_PHASE_NEUTRAL,
)

_LOGGER = logging.getLogger(f"custom_components.{DOMAIN}")


class SmartEVChargingCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Huvudkoordinator för Smart EV Charging."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, scan_interval_seconds: int
    ) -> None:
        """Initialisera koordinatorn."""
        self.hass = hass
        self.entry = entry
        self.config = entry.data | entry.options

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval_seconds),
        )
        _LOGGER.info(
            "SmartEVChargingCoordinator initialiserad med update_interval: %s sekunder.",
            self.update_interval,
        )

        self.listeners: list[CALLBACK_TYPE] = []
        self.active_control_mode: str = CONTROL_MODE_MANUAL
        self.should_charge_flag: bool = False
        self.target_charge_current_a: float = MIN_CHARGE_CURRENT_A
        self.active_control_mode_internal: str | None = (
            None  # Används för att bestämma self.active_control_mode
        )
        self.charger_main_switch_state: bool = True
        self.last_update_time: datetime = dt_util.utcnow()
        self.session_start_time_utc: datetime | None = None
        self._solar_surplus_start_time: datetime | None = None
        self._solar_session_active: bool = False
        self._price_time_eligible_for_charging: bool = False
        self._last_price_check_time: datetime | None = None
        self.smart_enable_switch_entity_id: str | None = None
        self.max_price_entity_id: str | None = None
        self.solar_enable_switch_entity_id: str | None = None
        self.solar_buffer_entity_id: str | None = None
        self.min_solar_charge_current_entity_id: str | None = None
        self._internal_entities_resolved: bool = False

    async def _resolve_internal_entities(self) -> bool:
        if self._internal_entities_resolved:
            return True
        _LOGGER.debug("Koordinator: _resolve_internal_entities STARTAR.")
        try:
            ent_reg: EntityRegistry = async_get_entity_registry(self.hass)
            self.smart_enable_switch_entity_id = ent_reg.async_get_entity_id(
                "switch",
                DOMAIN,
                f"{self.entry.entry_id}_{ENTITY_ID_SUFFIX_SMART_ENABLE_SWITCH}",
            )
            self.max_price_entity_id = ent_reg.async_get_entity_id(
                "number",
                DOMAIN,
                f"{self.entry.entry_id}_{ENTITY_ID_SUFFIX_MAX_PRICE_NUMBER}",
            )
            self.solar_enable_switch_entity_id = ent_reg.async_get_entity_id(
                "switch",
                DOMAIN,
                f"{self.entry.entry_id}_{ENTITY_ID_SUFFIX_ENABLE_SOLAR_CHARGING_SWITCH}",
            )
            self.solar_buffer_entity_id = ent_reg.async_get_entity_id(
                "number",
                DOMAIN,
                f"{self.entry.entry_id}_{ENTITY_ID_SUFFIX_SOLAR_BUFFER_NUMBER}",
            )
            self.min_solar_charge_current_entity_id = ent_reg.async_get_entity_id(
                "number",
                DOMAIN,
                f"{self.entry.entry_id}_{ENTITY_ID_SUFFIX_MIN_SOLAR_CHARGE_CURRENT_A_NUMBER}",
            )

            if not all(
                [
                    self.smart_enable_switch_entity_id,
                    self.max_price_entity_id,
                    self.solar_enable_switch_entity_id,
                    self.solar_buffer_entity_id,
                    self.min_solar_charge_current_entity_id,
                ]
            ):
                _LOGGER.debug(
                    "Ett eller flera interna ID:n ej redo under _resolve_internal_entities."
                )
                self._internal_entities_resolved = False
                return False

            self._internal_entities_resolved = True
            _LOGGER.debug("Koordinator: Interna ID:n OK.")
            return True
        except Exception as e:
            _LOGGER.error("Fel i _resolve_internal_entities: %s", e, exc_info=True)
            self._internal_entities_resolved = False
            return False

    def _setup_listeners(self) -> None:
        _LOGGER.debug("Sätter upp lyssnare...")
        self._remove_listeners()
        external_entities = [
            self.config.get(CONF_STATUS_SENSOR),
            self.config.get(CONF_PRICE_SENSOR),
            self.config.get(CONF_TIME_SCHEDULE_ENTITY),
            self.config.get(CONF_HOUSE_POWER_SENSOR),
            self.config.get(CONF_SOLAR_PRODUCTION_SENSOR),
            self.config.get(CONF_SOLAR_SCHEDULE_ENTITY),
            self.config.get(CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR),
            self.config.get(CONF_CHARGER_DYNAMIC_CURRENT_SENSOR),
            self.config.get(CONF_CHARGER_ENABLED_SWITCH_ID),
            self.config.get(CONF_EV_SOC_SENSOR),
        ]
        all_entities_to_listen = [
            entity_id for entity_id in external_entities if entity_id
        ]
        if all_entities_to_listen:
            _LOGGER.debug(
                "Lyssnar på tillståndsförändringar för externa entiteter: %s",
                all_entities_to_listen,
            )
            self.listeners.append(
                async_track_state_change_event(
                    self.hass,
                    all_entities_to_listen,
                    self._handle_external_state_change,
                )
            )
        else:
            _LOGGER.info("Inga externa entiteter konfigurerade för lyssning.")

    def _remove_listeners(self) -> None:
        if self.listeners:
            _LOGGER.debug("Tar bort %s lyssnare.", len(self.listeners))
        while self.listeners:
            unsub = self.listeners.pop()
            unsub()

    @callback
    def _handle_external_state_change(self, event: Event) -> None:
        entity_id = event.data.get("entity_id")
        old_state_obj = event.data.get("old_state")
        new_state_obj = event.data.get("new_state")
        old_state_val = old_state_obj.state if old_state_obj else "None"
        new_state_val = new_state_obj.state if new_state_obj else "None"
        if old_state_val == new_state_val and entity_id != self.config.get(
            CONF_STATUS_SENSOR
        ):
            return
        _LOGGER.info(
            "Tillståndsförändring detekterad för %s: Gammalt=%s, Nytt=%s. Begär refresh.",
            entity_id,
            old_state_val,
            new_state_val,
        )
        self.hass.async_create_task(self.async_request_refresh())

    async def _get_number_value(
        self,
        entity_id_or_key: str | None,
        default_value: float | None = None,
        is_config_key: bool = True,
    ) -> float | None:
        entity_id_to_check = entity_id_or_key
        if is_config_key:
            if not entity_id_or_key:
                _LOGGER.debug(
                    "Konfigurationsnyckel (som var None) för nummer är inte satt."
                )
                return default_value
            entity_id_to_check = self.config.get(str(entity_id_or_key))

        if not entity_id_to_check:
            if is_config_key:
                _LOGGER.debug(
                    "Konfigurationsnyckel %s för nummer är inte satt (resulterade i tomt entitets-ID).",
                    entity_id_or_key,
                )
            else:
                _LOGGER.debug("Entitets-ID för nummer är inte satt (var None/tomt).")
            return default_value

        state_obj = self.hass.states.get(str(entity_id_to_check))
        if state_obj is None or state_obj.state in [STATE_UNAVAILABLE, STATE_UNKNOWN]:
            _LOGGER.warning(
                "Entitet %s är otillgänglig eller har okänt tillstånd.",
                entity_id_to_check,
            )
            return default_value
        try:
            return float(state_obj.state)
        except (ValueError, TypeError):
            _LOGGER.warning(
                "Kunde inte konvertera värde '%s' från %s till float.",
                state_obj.state,
                entity_id_to_check,
            )
            return default_value

    async def _get_spot_price_in_kr(self) -> float | None:
        entity_id = self.config.get(CONF_PRICE_SENSOR)
        if not entity_id:
            return None
        state_obj = self.hass.states.get(str(entity_id))
        if state_obj is None or state_obj.state in [STATE_UNAVAILABLE, STATE_UNKNOWN]:
            _LOGGER.warning("Elprissensor %s är otillgänglig.", entity_id)
            return None
        try:
            price = float(state_obj.state)
            unit = str(state_obj.attributes.get("unit_of_measurement", "")).lower()
            if "öre" in unit or "/100kwh" in unit:
                price /= 100
            elif "mwh" in unit:
                price /= 1000
            return price
        except (ValueError, TypeError):
            _LOGGER.warning(
                "Kunde inte konvertera elprisvärde '%s' från %s.",
                state_obj.state,
                entity_id,
            )
            return None

    async def _get_power_value(self, entity_id_key: str) -> float | None:
        entity_id = self.config.get(entity_id_key)
        if not entity_id:
            return None
        state_obj = self.hass.states.get(str(entity_id))
        if state_obj is None or state_obj.state in [STATE_UNAVAILABLE, STATE_UNKNOWN]:
            _LOGGER.debug(
                "Effektsensor %s (%s) otillgänglig.", entity_id_key, entity_id
            )
            return None
        try:
            val = float(state_obj.state)
            unit = cast(
                str, state_obj.attributes.get("unit_of_measurement", "")
            ).lower()
            if unit in (UnitOfPower.KILO_WATT, "kw"):
                return val * 1000.0
            if unit in (UnitOfPower.WATT, "w"):
                return val
            _LOGGER.warning(
                "Okänd enhet ('%s') för effektsensor %s. Antar Watt.", unit, entity_id
            )
            return val
        except (ValueError, TypeError):
            _LOGGER.warning(
                "Kunde inte konvertera effektvärde '%s' från %s.",
                state_obj.state,
                entity_id,
            )
            return None

    def _reset_session_data(self, reason: str = "Okänd") -> None:
        _LOGGER.info("Återställer sessionsdata. Anledning: %s", reason)
        self.session_start_time_utc = None

    async def _control_charger(
        self, should_charge: bool, current_a: float, reason: str
    ) -> None:
        # >>> NY KOD STARTAR HÄR <<<
        # self.charger_main_switch_state uppdateras i _async_update_data precis innan denna funktion anropas.
        if not self.charger_main_switch_state:  # Om huvudströmbrytaren är AV
            _LOGGER.info(
                "Huvudströmbrytare är AV (enligt koordinatorns interna tillstånd). "
                "Inga kommandon skickas till laddaren."
            )
            return  # Avbryt och skicka inga kommandon
        # >>> NY KOD SLUTAR HÄR <<<

        charger_master_switch_id = self.config.get(CONF_CHARGER_ENABLED_SWITCH_ID)
        status_sensor_id = self.config.get(CONF_STATUS_SENSOR)
        charger_status_state = (
            self.hass.states.get(str(status_sensor_id)) if status_sensor_id else None
        )
        charger_status = (
            charger_status_state.state.lower()
            if charger_status_state and isinstance(charger_status_state.state, str)
            else STATE_UNKNOWN
        )

        charger_hw_max_amps_entity_id = self.config.get(
            CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR
        )
        _charger_hw_max_amps = MAX_CHARGE_CURRENT_A_HW_DEFAULT
        if charger_hw_max_amps_entity_id:
            val_from_sensor = await self._get_number_value(
                charger_hw_max_amps_entity_id,
                default_value=MAX_CHARGE_CURRENT_A_HW_DEFAULT,
                is_config_key=False,
            )
            if val_from_sensor is not None:
                _charger_hw_max_amps = val_from_sensor

        current_a = max(MIN_CHARGE_CURRENT_A, min(current_a, _charger_hw_max_amps))

        current_dynamic_limit_entity_id = self.config.get(
            CONF_CHARGER_DYNAMIC_CURRENT_SENSOR
        )
        current_dynamic_limit = None
        if current_dynamic_limit_entity_id:
            current_dynamic_limit = await self._get_number_value(
                current_dynamic_limit_entity_id, is_config_key=False
            )

        _LOGGER.debug(
            "Charger Control: should_charge=%s, current_a=%.1fA (begränsad av %.1fA HW), status=%s, reason='%s', current_dyn_limit=%.1fA",
            should_charge,
            current_a,
            _charger_hw_max_amps,
            charger_status,
            reason,
            current_dynamic_limit if current_dynamic_limit is not None else -1.0,
        )

        if not charger_master_switch_id:
            _LOGGER.error("Huvudströmbrytare för laddboxen är inte konfigurerad.")
            return
        try:
            current_master_switch_state = self.hass.states.get(charger_master_switch_id)
            if (
                current_master_switch_state
                and current_master_switch_state.state == STATE_OFF
                and should_charge
            ):
                _LOGGER.info(
                    "Huvudströmbrytare %s är AV, men laddning begärs (%s). Försöker slå PÅ.",
                    charger_master_switch_id,
                    reason,
                )
                await self.hass.services.async_call(
                    "homeassistant",
                    SERVICE_TURN_ON,
                    {ATTR_ENTITY_ID: charger_master_switch_id},
                    blocking=False,
                )
                await asyncio.sleep(2)
                charger_status_state = (
                    self.hass.states.get(str(status_sensor_id))
                    if status_sensor_id
                    else None
                )
                charger_status = (
                    charger_status_state.state.lower()
                    if charger_status_state
                    and isinstance(charger_status_state.state, str)
                    else STATE_UNKNOWN
                )

            if should_charge:

                async def set_current_if_needed_locally():
                    if current_dynamic_limit is None or round(
                        current_dynamic_limit, 1
                    ) != round(current_a, 1):
                        _LOGGER.debug(
                            "Målström (%.1fA) skiljer sig från nuvarande dynamiska gräns (%.1fA) eller nuvarande är okänd. Skickar uppdatering.",
                            current_a,
                            current_dynamic_limit
                            if current_dynamic_limit is not None
                            else -1.0,
                        )
                        await self.hass.services.async_call(
                            "easee",
                            EASEE_SERVICE_SET_DYNAMIC_CURRENT,
                            {
                                "device_id": self.config.get(CONF_CHARGER_DEVICE),
                                "circuit_id": 1,
                                "currentP1": current_a,
                                "currentP2": current_a,
                                "currentP3": current_a,
                            },
                            blocking=False,
                        )
                    else:
                        _LOGGER.debug(
                            "Målström (%.1fA) är redan satt enligt dynamisk gränssensor. Ingen uppdatering behövs.",
                            current_a,
                        )

                if (
                    charger_status in EASEE_STATUS_READY_TO_CHARGE
                    or charger_status == EASEE_STATUS_AWAITING_START
                    or charger_status == EASEE_STATUS_PAUSED
                    or charger_status == EASEE_STATUS_COMPLETED
                ):
                    _LOGGER.info(
                        "Startar/återupptar laddning eller justerar ström till %.1fA. Anledning: %s. Status: %s",
                        current_a,
                        reason,
                        charger_status,
                    )
                    await set_current_if_needed_locally()
                    if charger_status != EASEE_STATUS_CHARGING:
                        # -- KORRIGERING 1 av 2: Använder 'action_command' med 'resume' för att starta.
                        await self.hass.services.async_call(
                            "easee",
                            "action_command",
                            {
                                "device_id": self.config.get(CONF_CHARGER_DEVICE),
                                "action_command": "resume",
                            },
                            blocking=False,
                        )

                    # Hantera start av session korrekt
                    if self.session_start_time_utc is None:
                        _LOGGER.info(
                            "Startar ny laddningssession. Anledning: %s",
                            f"Laddning startad/återupptagen ({reason})",
                        )
                        self.session_start_time_utc = dt_util.utcnow()

                elif charger_status == EASEE_STATUS_CHARGING:
                    _LOGGER.debug(
                        "Laddning pågår. Justerar dynamisk ström vid behov till %.1fA. Anledning: %s",
                        current_a,
                        reason,
                    )
                    await set_current_if_needed_locally()
                elif (
                    charger_status in EASEE_STATUS_DISCONNECTED
                    or charger_status == EASEE_STATUS_OFFLINE
                ):
                    _LOGGER.warning(
                        "Laddning begärd, men laddaren är frånkopplad/offline (status: %s).",
                        charger_status,
                    )
                    if self.session_start_time_utc is not None:
                        self._reset_session_data(
                            f"Laddare frånkopplad/offline ({charger_status})"
                        )
                else:
                    _LOGGER.info(
                        "Laddning begärd (Anledning: %s), men laddarstatus är %s. Inväntar lämpligt tillstånd.",
                        reason,
                        charger_status,
                    )
            else:  # should_charge is False
                if charger_status == EASEE_STATUS_CHARGING or (
                    charger_status == EASEE_STATUS_PAUSED
                    and self.active_control_mode_internal != CONTROL_MODE_MANUAL
                ):
                    _LOGGER.info(
                        "Stoppar/pausar laddning. Anledning: %s. Status: %s",
                        reason,
                        charger_status,
                    )
                    # -- KORRIGERING 2 av 2: Använder 'action_command' med 'pause' för att stoppa.
                    await self.hass.services.async_call(
                        "easee",
                        "action_command",
                        {
                            "device_id": self.config.get(CONF_CHARGER_DEVICE),
                            "action_command": "pause",
                        },
                        blocking=False,
                    )
                    if self.session_start_time_utc is not None:
                        self._reset_session_data(f"Laddning stoppad/pausad ({reason})")
                else:
                    _LOGGER.debug(
                        "Ingen laddning begärd och laddaren är inte aktivt laddande (status: %s). Anledning till ingen laddning: %s",
                        charger_status,
                        reason,
                    )
                    if (
                        self.session_start_time_utc is not None
                        and charger_status
                        not in [
                            EASEE_STATUS_AWAITING_START,
                            EASEE_STATUS_READY_TO_CHARGE,
                            EASEE_STATUS_PAUSED,
                        ]
                    ):
                        self._reset_session_data(
                            f"Laddningssession avslutad (status: {charger_status}, Anledning: {reason})"
                        )
        except Exception as e:
            _LOGGER.error("Fel vid styrning av laddaren: %s", e, exc_info=True)

    async def _async_update_data(self) -> dict[str, Any]:
        _LOGGER.debug("Koordinatorn kör _async_update_data")
        self.config = self.entry.data | self.entry.options

        if not self._internal_entities_resolved:
            if not await self._resolve_internal_entities():
                _LOGGER.warning(
                    "Interna entiteter kunde inte lösas, avbryter uppdateringscykeln."
                )
                return (
                    self.data
                    if self.data
                    else {
                        "active_control_mode": CONTROL_MODE_MANUAL,
                        "should_charge_reason": "Väntar på interna entiteter.",
                    }
                )

        current_time = dt_util.utcnow()
        charger_status_sensor_id = self.config.get(CONF_STATUS_SENSOR)
        charger_status_state = (
            self.hass.states.get(str(charger_status_sensor_id))
            if charger_status_sensor_id
            else None
        )
        charger_status = (
            charger_status_state.state.lower()
            if charger_status_state and isinstance(charger_status_state.state, str)
            else STATE_UNKNOWN
        )

        charger_main_switch_id = self.config.get(CONF_CHARGER_ENABLED_SWITCH_ID)
        main_switch_state_obj = (
            self.hass.states.get(str(charger_main_switch_id))
            if charger_main_switch_id
            else None
        )
        self.charger_main_switch_state = (
            main_switch_state_obj.state == STATE_ON if main_switch_state_obj else True
        )

        smart_charging_enabled = self.hass.states.is_state(
            self.smart_enable_switch_entity_id, STATE_ON
        )
        solar_charging_enabled = self.hass.states.is_state(
            self.solar_enable_switch_entity_id, STATE_ON
        )

        current_price_kr = await self._get_spot_price_in_kr()
        surcharge_kr = (
            await self._get_number_value(CONF_SURCHARGE_HELPER, 0.0, is_config_key=True)
            or 0.0
        )
        total_price_kr = (
            (current_price_kr + surcharge_kr) if current_price_kr is not None else None
        )
        max_accepted_price_kr = (
            await self._get_number_value(
                self.max_price_entity_id, 999.0, is_config_key=False
            )
            or 999.0
        )

        time_schedule_entity_id = self.config.get(CONF_TIME_SCHEDULE_ENTITY)
        time_schedule_active = (
            self.hass.states.is_state(str(time_schedule_entity_id), STATE_ON)
            if time_schedule_entity_id
            else True
        )

        solar_schedule_entity_id = self.config.get(CONF_SOLAR_SCHEDULE_ENTITY)
        solar_schedule_active = (
            self.hass.states.is_state(str(solar_schedule_entity_id), STATE_ON)
            if solar_schedule_entity_id
            else True
        )

        current_house_power_w = await self._get_power_value(CONF_HOUSE_POWER_SENSOR)
        current_solar_production_w = (
            await self._get_power_value(CONF_SOLAR_PRODUCTION_SENSOR) or 0.0
        )

        charger_hw_max_amps_entity_id = self.config.get(
            CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR
        )
        charger_hw_max_amps = MAX_CHARGE_CURRENT_A_HW_DEFAULT
        if charger_hw_max_amps_entity_id:
            val_from_sensor = await self._get_number_value(
                charger_hw_max_amps_entity_id,
                default_value=MAX_CHARGE_CURRENT_A_HW_DEFAULT,
                is_config_key=False,
            )
            if val_from_sensor is not None:
                charger_hw_max_amps = val_from_sensor

        ev_soc_sensor_entity_id = self.config.get(CONF_EV_SOC_SENSOR)
        current_soc_percent = None
        if ev_soc_sensor_entity_id:
            current_soc_percent = await self._get_number_value(
                ev_soc_sensor_entity_id, is_config_key=False
            )

        target_soc_limit_config = self.config.get(CONF_TARGET_SOC_LIMIT)
        target_soc_limit = (
            float(target_soc_limit_config)
            if target_soc_limit_config is not None
            else None
        )

        _min_solar_current_from_sensor = await self._get_number_value(
            self.min_solar_charge_current_entity_id,
            default_value=None,
            is_config_key=False,
        )
        min_solar_charge_current_a = (
            _min_solar_current_from_sensor
            if _min_solar_current_from_sensor is not None
            else MIN_CHARGE_CURRENT_A
        )

        _solar_buffer_from_sensor = await self._get_number_value(
            self.solar_buffer_entity_id, default_value=None, is_config_key=False
        )
        solar_buffer_w = (
            _solar_buffer_from_sensor
            if _solar_buffer_from_sensor is not None
            else POWER_MARGIN_W
        )

        self.should_charge_flag = False
        self.target_charge_current_a = charger_hw_max_amps
        reason_for_action = "Ingen styrning aktiv."
        self.active_control_mode_internal = CONTROL_MODE_MANUAL

        if (
            charger_status in EASEE_STATUS_DISCONNECTED
            or charger_status == EASEE_STATUS_OFFLINE
        ):
            self.active_control_mode_internal = CONTROL_MODE_MANUAL
            self.should_charge_flag = False
            reason_for_action = (
                f"Laddaren är frånkopplad/offline (status: {charger_status})."
            )
            if self.session_start_time_utc is not None:
                self._reset_session_data(reason_for_action)
            self._solar_surplus_start_time = None
            self._solar_session_active = False
            self._price_time_eligible_for_charging = False

        elif not self.charger_main_switch_state:  # Om huvudströmbrytaren är AV
            # Kontrollera om en smart session var aktiv precis innan detta
            # Notera: self.active_control_mode_internal har ännu inte satts till CONTROL_MODE_MANUAL för denna cykel
            # så vi kan använda dess tidigare värde för att se om en smart session var igång.
            # Eller, mer robust, kolla om self.session_start_time_utc var satt, vilket indikerar en aktiv session.

            charger_main_switch_entity_id = self.config.get(
                CONF_CHARGER_ENABLED_SWITCH_ID
            )  # Hämta ID för loggning

            # Om en session pågick (indikerat av session_start_time_utc) OCH
            # det inte redan var manuellt läge (vilket det inte borde vara om en session pågick)
            if (
                self.session_start_time_utc is not None
                and self.active_control_mode != CONTROL_MODE_MANUAL
            ):
                _LOGGER.info(  # Testet förväntar sig INFO-nivå
                    "Huvudströmbrytaren %s stängdes av under en aktiv smart laddning. Återgår till manuellt läge.",
                    charger_main_switch_entity_id or "Okänd huvudströmbrytare",
                )

            self.active_control_mode_internal = CONTROL_MODE_MANUAL
            self.should_charge_flag = False
            reason_for_action = "Huvudströmbrytare för laddbox är AV."

            if (
                self.session_start_time_utc is not None
            ):  # Om en session var aktiv, återställ den
                self._reset_session_data(
                    reason_for_action
                )  # Denna loggar "Återställer sessionsdata..."

            self._solar_surplus_start_time = None
            self._solar_session_active = False
            self._price_time_eligible_for_charging = False
        # elif not self.charger_main_switch_state:
        #     self.active_control_mode_internal = CONTROL_MODE_MANUAL
        #     self.should_charge_flag = False
        #     reason_for_action = "Huvudströmbrytare för laddbox är AV."
        #     if self.session_start_time_utc is not None:
        #         self._reset_session_data(reason_for_action)
        #     self._solar_surplus_start_time = None
        #     self._solar_session_active = False
        #     self._price_time_eligible_for_charging = False
        elif (
            current_soc_percent is not None
            and target_soc_limit is not None
            and current_soc_percent >= target_soc_limit
        ):
            self.active_control_mode_internal = CONTROL_MODE_MANUAL
            self.should_charge_flag = False
            reason_for_action = (
                f"SoC ({current_soc_percent}%) har nått målet ({target_soc_limit}%)."
            )
            if self.session_start_time_utc is not None:
                self._reset_session_data(reason_for_action)
            self._solar_surplus_start_time = None
            self._solar_session_active = False
            self._price_time_eligible_for_charging = False
        else:
            price_time_conditions_met = False
            if smart_charging_enabled:
                price_ok = (
                    total_price_kr is not None
                    and total_price_kr <= max_accepted_price_kr
                )
                if price_ok and time_schedule_active:
                    price_time_conditions_met = True

            if price_time_conditions_met:
                self.active_control_mode_internal = CONTROL_MODE_PRICE_TIME
                self.should_charge_flag = True
                self.target_charge_current_a = charger_hw_max_amps
                reason_for_action = f"Pris/Tid-laddning aktiv (Pris: {total_price_kr:.2f} <= {max_accepted_price_kr:.2f} kr, Tidsschema PÅ)."
                self._solar_surplus_start_time = None
                self._solar_session_active = False
                if (
                    self.session_start_time_utc is None
                    or not self._price_time_eligible_for_charging
                ):
                    if (
                        self.session_start_time_utc is not None
                    ):  # Om det fanns en session (t.ex. sol)
                        _LOGGER.info(
                            "Avslutar föregående session (%s) för att starta Pris/Tid.",
                            self.active_control_mode_internal
                            if self.active_control_mode_internal
                            != CONTROL_MODE_PRICE_TIME
                            else "annan",
                        )
                        self._reset_session_data(
                            f"Avslutar {self.active_control_mode_internal if self.active_control_mode_internal != CONTROL_MODE_PRICE_TIME else 'annan'} för Pris/Tid"
                        )
                    _LOGGER.info("Startar ny Pris/Tid-session.")
                    self.session_start_time_utc = dt_util.utcnow()
                self._price_time_eligible_for_charging = True

            ### KORRIGERING STARTAR HÄR ###
            elif solar_charging_enabled and solar_schedule_active:
                # self.active_control_mode_internal sätts LÄNGRE NER, först efter att villkor är uppfyllda
                available_solar_surplus_w = (
                    current_solar_production_w
                    - (
                        current_house_power_w
                        if current_house_power_w is not None
                        else 0
                    )
                    - solar_buffer_w
                )

                if available_solar_surplus_w > 0:
                    calculated_solar_current_a = math.floor(
                        available_solar_surplus_w / (PHASES * VOLTAGE_PHASE_NEUTRAL)
                    )
                    if calculated_solar_current_a >= min_solar_charge_current_a:
                        # Tillräckligt med överskott för minsta ström
                        if (
                            not self._solar_session_active
                        ):  # Om ingen solsession är aktiv
                            if self._solar_surplus_start_time is None:
                                self._solar_surplus_start_time = current_time

                            if (
                                current_time - self._solar_surplus_start_time
                            ).total_seconds() >= SOLAR_SURPLUS_DELAY_SECONDS:
                                # Fördröjning passerad, starta solenergiladdning
                                self.active_control_mode_internal = (
                                    CONTROL_MODE_SOLAR_SURPLUS  # SÄTT LÄGE
                                )
                                self.should_charge_flag = True
                                self.target_charge_current_a = min(
                                    calculated_solar_current_a, charger_hw_max_amps
                                )
                                reason_for_action = f"Solenergiladdning aktiv (Överskott: {available_solar_surplus_w:.0f}W -> {self.target_charge_current_a:.1f}A)."
                                self._solar_session_active = True
                                if (
                                    self.session_start_time_utc is None
                                    or self._price_time_eligible_for_charging
                                ):
                                    if self.session_start_time_utc is not None:
                                        _LOGGER.info(
                                            "Avslutar föregående session (%s) för att starta Solenergi.",
                                            self.active_control_mode_internal
                                            if self.active_control_mode_internal
                                            != CONTROL_MODE_SOLAR_SURPLUS
                                            else "annan",
                                        )
                                        self._reset_session_data(
                                            f"Avslutar {self.active_control_mode_internal if self.active_control_mode_internal != CONTROL_MODE_SOLAR_SURPLUS else 'annan'} för Solenergi"
                                        )
                                    _LOGGER.info("Startar ny Solenergi-session.")
                                    self.session_start_time_utc = dt_util.utcnow()
                            else:  # Inom fördröjning
                                self.active_control_mode_internal = (
                                    CONTROL_MODE_MANUAL  # Styr inte aktivt än
                                )
                                self.should_charge_flag = False
                                reason_for_action = f"Väntar på att solöverskott ({available_solar_surplus_w:.0f}W -> {calculated_solar_current_a:.1f}A) ska stabiliseras."
                        else:  # Solenergisession redan aktiv, fortsätt
                            self.active_control_mode_internal = (
                                CONTROL_MODE_SOLAR_SURPLUS  # Behåll läge
                            )
                            self.should_charge_flag = True
                            self.target_charge_current_a = min(
                                calculated_solar_current_a, charger_hw_max_amps
                            )
                            reason_for_action = f"Solenergiladdning pågår (Överskott: {available_solar_surplus_w:.0f}W -> {self.target_charge_current_a:.1f}A)."
                    else:  # För lite överskott för minsta ström
                        self.active_control_mode_internal = (
                            CONTROL_MODE_MANUAL  # Inget aktivt sol-läge
                        )
                        self.should_charge_flag = False
                        reason_for_action = f"För lite solöverskott ({available_solar_surplus_w:.0f}W -> {calculated_solar_current_a:.1f}A < {min_solar_charge_current_a:.1f}A min)."
                        self._solar_surplus_start_time = None
                        self._solar_session_active = False
                        if (
                            self.session_start_time_utc is not None
                            and not self._price_time_eligible_for_charging
                        ):  # Om en sol-session var aktiv
                            self._reset_session_data(reason_for_action)
                else:  # Inget överskott alls
                    self.active_control_mode_internal = (
                        CONTROL_MODE_MANUAL  # Inget aktivt sol-läge
                    )
                    self.should_charge_flag = False
                    reason_for_action = f"Inget solöverskott tillgängligt ({available_solar_surplus_w:.0f}W)."
                    self._solar_surplus_start_time = None
                    self._solar_session_active = False
                    if (
                        self.session_start_time_utc is not None
                        and not self._price_time_eligible_for_charging
                    ):  # Om en sol-session var aktiv
                        self._reset_session_data(reason_for_action)

                self._price_time_eligible_for_charging = (
                    False  # Solenergi styr (eller försöker), inte P/T
                )
            ### KORRIGERING SLUTAR HÄR ###
            else:  # Inga smarta lägen aktiva
                self.active_control_mode_internal = CONTROL_MODE_MANUAL
                self.should_charge_flag = False
                reason_for_action = "Inga aktiva smarta laddningsvillkor uppfyllda."
                if self.session_start_time_utc is not None:
                    self._reset_session_data(reason_for_action)
                self._solar_surplus_start_time = None
                self._solar_session_active = False
                self._price_time_eligible_for_charging = False

        await self._control_charger(
            self.should_charge_flag, self.target_charge_current_a, reason_for_action
        )

        self.active_control_mode = (
            self.active_control_mode_internal or CONTROL_MODE_MANUAL
        )
        self.last_update_time = current_time

        _LOGGER.debug(
            "Uppdateringscykel klar. Styrningsläge: %s. Ska ladda: %s. Ström: %.1fA. Anledning: %s. Laddarstatus: %s",
            self.active_control_mode,
            self.should_charge_flag,
            self.target_charge_current_a,
            reason_for_action,
            charger_status,
        )

        return self._current_coordinator_data(reason_for_action)

    def _current_coordinator_data(self, reason: str) -> dict[str, Any]:
        return {
            "active_control_mode": self.active_control_mode
            if self.active_control_mode
            else CONTROL_MODE_MANUAL,
            "should_charge_reason": reason,
            "session_start_time_utc": self.session_start_time_utc.isoformat()
            if self.session_start_time_utc
            else None,
        }

    async def cleanup(self) -> None:
        _LOGGER.info("Rensar upp SmartEVChargingCoordinator...")
        self._remove_listeners()
