# File version: 2025-05-31 0.1.40 (Ny version efter korrigering)!
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

    # Definierar en asynkron metod (coroutine) som heter _control_charger.
    # Denna metod är en del av en klass (indikerat av 'self').
    # Den tar emot tre argument utöver 'self':
    #   should_charge: En boolean som indikerar om laddning ska ske eller inte.
    #   current_a: En float som representerar önskad laddström i Ampere.
    #   reason: En sträng som beskriver anledningen till det nuvarande laddningsbeslutet.
    # Metoden returnerar ingenting (None).
    async def _control_charger(
        self, should_charge: bool, current_a: float, reason: str
    ) -> None:
        # Hämtar entity_id för huvudströmbrytaren från integrationens konfiguration.
        # CONF_CHARGER_ENABLED_SWITCH_ID är en konstant som innehåller nyckeln för detta värde.
        charger_master_switch_id = self.config.get(CONF_CHARGER_ENABLED_SWITCH_ID)
        # Hämtar entity_id för laddarens statussensor från konfigurationen.
        status_sensor_id = self.config.get(CONF_STATUS_SENSOR)
        # Hämtar det aktuella tillståndsobjektet för statussensorn från Home Assistant.
        # Om status_sensor_id inte är satt (None), blir charger_status_state också None.
        charger_status_state = (
            self.hass.states.get(str(status_sensor_id)) if status_sensor_id else None
        )
        # Extraherar det faktiska tillståndet (som en sträng) från tillståndsobjektet.
        # Konverterar till gemener för enklare jämförelser.
        # Om inget giltigt tillstånd finns, sätts charger_status till STATE_UNKNOWN (en konstant, oftast "unknown").
        charger_status = (
            charger_status_state.state.lower()
            if charger_status_state and isinstance(charger_status_state.state, str)
            else STATE_UNKNOWN
        )

        # Hämtar entity_id för sensorn som anger laddarens maximala hårdvarubegränsning för ström.
        charger_hw_max_amps_entity_id = self.config.get(
            CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR
        )
        # Sätter ett standardvärde för maximal hårdvaruström.
        # MAX_CHARGE_CURRENT_A_HW_DEFAULT är en konstant, t.ex. 16A.
        _charger_hw_max_amps = MAX_CHARGE_CURRENT_A_HW_DEFAULT
        # Om en sensor för hårdvarumaximum är konfigurerad:
        if charger_hw_max_amps_entity_id:
            # Anropar en hjälpmetod (_get_number_value) för att hämta det numeriska värdet från sensorn.
            # is_config_key=False indikerar att charger_hw_max_amps_entity_id redan är ett entity_id.
            val_from_sensor = await self._get_number_value(
                charger_hw_max_amps_entity_id,
                default_value=MAX_CHARGE_CURRENT_A_HW_DEFAULT,  # Fallback-värde om sensorn inte ger ett giltigt nummer.
                is_config_key=False,
            )
            # Om ett giltigt värde hämtades från sensorn:
            if val_from_sensor is not None:
                # Uppdatera _charger_hw_max_amps med sensorvärdet.
                _charger_hw_max_amps = val_from_sensor

        # Säkerställer att den önskade laddströmmen (current_a) är inom tillåtna gränser:
        # Inte lägre än MIN_CHARGE_CURRENT_A (en konstant, t.ex. 6A).
        # Inte högre än den faktiska hårdvarubegränsningen _charger_hw_max_amps.
        # Inte högre än den current_a som skickades in (som kan ha beräknats från t.ex. solöverskott).
        current_a = max(MIN_CHARGE_CURRENT_A, min(current_a, _charger_hw_max_amps))

        # Hämtar entity_id för sensorn som rapporterar den *nuvarande* dynamiska strömgränsen på laddaren.
        current_dynamic_limit_entity_id = self.config.get(
            CONF_CHARGER_DYNAMIC_CURRENT_SENSOR
        )
        # Initierar variabeln för nuvarande dynamisk gräns till None.
        current_dynamic_limit = None
        # Om en sensor för dynamisk gräns är konfigurerad:
        if current_dynamic_limit_entity_id:
            # Hämta dess numeriska värde.
            current_dynamic_limit = await self._get_number_value(
                current_dynamic_limit_entity_id, is_config_key=False
            )

        # Loggar ett debug-meddelande med aktuella parametrar och tillstånd för styrningen.
        # Detta är användbart för felsökning för att se vilka beslut som fattas.
        _LOGGER.debug(
            "Charger Control: should_charge=%s, current_a=%.1fA (begränsad av %.1fA HW), status=%s, reason='%s', current_dyn_limit=%.1fA",
            should_charge,  # Ska laddning ske?
            current_a,  # Målström efter begränsningar.
            _charger_hw_max_amps,  # Faktisk HW-maxström.
            charger_status,  # Laddarens nuvarande status.
            reason,  # Anledningen till beslutet.
            current_dynamic_limit
            if current_dynamic_limit is not None
            else -1.0,  # Nuvarande dynamisk gräns, eller -1.0 om okänd.
        )

        # Kontrollerar om en huvudströmbrytare för laddboxen är konfigurerad.
        if not charger_master_switch_id:
            # Om inte, logga ett fel och avbryt funktionen eftersom vi inte kan garantera att laddaren kan styras.
            _LOGGER.error("Huvudströmbrytare för laddboxen är inte konfigurerad.")
            return  # Avsluta metoden här.
        # Startar ett try-block för felhantering vid tjänsteanrop etc.
        try:
            # Hämtar tillståndsobjektet för huvudströmbrytaren.
            current_master_switch_state = self.hass.states.get(charger_master_switch_id)
            # Kontrollerar om huvudströmbrytaren existerar, är AV, och om laddning begärs (should_charge är True).
            if (
                current_master_switch_state  # Finns strömbrytaren?
                and current_master_switch_state.state == STATE_OFF  # Är den AV?
                and should_charge  # Begärs laddning?
            ):
                # Om ja, logga att vi försöker slå PÅ den.
                _LOGGER.info(
                    "Huvudströmbrytare %s är AV, men laddning begärs (%s). Försöker slå PÅ.",
                    charger_master_switch_id,  # Vilken strömbrytare.
                    reason,  # Varför laddning begärs.
                )
                # Anropar Home Assistant-tjänsten för att slå PÅ en entitet.
                await self.hass.services.async_call(
                    "homeassistant",  # Domänen för tjänsten (standard HA-tjänster).
                    SERVICE_TURN_ON,  # Tjänsten som ska anropas (konstant för "turn_on").
                    {
                        ATTR_ENTITY_ID: charger_master_switch_id
                    },  # Data: vilken entitet som ska slås på.
                    blocking=False,  # blocking=False innebär att vi inte väntar på att tjänsten ska slutföras.
                )
                # Pausar exekveringen i 2 sekunder för att ge strömbrytaren tid att slå på och laddaren att initialiseras.
                await asyncio.sleep(2)
                # Efter pausen, läs om laddarens status eftersom den kan ha ändrats.
                charger_status_state = (
                    self.hass.states.get(str(status_sensor_id))
                    if status_sensor_id
                    else None
                )
                # Tolka den nya statusen.
                charger_status = (
                    charger_status_state.state.lower()
                    if charger_status_state
                    and isinstance(charger_status_state.state, str)
                    else STATE_UNKNOWN
                )

            # Huvudlogik: Om laddning ska ske (should_charge är True).
            if should_charge:
                # Definierar en inre asynkron funktion för att sätta strömmen om det behövs.
                # Detta görs för att undvika kodupprepning.
                async def set_current_if_needed_locally():
                    # Kontrollerar om den nuvarande dynamiska gränsen är okänd (None)
                    # ELLER om den avrundade nuvarande dynamiska gränsen skiljer sig från den avrundade målströmmen.
                    # Jämför med en decimals precision.
                    if current_dynamic_limit is None or round(
                        current_dynamic_limit, 1
                    ) != round(current_a, 1):
                        # Om strömmen behöver ändras, logga detta.
                        _LOGGER.debug(
                            "Målström (%.1fA) skiljer sig från nuvarande dynamiska gräns (%.1fA) eller nuvarande är okänd. Skickar uppdatering.",
                            current_a,  # Målström.
                            current_dynamic_limit
                            if current_dynamic_limit is not None
                            else -1.0,  # Nuvarande dynamisk gräns, eller -1.0 om okänd.
                        )
                        # Denna del är utkommenterad, representerar ett tidigare sätt att anropa tjänsten.
                        # await self.hass.services.async_call(
                        #     "easee",
                        #     EASEE_SERVICE_SET_DYNAMIC_CURRENT, # Konstant för tjänstenamnet.
                        #     {
                        #         "device_id": self.config.get(CONF_CHARGER_DEVICE),
                        #         "circuit_id": 1, # Easee-specifik parameter.
                        #         "currentP1": current_a, # Ström för fas 1.
                        #         "currentP2": current_a, # Ström för fas 2.
                        #         "currentP3": current_a, # Ström för fas 3.
                        #     },
                        #     blocking=False,
                        # )
                        # Anropar Easee-tjänsten för att sätta den dynamiska laddningsgränsen.
                        # Detta är den aktiva koden för att sätta ström, baserat på användarens tidigare input.
                        await self.hass.services.async_call(
                            "easee",  # Domänen för Easee-integrationen.
                            "set_charger_dynamic_limit",  # Specifikt tjänstenamn.
                            {
                                "device_id": self.config.get(
                                    CONF_CHARGER_DEVICE
                                ),  # Enhets-ID för laddaren.
                                "current": current_a,  # Den nya strömgränsen.
                                "time_to_live": 0,  # Parameter för hur länge gränsen ska gälla (0 = tills vidare).
                            },
                            blocking=False,  # Kör anropet asynkront utan att vänta på svar.
                        )
                    # Om målströmmen redan är satt:
                    else:
                        # Logga att ingen uppdatering av strömmen behövs.
                        _LOGGER.debug(
                            "Målström (%.1fA) är redan satt enligt dynamisk gränssensor. Ingen uppdatering behövs.",
                            current_a,
                        )

                # Kontrollerar om laddarens status indikerar att den är redo att starta/återuppta laddning.
                # EASEE_STATUS_READY_TO_CHARGE etc. är listor eller strängar med kända statusvärden.
                if (
                    charger_status
                    in EASEE_STATUS_READY_TO_CHARGE  # Är laddaren redo? (kan vara en lista av statusar)
                    or charger_status
                    == EASEE_STATUS_AWAITING_START  # Väntar den på startsignal?
                    or charger_status == EASEE_STATUS_PAUSED  # Är den pausad?
                    or charger_status
                    == EASEE_STATUS_COMPLETED  # Är den precis klar med en session?
                ):
                    # Om ja, logga att vi startar/återupptar eller justerar ström.
                    _LOGGER.info(
                        "Startar/återupptar laddning eller justerar ström till %.1fA. Anledning: %s. Status: %s",
                        current_a,  # Målström.
                        reason,  # Anledning till åtgärden.
                        charger_status,  # Nuvarande status.
                    )
                    # Anropa den inre funktionen för att sätta strömmen om det behövs.
                    await set_current_if_needed_locally()
                    # Om laddaren inte redan aktivt laddar:
                    if charger_status != EASEE_STATUS_CHARGING:
                        # Denna del är utkommenterad, representerar ett tidigare sätt att anropa tjänsten.
                        # await self.hass.services.async_call(
                        #     "easee",
                        #     EASEE_SERVICE_RESUME_CHARGING, # Konstant för resume-tjänsten.
                        #     {"charger_id": self.config.get(CONF_CHARGER_DEVICE)}, # Äldre parameter för laddar-ID.
                        #     blocking=False,
                        # )
                        # Anropar Easee-tjänsten för att starta/återuppta laddningen.
                        # Detta är den aktiva koden, baserat på användarens tidigare input.
                        await self.hass.services.async_call(
                            "easee",  # Domänen för Easee.
                            "action_command",  # Tjänstenamn för generiska kommandon.
                            {
                                "device_id": self.config.get(
                                    CONF_CHARGER_DEVICE
                                ),  # Enhets-ID.
                                "action_command": "start",  # Kommando för att starta.
                            },
                            blocking=False,  # Kör asynkront.
                        )
                    # Hanterar logik för att markera starten på en ny laddningssession.
                    if (
                        self.session_start_time_utc is None
                    ):  # Om ingen sessionstid är satt (dvs. ny session).
                        # Logga att en ny session startas.
                        _LOGGER.info(
                            "Startar ny laddningssession. Anledning: %s",
                            f"Laddning startad/återupptagen ({reason})",
                        )
                        # Sätt starttiden för sessionen till nuvarande tid (UTC).
                        self.session_start_time_utc = dt_util.utcnow()
                    # Kommentar som förklarar logik som inte längre är aktiv eller hanteras på annat ställe.
                    # Om en session redan pågick (t.ex. P/T och nu byter till Sol eller vice versa),
                    # och det är en *annan* anledning än tidigare, kan man överväga att logga byte av anledning.
                    # Men _reset_session_data anropas redan från _async_update_data vid byte av smart läge.

                # Om laddaren redan aktivt laddar (EASEE_STATUS_CHARGING):
                elif charger_status == EASEE_STATUS_CHARGING:
                    # Logga att vi justerar strömmen om det behövs.
                    _LOGGER.debug(
                        "Laddning pågår. Justerar dynamisk ström vid behov till %.1fA. Anledning: %s",
                        current_a,
                        reason,
                    )
                    # Anropa den inre funktionen för att eventuellt justera strömmen.
                    await set_current_if_needed_locally()
                # Om laddaren är frånkopplad eller offline, men laddning begärs:
                elif (
                    charger_status in EASEE_STATUS_DISCONNECTED  # Är bilen frånkopplad?
                    or charger_status == EASEE_STATUS_OFFLINE  # Är laddaren offline?
                ):
                    # Logga en varning om detta.
                    _LOGGER.warning(
                        "Laddning begärd, men laddaren är frånkopplad/offline (status: %s).",
                        charger_status,
                    )
                    # Om en session var aktiv, återställ sessionsdata.
                    if self.session_start_time_utc is not None:
                        self._reset_session_data(
                            f"Laddare frånkopplad/offline ({charger_status})"
                        )
                # Annat fall: Laddning begärs men statusen är inte optimal för start (t.ex. error).
                else:
                    _LOGGER.info(
                        "Laddning begärd (Anledning: %s), men laddarstatus är %s. Inväntar lämpligt tillstånd.",
                        reason,
                        charger_status,
                    )
            # Om laddning INTE ska ske (should_charge är False):
            else:
                # Om laddaren just nu laddar, eller om den är pausad och det inte är manuellt läge:
                # (Logiken här är att om den är pausad och vi är i manuellt läge, ska vi inte skicka ett nytt pauskommando).
                if charger_status == EASEE_STATUS_CHARGING or (
                    charger_status == EASEE_STATUS_PAUSED
                    and self.active_control_mode_internal != CONTROL_MODE_MANUAL
                ):
                    # Logga att vi stoppar/pausar laddningen.
                    _LOGGER.info(
                        "Stoppar/pausar laddning. Anledning: %s. Status: %s",
                        reason,
                        charger_status,
                    )
                    # Denna del är utkommenterad, representerar ett tidigare sätt att anropa tjänsten.
                    # await self.hass.services.async_call(
                    #     "easee",
                    #     EASEE_SERVICE_PAUSE_CHARGING, # Konstant för paus-tjänsten.
                    #     {"charger_id": self.config.get(CONF_CHARGER_DEVICE)},
                    #     blocking=False,
                    # )
                    # Anropar Easee-tjänsten för att pausa laddningen.
                    # Detta är den aktiva koden, baserat på användarens tidigare input.
                    await self.hass.services.async_call(
                        "easee",  # Domänen för Easee.
                        "action_command",  # Tjänstenamn för generiska kommandon.
                        {
                            "device_id": self.config.get(
                                CONF_CHARGER_DEVICE
                            ),  # Enhets-ID.
                            "action_command": "pause",  # Kommando för att pausa.
                        },
                        blocking=False,  # Kör asynkront.
                    )
                    # Om en session var aktiv, återställ sessionsdata.
                    if self.session_start_time_utc is not None:
                        self._reset_session_data(f"Laddning stoppad/pausad ({reason})")
                # Om ingen laddning begärs och laddaren inte aktivt laddar:
                else:
                    # Logga nuvarande status.
                    _LOGGER.debug(
                        "Ingen laddning begärd och laddaren är inte aktivt laddande (status: %s). Anledning till ingen laddning: %s",
                        charger_status,
                        reason,
                    )
                    # Om en session var aktiv men laddaren nu har en oväntad status (inte redo, väntar, pausad),
                    # återställ sessionen för att undvika felaktig sessionsdata.
                    if (
                        self.session_start_time_utc is not None  # Fanns en session?
                        and charger_status  # Finns en status?
                        not in [  # Och statusen är INTE en av dessa "vilande men OK" statusar?
                            EASEE_STATUS_AWAITING_START,
                            EASEE_STATUS_READY_TO_CHARGE,
                            EASEE_STATUS_PAUSED,
                        ]
                    ):
                        self._reset_session_data(
                            f"Laddningssession avslutad (status: {charger_status}, Anledning: {reason})"
                        )
        # Fångar upp eventuella oväntade fel under styrningen av laddaren.
        except Exception as e:
            _LOGGER.error(
                "Fel vid styrning av laddaren: %s", e, exc_info=True
            )  # Logga felet med traceback.

    # Definierar en asynkron metod (coroutine) med namnet _async_update_data.
    # Denna metod är en del av DataUpdateCoordinator och anropas periodiskt för att hämta och bearbeta data.
    # Den förväntas returnera en dictionary med data som kan användas av sensorer/entiteter.
    async def _async_update_data(self) -> dict[str, Any]:
        # Loggar ett debug-meddelande som indikerar att uppdateringscykeln har startat.
        _LOGGER.debug("Koordinatorn kör _async_update_data")
        # Uppdaterar koordinatorns interna konfiguration (self.config) genom att slå samman
        # den ursprungliga konfigurationen (self.entry.data) med eventuella användarändrade alternativ (self.entry.options).
        # Options har företräde om samma nyckel finns i båda.
        self.config = self.entry.data | self.entry.options

        # Kontrollerar om de interna entiteterna (switchar, nummer etc. som skapas av denna integration) har blivit lösta (deras entity_id har hittats).
        if not self._internal_entities_resolved:
            # Om de inte är lösta, försök att lösa dem nu genom att anropa _resolve_internal_entities.
            if not await self._resolve_internal_entities():
                # Om de fortfarande inte kunde lösas, logga en varning.
                _LOGGER.warning(
                    "Interna entiteter kunde inte lösas, avbryter uppdateringscykeln."
                )
                # Avbryt uppdateringscykeln och returnera befintlig data (om någon finns),
                # annars returnera ett standardobjekt som indikerar manuellt läge och väntan.
                # Detta förhindrar fel om integrationen inte är fullständigt initialiserad.
                return (
                    self.data  # Returnera tidigare data om den finns.
                    if self.data  # Kontrollera om self.data har ett värde.
                    else {  # Annars, returnera ett standardobjekt.
                        "active_control_mode": CONTROL_MODE_MANUAL,  # Sätt aktivt läge till manuellt.
                        "should_charge_reason": "Väntar på interna entiteter.",  # Ange anledning.
                    }
                )

        # Hämtar den nuvarande tiden i UTC-format. Används för tidsbaserade jämförelser.
        current_time = dt_util.utcnow()
        # Hämtar entity_id för laddarens statussensor från konfigurationen.
        charger_status_sensor_id = self.config.get(CONF_STATUS_SENSOR)
        # Hämtar tillståndsobjektet för statussensorn från Home Assistant.
        # Om ingen statussensor är konfigurerad (charger_status_sensor_id är None), blir charger_status_state None.
        charger_status_state = (
            self.hass.states.get(
                str(charger_status_sensor_id)
            )  # Hämta tillstånd om ID finns.
            if charger_status_sensor_id  # Kontrollera om ID är satt.
            else None  # Annars, sätt till None.
        )
        # Extraherar det faktiska statusvärdet (som en sträng) från tillståndsobjektet.
        # Konverterar till gemener för konsekventa jämförelser.
        # Om inget giltigt tillstånd finns (t.ex. sensorn är otillgänglig), sätts status till STATE_UNKNOWN.
        charger_status = (
            charger_status_state.state.lower()  # Hämta state och konvertera till gemener.
            if charger_status_state
            and isinstance(
                charger_status_state.state, str
            )  # Kontrollera att state-objekt och dess state-attribut finns och är en sträng.
            else STATE_UNKNOWN  # Annars, använd STATE_UNKNOWN (oftast "unknown").
        )

        # Hämtar entity_id för laddarens huvudströmbrytare från konfigurationen.
        charger_main_switch_id = self.config.get(CONF_CHARGER_ENABLED_SWITCH_ID)
        # Hämtar tillståndsobjektet för huvudströmbrytaren.
        main_switch_state_obj = (
            self.hass.states.get(
                str(charger_main_switch_id)
            )  # Hämta tillstånd om ID finns.
            if charger_main_switch_id  # Kontrollera om ID är satt.
            else None  # Annars, sätt till None.
        )
        # Bestämmer om huvudströmbrytaren är PÅ.
        # Om inget strömbrytarobjekt finns (dvs. ingen är konfigurerad), antas den vara PÅ (True) för att inte blockera logiken i onödan.
        self.charger_main_switch_state = (
            main_switch_state_obj.state == STATE_ON
            if main_switch_state_obj
            else True  # Är switchen PÅ? True om ej konfad.
        )

        # Kontrollerar om switchen för smart laddning (Pris/Tid) är PÅ.
        # self.smart_enable_switch_entity_id är ID:t för den switch som denna integration skapar.
        smart_charging_enabled = self.hass.states.is_state(
            self.smart_enable_switch_entity_id,
            STATE_ON,  # Jämför tillståndet med STATE_ON ("on").
        )
        # Kontrollerar om switchen för solenergiladdning är PÅ.
        # self.solar_enable_switch_entity_id är ID:t för den switch som denna integration skapar.
        solar_charging_enabled = self.hass.states.is_state(
            self.solar_enable_switch_entity_id,
            STATE_ON,  # Jämför tillståndet med STATE_ON.
        )

        # Hämtar det aktuella spotpriset i kr/kWh via en hjälpmetod.
        current_price_kr = await self._get_spot_price_in_kr()
        # Hämtar det maximalt accepterade priset från nummer-entiteten som skapats av denna integration.
        # Om värdet inte kan hämtas, används 999.0 som ett högt defaultvärde (laddning tillåts prismässigt).
        # is_config_key=False betyder att self.max_price_entity_id redan är ett fullständigt entity_id.
        max_accepted_price_kr = (
            await self._get_number_value(
                self.max_price_entity_id,
                999.0,
                is_config_key=False,  # Standardvärde om inget kan läsas.
            )
            or 999.0  # Säkerställer att det inte blir None om _get_number_value returnerar None (t.ex. om entiteten är ny).
        )

        # Hämtar entity_id för tidsschemat (för Pris/Tid-laddning) från konfigurationen.
        time_schedule_entity_id = self.config.get(CONF_TIME_SCHEDULE_ENTITY)
        # Kontrollerar om tidsschemat är aktivt (PÅ).
        # Om inget tidsschema är konfigurerat, antas det vara aktivt (True).
        time_schedule_active = (
            self.hass.states.is_state(
                str(time_schedule_entity_id), STATE_ON
            )  # Är schemat PÅ?
            if time_schedule_entity_id  # Om ett schema-ID finns.
            else True  # Annars, antag att det är aktivt.
        )

        # Hämtar entity_id för solenergi-tidsschemat från konfigurationen.
        solar_schedule_entity_id = self.config.get(CONF_SOLAR_SCHEDULE_ENTITY)
        # Kontrollerar om solenergi-tidsschemat är aktivt (PÅ).
        # Om inget schema är konfigurerat, antas det vara aktivt (True).
        solar_schedule_active = (
            self.hass.states.is_state(
                str(solar_schedule_entity_id), STATE_ON
            )  # Är schemat PÅ?
            if solar_schedule_entity_id  # Om ett schema-ID finns.
            else True  # Annars, antag att det är aktivt.
        )

        # Hämtar aktuell husförbrukning i Watt via en hjälpmetod.
        current_house_power_w = await self._get_power_value(CONF_HOUSE_POWER_SENSOR)
        # Hämtar aktuell solproduktion i Watt. Om sensorn inte finns eller är otillgänglig, använd 0.0 W.
        current_solar_production_w = (
            await self._get_power_value(CONF_SOLAR_PRODUCTION_SENSOR)
            or 0.0  # Default 0.0 om inget värde.
        )

        # Hämtar entity_id för sensorn som anger laddarens maximala hårdvarubegränsning för ström.
        charger_hw_max_amps_entity_id = self.config.get(
            CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR
        )
        # Sätter ett standardvärde för maximal hårdvaruström.
        charger_hw_max_amps = MAX_CHARGE_CURRENT_A_HW_DEFAULT
        # Om en sensor för hårdvarumaximum är konfigurerad:
        if charger_hw_max_amps_entity_id:
            # Hämta värdet från sensorn.
            val_from_sensor = await self._get_number_value(
                charger_hw_max_amps_entity_id,
                default_value=MAX_CHARGE_CURRENT_A_HW_DEFAULT,  # Fallback-värde.
                is_config_key=False,  # Detta är redan ett entity_id.
            )
            # Om ett giltigt värde hämtades:
            if val_from_sensor is not None:
                # Uppdatera variabeln med sensorvärdet.
                charger_hw_max_amps = val_from_sensor

        # Hämtar entity_id för sensorn som rapporterar bilens laddningsnivå (State of Charge, SoC).
        ev_soc_sensor_entity_id = self.config.get(CONF_EV_SOC_SENSOR)
        # Initierar variabeln för aktuell SoC till None.
        current_soc_percent = None
        # Om en SoC-sensor är konfigurerad:
        if ev_soc_sensor_entity_id:
            # Hämta dess numeriska värde.
            current_soc_percent = await self._get_number_value(
                ev_soc_sensor_entity_id, is_config_key=False
            )

        # Hämtar den konfigurerade övre SoC-gränsen från konfigurationen.
        target_soc_limit_config = self.config.get(CONF_TARGET_SOC_LIMIT)
        # Konverterar SoC-gränsen till float om den är satt, annars None.
        target_soc_limit = (
            float(target_soc_limit_config)  # Försök konvertera till float.
            if target_soc_limit_config is not None  # Om ett värde är satt.
            else None  # Annars, sätt till None.
        )

        # Hämtar värdet från nummer-entiteten för minsta laddström vid solenergiladdning.
        _min_solar_current_from_sensor = await self._get_number_value(
            self.min_solar_charge_current_entity_id,  # ID för den interna nummer-entiteten.
            default_value=None,  # Inget default här, hanteras nedan.
            is_config_key=False,  # Detta är redan ett entity_id.
        )
        # Sätter minsta solenergiladdström. Använder värdet från nummer-entiteten om det finns,
        # annars används en global konstant (MIN_CHARGE_CURRENT_A).
        min_solar_charge_current_a = (
            _min_solar_current_from_sensor  # Använd sensorvärdet om det finns.
            if _min_solar_current_from_sensor
            is not None  # Kontrollera om värdet är giltigt.
            else MIN_CHARGE_CURRENT_A  # Annars, använd standardminimum.
        )

        # Hämtar värdet från nummer-entiteten för solenergi-bufferten.
        _solar_buffer_from_sensor = await self._get_number_value(
            self.solar_buffer_entity_id, default_value=None, is_config_key=False
        )
        # Sätter solenergi-bufferten. Använder värdet från nummer-entiteten om det finns,
        # annars används en global konstant (POWER_MARGIN_W).
        solar_buffer_w = (
            _solar_buffer_from_sensor  # Använd sensorvärdet.
            if _solar_buffer_from_sensor is not None  # Om giltigt.
            else POWER_MARGIN_W  # Annars, använd standardbuffert.
        )

        # Initierar flaggan för om laddning ska ske till False (standard).
        self.should_charge_flag = False
        # Sätter målladdströmmen initialt till laddarens hårdvarumaximum.
        # Detta värde kan justeras nedåt av solenergilogiken.
        self.target_charge_current_a = charger_hw_max_amps
        # Initierar en sträng som förklarar det aktuella beslutet eller anledningen till ingen laddning.
        reason_for_action = "Ingen styrning aktiv."
        # Sätter det interna styrningsläget initialt till manuellt (AV).
        self.active_control_mode_internal = CONTROL_MODE_MANUAL

        # Start på huvudlogiken för att avgöra om och hur laddning ska ske.
        # Kontrollerar först blockerande tillstånd.
        # Om laddaren är frånkopplad eller offline:
        if (
            charger_status
            in EASEE_STATUS_DISCONNECTED  # Är statusen i listan över frånkopplade statusar?
            or charger_status == EASEE_STATUS_OFFLINE  # Eller är statusen offline?
        ):
            # Sätt läget till manuellt och ingen laddning.
            self.active_control_mode_internal = CONTROL_MODE_MANUAL
            self.should_charge_flag = False
            # Sätt anledningen.
            reason_for_action = (
                f"Laddaren är frånkopplad/offline (status: {charger_status})."
            )
            # Om en laddningssession pågick, återställ sessionsdata.
            if self.session_start_time_utc is not None:
                self._reset_session_data(reason_for_action)
            # Återställ timers och flaggor relaterade till solenergiladdning.
            self._solar_surplus_start_time = None
            self._solar_session_active = False
            # Återställ flagga för om Pris/Tid var det som senast initierade laddning.
            self._price_time_eligible_for_charging = False
        # Om huvudströmbrytaren för laddboxen är AV:
        elif not self.charger_main_switch_state:
            # Sätt läget till manuellt och ingen laddning.
            self.active_control_mode_internal = CONTROL_MODE_MANUAL
            self.should_charge_flag = False
            reason_for_action = "Huvudströmbrytare för laddbox är AV."
            if self.session_start_time_utc is not None:
                self._reset_session_data(reason_for_action)
            self._solar_surplus_start_time = None
            self._solar_session_active = False
            self._price_time_eligible_for_charging = False
        # Om bilens laddningsnivå (SoC) har nått den inställda gränsen:
        elif (
            current_soc_percent is not None  # Finns ett SoC-värde?
            and target_soc_limit is not None  # Finns en SoC-gräns?
            and current_soc_percent >= target_soc_limit  # Är SoC >= gränsen?
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
        # Om inga av ovanstående blockerande tillstånd är uppfyllda, utvärdera smarta laddningslägen:
        else:
            # Initiera flagga för om Pris/Tid-villkoren är uppfyllda.
            price_time_conditions_met = False
            # Om Pris/Tid-switchen är PÅ:
            if smart_charging_enabled:
                # Kontrollera om priset är OK (spotpris + påslag <= max accepterat pris).
                price_ok = (
                    current_price_kr is not None  # Finns ett aktuellt pris?
                    and current_price_kr
                    <= max_accepted_price_kr  # Är det lägre än eller lika med maxpriset?
                )
                # Om priset är OK och tidsschemat är aktivt:
                if price_ok and time_schedule_active:
                    # Då är alla villkor för Pris/Tid-laddning uppfyllda.
                    price_time_conditions_met = True

            # Om villkoren för Pris/Tid-laddning är uppfyllda:
            if price_time_conditions_met:
                # Sätt aktivt styrningsläge till Pris/Tid.
                self.active_control_mode_internal = CONTROL_MODE_PRICE_TIME
                # Sätt flaggan att laddning ska ske.
                self.should_charge_flag = True
                # Sätt målladdström till laddarens hårdvarumaximum.
                self.target_charge_current_a = charger_hw_max_amps
                # Sätt anledningen.
                reason_for_action = f"Pris/Tid-laddning aktiv (Pris: {current_price_kr:.2f} <= {max_accepted_price_kr:.2f} kr, Tidsschema PÅ)."
                # Återställ eventuell pågående solenergi-timer och session.
                self._solar_surplus_start_time = None
                self._solar_session_active = False
                # Om ingen session pågår eller om den tidigare sessionen inte var en Pris/Tid-session:
                if (
                    self.session_start_time_utc is None  # Ingen session aktiv?
                    or not self._price_time_eligible_for_charging  # Eller var föregående session inte Pris/Tid?
                ):
                    # Om en session faktiskt pågick (t.ex. solenergi):
                    if self.session_start_time_utc is not None:
                        # Logga att vi byter från den tidigare sessionstypen.
                        _LOGGER.info(
                            "Avslutar föregående session (%s) för att starta Pris/Tid.",
                            self.active_control_mode_internal  # Detta kommer vara det gamla värdet innan det sätts till PRICE_TIME
                            if self.active_control_mode_internal  # if-sats för att hantera om det är None
                            != CONTROL_MODE_PRICE_TIME  # och inte redan PRICE_TIME
                            else "annan",  # Fallback-text.
                        )
                        # Återställ sessionsdata.
                        self._reset_session_data(
                            f"Avslutar {self.active_control_mode_internal if self.active_control_mode_internal != CONTROL_MODE_PRICE_TIME else 'annan'} för Pris/Tid"
                        )
                    # Logga att en ny Pris/Tid-session startas.
                    _LOGGER.info("Startar ny Pris/Tid-session.")
                    # Sätt starttiden för sessionen.
                    self.session_start_time_utc = dt_util.utcnow()
                # Markera att den nuvarande sessionen (om den startas) är en Pris/Tid-session.
                self._price_time_eligible_for_charging = True

            # Om Pris/Tid-villkoren INTE är uppfyllda, OCH solenergiladdning är aktiverad (switch PÅ) OCH solenergi-schemat är aktivt:
            ### KORRIGERING STARTAR HÄR ### (Detta block är en tidigare korrigering från mig, se till att det är din avsedda logik)
            elif solar_charging_enabled and solar_schedule_active:
                # Kommentar: active_control_mode_internal sätts nedan när/om solenergiladdning faktiskt startar.
                # Beräkna tillgängligt solöverskott i Watt.
                available_solar_surplus_w = (
                    current_solar_production_w  # Total solproduktion.
                    - (  # Minus
                        current_house_power_w  # Husets förbrukning.
                        if current_house_power_w is not None  # Om husförbrukning finns.
                        else 0  # Annars antag 0.
                    )
                    - solar_buffer_w  # Minus den inställda bufferten.
                )

                # Om det finns ett positivt solöverskott:
                if available_solar_surplus_w > 0:
                    # Beräkna hur många Ampere detta överskott motsvarar för trefasladdning.
                    # math.floor avrundar nedåt till närmaste heltal.
                    calculated_solar_current_a = math.floor(
                        available_solar_surplus_w
                        / (
                            PHASES * VOLTAGE_PHASE_NEUTRAL
                        )  # Effekt / (antal faser * spänning per fas)
                    )
                    # Om den beräknade solströmmen är tillräcklig (minst lika med minsta tillåtna för sol):
                    if calculated_solar_current_a >= min_solar_charge_current_a:
                        # Om ingen solenergisession är aktiv just nu:
                        if not self._solar_session_active:
                            # Om fördröjningstimern för solöverskott inte har startat än:
                            if self._solar_surplus_start_time is None:
                                # Starta timern genom att sätta starttiden till nuvarande tid.
                                self._solar_surplus_start_time = current_time

                            # Om tiden som passerat sedan timern startade är längre än eller lika med den inställda fördröjningen:
                            if (
                                current_time - self._solar_surplus_start_time
                            ).total_seconds() >= SOLAR_SURPLUS_DELAY_SECONDS:
                                # Fördröjningen har passerat, dags att starta/aktivera solenergiladdning.
                                self.active_control_mode_internal = CONTROL_MODE_SOLAR_SURPLUS  # Sätt aktivt läge till Solenergi.
                                self.should_charge_flag = (
                                    True  # Sätt flaggan att laddning ska ske.
                                )
                                # Sätt målladdströmmen till den beräknade solströmmen, men inte högre än laddarens max.
                                self.target_charge_current_a = min(
                                    calculated_solar_current_a, charger_hw_max_amps
                                )
                                # Sätt anledningen.
                                reason_for_action = f"Solenergiladdning aktiv (Överskott: {available_solar_surplus_w:.0f}W -> {self.target_charge_current_a:.1f}A)."
                                # Markera att en solenergisession nu är aktiv.
                                self._solar_session_active = True
                                # Om ingen session pågick, eller om föregående session var Pris/Tid:
                                if (
                                    self.session_start_time_utc is None
                                    or self._price_time_eligible_for_charging  # Om Pris/Tid var det som gällde innan.
                                ):
                                    # Om en session faktiskt pågick (måste ha varit Pris/Tid i detta fall):
                                    if self.session_start_time_utc is not None:
                                        # Logga att vi byter från den.
                                        _LOGGER.info(
                                            "Avslutar föregående session (%s) för att starta Solenergi.",
                                            self.active_control_mode_internal  # Det gamla värdet.
                                            if self.active_control_mode_internal
                                            != CONTROL_MODE_SOLAR_SURPLUS  # Om det inte redan var sol (bör inte hända här).
                                            else "annan",
                                        )
                                        # Återställ sessionsdata.
                                        self._reset_session_data(
                                            f"Avslutar {self.active_control_mode_internal if self.active_control_mode_internal != CONTROL_MODE_SOLAR_SURPLUS else 'annan'} för Solenergi"
                                        )
                                    # Logga att en ny solenergisession startas.
                                    _LOGGER.info("Startar ny Solenergi-session.")
                                    # Sätt starttiden för sessionen.
                                    self.session_start_time_utc = dt_util.utcnow()
                            # Om fördröjningstiden INTE har passerat än:
                            else:
                                # Sätt läget till manuellt (vi styr inte aktivt laddningen än).
                                self.active_control_mode_internal = CONTROL_MODE_MANUAL
                                self.should_charge_flag = (
                                    False  # Laddning ska inte ske.
                                )
                                # Sätt anledningen till att vi väntar.
                                reason_for_action = f"Väntar på att solöverskott ({available_solar_surplus_w:.0f}W -> {calculated_solar_current_a:.1f}A) ska stabiliseras."
                        # Om en solenergisession REDAN ÄR AKTIV:
                        else:
                            # Behåll solenergiläget.
                            self.active_control_mode_internal = (
                                CONTROL_MODE_SOLAR_SURPLUS
                            )
                            self.should_charge_flag = True  # Fortsätt ladda.
                            # Uppdatera målladdströmmen baserat på det nuvarande överskottet.
                            self.target_charge_current_a = min(
                                calculated_solar_current_a, charger_hw_max_amps
                            )
                            # Sätt anledningen.
                            reason_for_action = f"Solenergiladdning pågår (Överskott: {available_solar_surplus_w:.0f}W -> {self.target_charge_current_a:.1f}A)."
                    # Om det beräknade solöverskottet är FÖR LITET för minsta laddström:
                    else:
                        # Sätt läget till manuellt.
                        self.active_control_mode_internal = CONTROL_MODE_MANUAL
                        self.should_charge_flag = False  # Ingen laddning.
                        # Sätt anledningen.
                        reason_for_action = f"För lite solöverskott ({available_solar_surplus_w:.0f}W -> {calculated_solar_current_a:.1f}A < {min_solar_charge_current_a:.1f}A min)."
                        # Nollställ fördröjningstimern och flaggan för aktiv solsession.
                        self._solar_surplus_start_time = None
                        self._solar_session_active = False
                        # Om en solsession var aktiv och avbröts, och det inte var Pris/Tid som tog över:
                        if (
                            self.session_start_time_utc is not None
                            and not self._price_time_eligible_for_charging
                        ):
                            self._reset_session_data(
                                reason_for_action
                            )  # Återställ sessionsdata.
                # Om det INTE finns något positivt solöverskott alls:
                else:
                    self.active_control_mode_internal = CONTROL_MODE_MANUAL
                    self.should_charge_flag = False
                    reason_for_action = f"Inget solöverskott tillgängligt ({available_solar_surplus_w:.0f}W)."
                    self._solar_surplus_start_time = None
                    self._solar_session_active = False
                    if (
                        self.session_start_time_utc is not None
                        and not self._price_time_eligible_for_charging
                    ):
                        self._reset_session_data(reason_for_action)

                # Om solenergilogiken har körts, sätt att Pris/Tid inte är den som är berättigad.
                self._price_time_eligible_for_charging = False
            ### KORRIGERING SLUTAR HÄR ###
            # Om varken Pris/Tid eller Solenergi-villkoren är uppfyllda:
            else:
                self.active_control_mode_internal = (
                    CONTROL_MODE_MANUAL  # Manuell/AV-läge.
                )
                self.should_charge_flag = False  # Ingen laddning.
                reason_for_action = "Inga aktiva smarta laddningsvillkor uppfyllda."
                # Om en session pågick, återställ den.
                if self.session_start_time_utc is not None:
                    self._reset_session_data(reason_for_action)
                # Nollställ solenergi-specifika flaggor/timers.
                self._solar_surplus_start_time = None
                self._solar_session_active = False
                self._price_time_eligible_for_charging = False

        # Anropa metoden som faktiskt skickar kommandon till laddaren,
        # baserat på de beslut som fattats ovan.
        await self._control_charger(
            self.should_charge_flag, self.target_charge_current_a, reason_for_action
        )

        # Sätter det "officiella" aktiva styrningsläget som exponeras utåt.
        # Om self.active_control_mode_internal är None (vilket det inte borde vara här), fall tillbaka till MANUELL.
        self.active_control_mode = (
            self.active_control_mode_internal or CONTROL_MODE_MANUAL
        )
        # Uppdaterar tidsstämpeln för den senaste uppdateringen.
        self.last_update_time = current_time

        # Loggar en sammanfattning av uppdateringscykelns resultat.
        _LOGGER.debug(
            "Uppdateringscykel klar. Styrningsläge: %s. Ska ladda: %s. Ström: %.1fA. Anledning: %s. Laddarstatus: %s",
            self.active_control_mode,  # Det slutgiltiga styrningsläget.
            self.should_charge_flag,  # Om laddning ska ske.
            self.target_charge_current_a,  # Den målsatta laddströmmen.
            reason_for_action,  # Den huvudsakliga anledningen till beslutet.
            charger_status,  # Laddarens status.
        )

        # Returnerar en dictionary med data som kan användas av sensorer kopplade till denna koordinator.
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
