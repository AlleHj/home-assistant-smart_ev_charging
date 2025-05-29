# File version: 2025-05-29 0.1.34
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
    # EASEE_SERVICE_SET_CIRCUIT_MAX_CURRENT, # Oanvänd?
    # EASEE_SERVICE_ENABLE_CHARGER, # Oanvänd?
    # EASEE_SERVICE_DISABLE_CHARGER, # Oanvänd?
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
    # PRICE_CHECK_INTERVAL_MINUTES, # Oanvänd?
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
        # self.config sätts här och uppdateras i början av _async_update_data
        self.config = entry.data | entry.options

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(
                seconds=scan_interval_seconds
            ),  # Använd det validerade intervallet
        )
        _LOGGER.info(
            "SmartEVChargingCoordinator initialiserad med update_interval: %s sekunder.",
            self.update_interval,
        )

        self.charger_entity_id: str | None = (
            self._get_charger_entity_id()
        )  # Försöker hitta en relevant entitet
        self.listeners: list[CALLBACK_TYPE] = []

        # Initiera tillståndsvariabler
        self.active_control_mode: str = CONTROL_MODE_MANUAL
        self.should_charge_flag: bool = False
        self.target_charge_current_a: float = MIN_CHARGE_CURRENT_A
        self.active_control_mode_internal: str | None = None
        self.charger_main_switch_state: bool = True

        self.last_update_time: datetime = dt_util.utcnow()
        self.session_start_time_utc: datetime | None = None

        self._solar_surplus_start_time: datetime | None = None
        self._solar_session_active: bool = False

        self._price_time_eligible_for_charging: bool = False
        self._last_price_check_time: datetime | None = None  # Används inte aktivt f.n.

        self.smart_enable_switch_entity_id: str | None = None
        self.max_price_entity_id: str | None = None
        self.solar_enable_switch_entity_id: str | None = None
        self.solar_buffer_entity_id: str | None = None
        self.min_solar_charge_current_entity_id: str | None = None
        self._internal_entities_resolved: bool = False

        # _setup_listeners() anropas normalt efter att _resolve_internal_entities har körts framgångsrikt
        # och även vid _async_first_refresh. För att säkerställa att de sätts upp tidigt om allt är redo:
        # self.hass.create_task(self._resolve_and_setup_listeners_if_ready())
        # Alternativt, låt _async_first_refresh hantera det.

    async def _resolve_and_setup_listeners_if_ready(self):
        """Försöker lösa interna entiteter och sätter upp lyssnare om lyckat."""
        if await self._resolve_internal_entities():
            self._setup_listeners()

    def _get_charger_entity_id(self) -> str | None:
        """Hämtar entity_id för laddarenheten från Easee-integrationen."""
        device_id = self.config.get(CONF_CHARGER_DEVICE)
        if not device_id:
            _LOGGER.error("Ingen laddarenhet (CONF_CHARGER_DEVICE) är konfigurerad.")
            return None
        # Vi förlitar oss på att CONF_CHARGER_ENABLED_SWITCH_ID är korrekt satt för Easee-switch.
        # Tjänsteanrop använder oftast device_id.
        return self.config.get(CONF_CHARGER_ENABLED_SWITCH_ID)

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
                )  # Debug istället för Warning om det är normalt vid start
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
        """Sätter upp lyssnare för relevanta entitetsförändringar."""
        _LOGGER.debug("Sätter upp lyssnare...")
        self._remove_listeners()

        external_entities = [
            self.config.get(CONF_STATUS_SENSOR),
            self.config.get(CONF_PRICE_SENSOR),
            # self.config.get(CONF_SURCHARGE_HELPER), # Påslag påverkar inte logik, bara kostnadssensor (borttagen)
            self.config.get(CONF_TIME_SCHEDULE_ENTITY),
            self.config.get(CONF_HOUSE_POWER_SENSOR),
            self.config.get(CONF_SOLAR_PRODUCTION_SENSOR),
            self.config.get(CONF_SOLAR_SCHEDULE_ENTITY),
            self.config.get(CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR),
            # self.config.get(CONF_EV_POWER_SENSOR), # Används inte längre aktivt av koordinatorlogik
            self.config.get(CONF_CHARGER_ENABLED_SWITCH_ID),
            self.config.get(CONF_EV_SOC_SENSOR),
        ]

        # Internt skapade entiteter som koordinatorn behöver reagera på (om några)
        # Dessa läses av direkt i _async_update_data, så explicita lyssnare kanske inte behövs
        # om pollingintervallet är tillräckligt tätt eller om de inte ändras utanför HA:s state machine.
        # För switchar och nummer som sätts via UI, kommer en options_update_listener att trigga en reload + refresh.

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
            _LOGGER.info(
                "Inga externa entiteter konfigurerade för lyssning."
            )  # Info istället för Warning

    def _remove_listeners(self) -> None:
        """Tar bort alla aktiva lyssnare."""
        if self.listeners:
            _LOGGER.debug("Tar bort %s lyssnare.", len(self.listeners))
        while self.listeners:
            unsub = self.listeners.pop()
            unsub()

    @callback
    async def _handle_external_state_change(self, event: Event) -> None:
        """Hanterar tillståndsförändringar för externa lyssnade entiteter."""
        entity_id = event.data.get("entity_id")
        old_state_obj = event.data.get("old_state")
        new_state_obj = event.data.get("new_state")

        old_state_val = old_state_obj.state if old_state_obj else "None"
        new_state_val = new_state_obj.state if new_state_obj else "None"

        # Undvik onödig refresh om bara attribut ändrats (förutom för status_sensor)
        if old_state_val == new_state_val and entity_id != self.config.get(
            CONF_STATUS_SENSOR
        ):
            # _LOGGER.debug("Ignorerar tillståndsförändring för %s, state oförändrat: %s", entity_id, new_state_val)
            return

        _LOGGER.info(
            "Tillståndsförändring detekterad för %s: Gammalt=%s, Nytt=%s. Begär refresh.",
            entity_id,
            old_state_val,
            new_state_val,
        )
        await self.async_request_refresh()

    # ... (resten av metoderna: _get_number_value, _get_spot_price_in_kr, etc. är oförändrade från v0.1.33) ...
    # ... (_get_power_value, _reset_session_data, _control_charger är oförändrade från v0.1.33) ...
    # ... (_async_update_data, _current_coordinator_data, cleanup är oförändrade från v0.1.33) ...
    # Se till att hela filen kopieras från den versionen, med endast __init__ signaturen ändrad enligt ovan.
    # Nedan följer de metoderna för fullständighet, men de är logiskt oförändrade från den version du hade
    # förutom syntaxkorrigeringar och borttagning av energi/kostnadslogik.

    async def _get_number_value(
        self,
        entity_id_or_key: str,
        default_value: float | None = None,
        is_config_key: bool = True,
    ) -> float | None:
        entity_id = (
            self.config.get(entity_id_or_key) if is_config_key else entity_id_or_key
        )
        if not entity_id:
            if is_config_key:
                _LOGGER.debug(
                    "Konfigurationsnyckel %s för nummer är inte satt.", entity_id_or_key
                )
            return default_value
        state_obj = self.hass.states.get(str(entity_id))
        if state_obj is None or state_obj.state in [STATE_UNAVAILABLE, STATE_UNKNOWN]:
            _LOGGER.warning(
                "Entitet %s är otillgänglig eller har okänt tillstånd.", entity_id
            )
            return default_value
        try:
            return float(state_obj.state)
        except (ValueError, TypeError):
            _LOGGER.warning(
                "Kunde inte konvertera värde '%s' från %s till float.",
                state_obj.state,
                entity_id,
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
            currency = str(state_obj.attributes.get("currency", "")).upper()
            if "öre" in unit or "/100kwh" in unit:
                price /= 100
            if "mwh" in unit:
                price /= 1000
            if not (-5 < price < 20):  # Rimlighetskontroll
                _LOGGER.warning(
                    "Elpris '%s %s' från %s verkar orimligt.", price, unit, entity_id
                )
                return None
            if currency and currency != "SEK":  # Logga om det inte är SEK
                _LOGGER.warning(
                    "Elprissensor %s har valuta %s, men SEK förväntas.",
                    entity_id,
                    currency,
                )
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
        state_str = state_obj.state if state_obj else STATE_UNKNOWN
        if (
            state_str == STATE_UNKNOWN
            or state_str == STATE_UNAVAILABLE
            or state_obj is None
        ):
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
        if self.session_start_time_utc is not None:
            _LOGGER.debug(
                "Föregående session startade: %s", self.session_start_time_utc
            )
        self.session_start_time_utc = dt_util.utcnow()

    async def _control_charger(
        self, should_charge: bool, current_a: float, reason: str
    ) -> None:
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
        current_a = max(
            MIN_CHARGE_CURRENT_A, min(current_a, MAX_CHARGE_CURRENT_A_HW_DEFAULT)
        )
        _LOGGER.debug(
            "Charger Control: should_charge=%s, current_a=%.1fA, status=%s, reason='%s'",
            should_charge,
            current_a,
            charger_status,
            reason,
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
                    "Huvudströmbrytare %s är AV, men laddning begärs. Försöker slå PÅ.",
                    charger_master_switch_id,
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
                    if charger_status != EASEE_STATUS_CHARGING:
                        await self.hass.services.async_call(
                            "easee",
                            EASEE_SERVICE_RESUME_CHARGING,
                            {"charger_id": self.config.get(CONF_CHARGER_DEVICE)},
                            blocking=False,
                        )
                    if self.session_start_time_utc is None:
                        self._reset_session_data(f"Laddning startad ({reason})")
                elif charger_status == EASEE_STATUS_CHARGING:
                    _LOGGER.debug(
                        "Laddning pågår. Justerar dynamisk ström till %.1fA. Anledning: %s",
                        current_a,
                        reason,
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
                        "Laddning begärd, men laddarstatus är %s. Inväntar lämpligt tillstånd.",
                        charger_status,
                    )
            else:
                if (
                    charger_status == EASEE_STATUS_CHARGING
                    or charger_status == EASEE_STATUS_PAUSED
                ):
                    _LOGGER.info(
                        "Stoppar/pausar laddning. Anledning: %s. Status: %s",
                        reason,
                        charger_status,
                    )
                    await self.hass.services.async_call(
                        "easee",
                        EASEE_SERVICE_PAUSE_CHARGING,
                        {"charger_id": self.config.get(CONF_CHARGER_DEVICE)},
                        blocking=False,
                    )
                    if self.session_start_time_utc is not None:
                        self._reset_session_data(f"Laddning stoppad/pausad ({reason})")
                else:
                    _LOGGER.debug(
                        "Ingen laddning begärd och laddaren är inte aktivt laddande (status: %s).",
                        charger_status,
                    )
                    if (
                        self.session_start_time_utc is not None
                        and charger_status
                        not in [
                            EASEE_STATUS_AWAITING_START,
                            EASEE_STATUS_READY_TO_CHARGE,
                        ]
                    ):
                        self._reset_session_data(
                            f"Laddningssession avslutad (status: {charger_status})"
                        )
        except Exception as e:
            _LOGGER.error("Fel vid styrning av laddaren: %s", e, exc_info=True)

    async def _async_update_data(self) -> dict[str, Any]:
        _LOGGER.debug("Koordinatorn kör _async_update_data")

        self.config = self.entry.data | self.entry.options

        if not self._internal_entities_resolved:
            await self._resolve_internal_entities()
            if not self._internal_entities_resolved:
                _LOGGER.warning(
                    "Interna entiteter kunde inte lösas, avbryter uppdateringscykeln."
                )
                return (
                    self.data
                    if self.data
                    else self._current_coordinator_data("Väntar på interna entiteter.")
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

        smart_enable_switch_state_obj = (
            self.hass.states.get(self.smart_enable_switch_entity_id)
            if self.smart_enable_switch_entity_id
            else None
        )
        smart_charging_enabled = (
            smart_enable_switch_state_obj.state == STATE_ON
            if smart_enable_switch_state_obj
            else False
        )

        solar_enable_switch_state_obj = (
            self.hass.states.get(self.solar_enable_switch_entity_id)
            if self.solar_enable_switch_entity_id
            else None
        )
        solar_charging_enabled = (
            solar_enable_switch_state_obj.state == STATE_ON
            if solar_enable_switch_state_obj
            else False
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

        time_schedule_id = self.config.get(CONF_TIME_SCHEDULE_ENTITY)
        time_schedule_active = False
        if time_schedule_id:
            time_schedule_state_obj = self.hass.states.get(str(time_schedule_id))
            if time_schedule_state_obj:
                time_schedule_active = time_schedule_state_obj.state == STATE_ON

        solar_schedule_id = self.config.get(CONF_SOLAR_SCHEDULE_ENTITY)
        solar_schedule_active = False
        if solar_schedule_id:
            solar_schedule_state_obj = self.hass.states.get(str(solar_schedule_id))
            if solar_schedule_state_obj:
                solar_schedule_active = solar_schedule_state_obj.state == STATE_ON

        current_house_power_w = await self._get_power_value(CONF_HOUSE_POWER_SENSOR)
        current_solar_production_w = (
            await self._get_power_value(CONF_SOLAR_PRODUCTION_SENSOR) or 0.0
        )

        charger_hw_max_amps_sensor_id = self.config.get(
            CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR
        )
        charger_hw_max_amps_obj = (
            self.hass.states.get(str(charger_hw_max_amps_sensor_id))
            if charger_hw_max_amps_sensor_id
            else None
        )
        charger_hw_max_amps = MAX_CHARGE_CURRENT_A_HW_DEFAULT
        if charger_hw_max_amps_obj and charger_hw_max_amps_obj.state not in [
            STATE_UNKNOWN,
            STATE_UNAVAILABLE,
        ]:
            try:
                charger_hw_max_amps = float(charger_hw_max_amps_obj.state)
            except (ValueError, TypeError):
                _LOGGER.warning(
                    "Kunde inte tolka värde för charger_hw_max_amps från %s",
                    charger_hw_max_amps_sensor_id,
                )

        current_soc_percent = await self._get_number_value(
            CONF_EV_SOC_SENSOR, is_config_key=True
        )
        target_soc_limit_val = self.config.get(CONF_TARGET_SOC_LIMIT)
        target_soc_limit = (
            float(target_soc_limit_val) if target_soc_limit_val is not None else None
        )

        min_solar_charge_current_a = (
            await self._get_number_value(
                self.min_solar_charge_current_entity_id,
                MIN_CHARGE_CURRENT_A,
                is_config_key=False,
            )
            or MIN_CHARGE_CURRENT_A
        )
        solar_buffer_w = (
            await self._get_number_value(
                self.solar_buffer_entity_id, POWER_MARGIN_W, is_config_key=False
            )
            or POWER_MARGIN_W
        )

        self.should_charge_flag = False
        reason_for_action = "Ingen styrning aktiv."
        self.active_control_mode_internal = CONTROL_MODE_MANUAL
        self.target_charge_current_a = MIN_CHARGE_CURRENT_A

        if not self.charger_main_switch_state:
            self.should_charge_flag = False
            reason_for_action = "Huvudströmbrytare för laddbox är AV."
            if self.session_start_time_utc is not None:
                self._reset_session_data(reason_for_action)

        elif (
            current_soc_percent is not None
            and target_soc_limit is not None
            and current_soc_percent >= target_soc_limit
        ):
            self.should_charge_flag = False
            reason_for_action = (
                f"SoC ({current_soc_percent}%) har nått målet ({target_soc_limit}%)."
            )
            if self.session_start_time_utc is not None:
                self._reset_session_data(reason_for_action)
            if charger_status == EASEE_STATUS_CHARGING:
                await self._control_charger(
                    False, MIN_CHARGE_CURRENT_A, reason_for_action
                )

        elif solar_charging_enabled and solar_schedule_active:
            self.active_control_mode_internal = CONTROL_MODE_SOLAR_SURPLUS
            available_solar_surplus_w = (
                current_solar_production_w
                - (current_house_power_w if current_house_power_w is not None else 0)
                - solar_buffer_w
            )
            if available_solar_surplus_w > 0:
                calculated_solar_current_a = math.floor(available_solar_surplus_w / 230)
                if calculated_solar_current_a >= min_solar_charge_current_a:
                    if not self._solar_session_active:
                        if self._solar_surplus_start_time is None:
                            self._solar_surplus_start_time = current_time
                            _LOGGER.debug(
                                "Solöverskott detekterat (%.0fW -> %.1fA), startar fördröjningstimer.",
                                available_solar_surplus_w,
                                calculated_solar_current_a,
                            )
                        if (
                            current_time - self._solar_surplus_start_time
                        ).total_seconds() >= SOLAR_SURPLUS_DELAY_SECONDS:
                            self.should_charge_flag = True
                            self.target_charge_current_a = min(
                                calculated_solar_current_a, charger_hw_max_amps
                            )
                            reason_for_action = f"Solenergiladdning aktiv (Överskott: {available_solar_surplus_w:.0f}W -> {self.target_charge_current_a:.1f}A)."
                            self._solar_session_active = True
                            if self.session_start_time_utc is None:
                                self._reset_session_data(reason_for_action)
                        else:
                            reason_for_action = (
                                "Väntar på att solöverskott ska stabiliseras."
                            )
                            self.should_charge_flag = False
                    else:
                        self.should_charge_flag = True
                        self.target_charge_current_a = min(
                            calculated_solar_current_a, charger_hw_max_amps
                        )
                        reason_for_action = f"Solenergiladdning pågår (Överskott: {available_solar_surplus_w:.0f}W -> {self.target_charge_current_a:.1f}A)."
                else:
                    reason_for_action = f"För lite solöverskott ({available_solar_surplus_w:.0f}W -> {calculated_solar_current_a:.1f}A < {min_solar_charge_current_a:.1f}A min)."
                    self.should_charge_flag = False
                    self._solar_surplus_start_time = None
                    if self._solar_session_active:
                        self._reset_session_data(reason_for_action)
                    self._solar_session_active = False
            else:
                reason_for_action = f"Inget solöverskott tillgängligt ({available_solar_surplus_w:.0f}W)."
                self.should_charge_flag = False
                self._solar_surplus_start_time = None
                if self._solar_session_active:
                    self._reset_session_data(reason_for_action)
                self._solar_session_active = False

        elif smart_charging_enabled:
            self.active_control_mode_internal = CONTROL_MODE_PRICE_TIME
            self._solar_surplus_start_time = None
            self._solar_session_active = False
            price_ok = (
                total_price_kr is not None
                and max_accepted_price_kr is not None
                and total_price_kr <= max_accepted_price_kr
            )
            time_slot_active = time_schedule_active
            if price_ok and time_slot_active:
                self.should_charge_flag = True
                self.target_charge_current_a = charger_hw_max_amps
                reason_for_action = f"Pris/Tid-laddning aktiv (Pris: {total_price_kr:.2f} <= {max_accepted_price_kr:.2f} kr, Tidsschema PÅ)."
                if self.session_start_time_utc is None:
                    self._reset_session_data(reason_for_action)
                self._price_time_eligible_for_charging = True
            else:
                self.should_charge_flag = False
                if not price_ok and total_price_kr is not None:
                    reason_for_action = f"Pris för högt ({total_price_kr:.2f} > {max_accepted_price_kr:.2f} kr)."
                elif not time_slot_active:
                    reason_for_action = "Tidsschema för Pris/Tid är AV."
                else:
                    reason_for_action = "Pris/Tid-villkor ej uppfyllda."
                if self._price_time_eligible_for_charging:
                    self._reset_session_data(reason_for_action)
                self._price_time_eligible_for_charging = False
        else:
            self.active_control_mode_internal = CONTROL_MODE_MANUAL
            reason_for_action = "Smart styrning är avaktiverad."
            self.should_charge_flag = False
            self._solar_surplus_start_time = None
            if self.session_start_time_utc is not None:
                self._reset_session_data(reason_for_action)
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
            "Uppdateringscykel klar. Styrningsläge: %s. Ska ladda: %s. Ström: %.1fA. Anledning: %s. Status: %s",
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
            "should_charge_flag_internal": self.should_charge_flag,
            "target_charge_current_a_internal": self.target_charge_current_a,
        }

    async def cleanup(self) -> None:
        _LOGGER.info("Rensar upp SmartEVChargingCoordinator...")
        self._remove_listeners()
