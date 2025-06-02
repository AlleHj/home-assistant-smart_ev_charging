# test_solar_to_price_time_transition.py
"""
Testar övergången från Solenergiladdning till Pris/Tid-laddning
när Pris/Tid-schemat blir aktivt.
"""

import pytest
import logging
from unittest.mock import patch
import math
from datetime import datetime, timedelta, timezone

from homeassistant.core import HomeAssistant
from homeassistant.const import STATE_ON, STATE_OFF, STATE_UNAVAILABLE
from homeassistant.util import dt as dt_util

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
    async_fire_time_changed,
)

from custom_components.smart_ev_charging.const import (
    DOMAIN,
    CONF_CHARGER_DEVICE,
    CONF_STATUS_SENSOR,
    CONF_CHARGER_ENABLED_SWITCH_ID,
    CONF_PRICE_SENSOR,
    CONF_TIME_SCHEDULE_ENTITY,
    CONF_SOLAR_PRODUCTION_SENSOR,
    CONF_HOUSE_POWER_SENSOR,
    CONF_SOLAR_SCHEDULE_ENTITY,  # Även om det inte används, behövs det för config
    CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR,
    CONF_CHARGER_DYNAMIC_CURRENT_SENSOR,
    CONF_DEBUG_LOGGING,
    ENTITY_ID_SUFFIX_SMART_ENABLE_SWITCH,
    ENTITY_ID_SUFFIX_MAX_PRICE_NUMBER,
    ENTITY_ID_SUFFIX_ENABLE_SOLAR_CHARGING_SWITCH,
    ENTITY_ID_SUFFIX_SOLAR_BUFFER_NUMBER,
    ENTITY_ID_SUFFIX_MIN_SOLAR_CHARGE_CURRENT_A_NUMBER,
    EASEE_SERVICE_SET_DYNAMIC_CURRENT,
    EASEE_SERVICE_RESUME_CHARGING,
    EASEE_STATUS_CHARGING,
    CONTROL_MODE_SOLAR_SURPLUS,
    CONTROL_MODE_PRICE_TIME,
    MIN_CHARGE_CURRENT_A,
    MAX_CHARGE_CURRENT_A_HW_DEFAULT,  # Antag att detta är "max"
    SOLAR_SURPLUS_DELAY_SECONDS,
)
from custom_components.smart_ev_charging.coordinator import SmartEVChargingCoordinator

# Konstanter för testet
PRICE_TIME_SCHEDULE_ID = "schedule.price_time_charging_20_07"
SOLAR_SCHEDULE_ID = "schedule.solar_always_active"  # För konfigurationen
CHARGER_DEVICE_ID = "easee_sol_to_price"
STATUS_SENSOR_ID = "sensor.easee_status_sol_to_price"
POWER_SWITCH_ID = "switch.easee_power_sol_to_price"
PRICE_SENSOR_ID = "sensor.nordpool_price_sol_to_price"
SOLAR_PROD_SENSOR_ID = "sensor.solar_production_sol_to_price"
HOUSE_POWER_SENSOR_ID = "sensor.house_power_sol_to_price"
MAX_CURRENT_SENSOR_ID = (
    "sensor.charger_max_current_sol_to_price"  # Sensor för hårdvarumax
)
DYN_CURRENT_SENSOR_ID = (
    "sensor.charger_dynamic_current_sol_to_price"  # Sensor för nuvarande dynamisk gräns
)

# Hårdkodade ID:n för interna entiteter (för enkelhetens skull i testet)
SMART_ENABLE_SWITCH_ID = (
    f"switch.{DOMAIN}_test_sol_to_price_{ENTITY_ID_SUFFIX_SMART_ENABLE_SWITCH}"
)
MAX_PRICE_NUMBER_ID = (
    f"number.{DOMAIN}_test_sol_to_price_{ENTITY_ID_SUFFIX_MAX_PRICE_NUMBER}"
)
SOLAR_ENABLE_SWITCH_ID = (
    f"switch.{DOMAIN}_test_sol_to_price_{ENTITY_ID_SUFFIX_ENABLE_SOLAR_CHARGING_SWITCH}"
)
SOLAR_BUFFER_NUMBER_ID = (
    f"number.{DOMAIN}_test_sol_to_price_{ENTITY_ID_SUFFIX_SOLAR_BUFFER_NUMBER}"
)
MIN_SOLAR_CURRENT_NUMBER_ID = f"number.{DOMAIN}_test_sol_to_price_{ENTITY_ID_SUFFIX_MIN_SOLAR_CHARGE_CURRENT_A_NUMBER}"


@pytest.fixture(autouse=True)
def enable_debug_logging():
    """Aktivera debug-loggning för komponenten."""
    logging.getLogger(f"custom_components.{DOMAIN}").setLevel(logging.DEBUG)


async def test_solar_to_price_time_transition(hass: HomeAssistant, caplog):
    """
    Testar övergången från Solenergiladdning till Pris/Tid när schemat startar.

    SYFTE:
        Att verifiera att:
        1. Solenergiladdning är aktiv initialt när solen lyser och villkoren är uppfyllda.
        2. När Pris/Tid-schemat startar (kl. 20:00), tar det över styrningen från solenergiladdning.
        3. Den dynamiska strömgränsen sätts till hårdvarumaximum (från MAX_CURRENT_SENSOR_ID)
           när Pris/Tid tar över.

    FÖRUTSÄTTNINGAR (Arrange):
        - Elpriset är konstant lågt (0.20 kr/kWh).
        - Maxpriset för Pris/Tid är högre (0.50 kr/kWh).
        - Switch för "Smart Laddning" (Pris/Tid) är PÅ.
        - Switch för "Solenergiladdning" är PÅ.
        - Solenergi produceras (t.ex. 5000 W).
        - Husets förbrukning är låg (t.ex. 500 W).
        - Solenergi buffert är satt (t.ex. 300 W).
        - Minsta laddström för sol är satt (t.ex. 6 A).
        - Pris/Tid-schemat är initialt AV (tiden är 19:00) och blir PÅ kl. 20:00.
        - Solenergi-schemat (om konfigurerat) är PÅ. (I detta fall är CONF_SOLAR_SCHEDULE_ENTITY satt till None i koden för att alltid tillåta sol om switch är på)
        - Laddaren är initialt i 'charging'-status.
        - Sensor för dynamisk strömgräns finns och är satt till 7A initialt.
        - Sensor för max hårdvaruström finns och är satt till 16A.


    UTFÖRANDE (Act) & FÖRVÄNTAT RESULTAT (Assert):
        - Kl. 19:00: Solenergiladdning ska vara aktiv.
            - `active_control_mode` ska vara `CONTROL_MODE_SOLAR_SURPLUS`.
            - `set_dynamic_current` ska ha anropats för solenergi (t.ex. till 7A).
        - När klockan slår 20:00 (Pris/Tid-schema blir aktivt):
            - `active_control_mode` ska byta till `CONTROL_MODE_PRICE_TIME`.
            - `set_dynamic_current` ska anropas igen, nu med hårdvarumax (16A).
    """  # noqa: D212
    # 1. ARRANGE
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_CHARGER_DEVICE: CHARGER_DEVICE_ID,
            CONF_STATUS_SENSOR: STATUS_SENSOR_ID,
            CONF_CHARGER_ENABLED_SWITCH_ID: POWER_SWITCH_ID,
            CONF_PRICE_SENSOR: PRICE_SENSOR_ID,
            CONF_TIME_SCHEDULE_ENTITY: PRICE_TIME_SCHEDULE_ID,  # Schema för Pris/Tid
            CONF_SOLAR_PRODUCTION_SENSOR: SOLAR_PROD_SENSOR_ID,
            CONF_HOUSE_POWER_SENSOR: HOUSE_POWER_SENSOR_ID,
            CONF_SOLAR_SCHEDULE_ENTITY: None,  # Inget specifikt schema för sol, styrs av switchen
            CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR: MAX_CURRENT_SENSOR_ID,
            CONF_CHARGER_DYNAMIC_CURRENT_SENSOR: DYN_CURRENT_SENSOR_ID,
            CONF_DEBUG_LOGGING: True,
        },
        entry_id="test_sol_to_price",  # Unikt ID för testet
    )
    entry.add_to_hass(hass)

    # Patcha _setup_listeners för att undvika problem med externa lyssnare i testmiljön.
    # Patcha även _resolve_internal_entities för att kunna sätta ID:n manuellt.
    with (
        patch(
            "custom_components.smart_ev_charging.coordinator.SmartEVChargingCoordinator._setup_listeners"
        ),
        patch(
            "custom_components.smart_ev_charging.coordinator.SmartEVChargingCoordinator._resolve_internal_entities",
            return_value=True,  # Låtsas att de är lösta
        ),
    ):
        # Skapa koordinatorn
        # Använd en kortare scan interval för snabbare testkörning om nödvändigt, men 30s är ok.
        coordinator = SmartEVChargingCoordinator(hass, entry, 30)

        # Manuell tilldelning av interna entitets-ID:n eftersom _resolve_internal_entities är patchad
        coordinator.smart_enable_switch_entity_id = SMART_ENABLE_SWITCH_ID
        coordinator.max_price_entity_id = MAX_PRICE_NUMBER_ID
        coordinator.solar_enable_switch_entity_id = SOLAR_ENABLE_SWITCH_ID
        coordinator.solar_buffer_entity_id = SOLAR_BUFFER_NUMBER_ID
        coordinator.min_solar_charge_current_entity_id = MIN_SOLAR_CURRENT_NUMBER_ID
        coordinator._internal_entities_resolved = True  # Markera som lösta

        # Sätt initiala tillstånd för externa sensorer och interna entiteter
        hass.states.async_set(POWER_SWITCH_ID, STATE_ON)
        hass.states.async_set(PRICE_SENSOR_ID, "0.20")  # Lågt pris
        hass.states.async_set(SOLAR_PROD_SENSOR_ID, "5000")  # Bra solproduktion (W)
        hass.states.async_set(HOUSE_POWER_SENSOR_ID, "500")  # Husets förbrukning (W)
        hass.states.async_set(
            MAX_CURRENT_SENSOR_ID, str(MAX_CHARGE_CURRENT_A_HW_DEFAULT)
        )  # Max hårdvaruström (16A)
        hass.states.async_set(
            DYN_CURRENT_SENSOR_ID, "7.0"
        )  # Initial dynamisk gräns satt av "solen"

        # Interna switchar och nummer-entiteter (som om användaren satt dem i UI)
        hass.states.async_set(SMART_ENABLE_SWITCH_ID, STATE_ON)  # Pris/Tid är aktiverat
        hass.states.async_set(MAX_PRICE_NUMBER_ID, "0.50")  # Maxpris för Pris/Tid
        hass.states.async_set(
            SOLAR_ENABLE_SWITCH_ID, STATE_ON
        )  # Solenergiladdning är aktiverat
        hass.states.async_set(SOLAR_BUFFER_NUMBER_ID, "300")  # Solenergi buffert (W)
        hass.states.async_set(
            MIN_SOLAR_CURRENT_NUMBER_ID, str(MIN_CHARGE_CURRENT_A)
        )  # Minsta laddström sol (6A)

        # Scheman: Pris/Tid är AV, Sol är PÅ (genom att inte ha ett schema och switchen är PÅ)
        # Starttid för simuleringen: 2025-05-30 19:00:00 UTC
        # Notera: dt_util.utcnow() i HA tester kan vara fixerad, vi använder specifik tid.
        start_time_utc = datetime(2025, 5, 30, 19, 0, 0, tzinfo=timezone.utc)
        hass.states.async_set(
            PRICE_TIME_SCHEDULE_ID, STATE_OFF
        )  # Pris/Tid-schemat är AV kl 19:00

        # Mocka tjänsteanrop
        set_charger_dynamic_limit_calls = async_mock_service(
            hass, "easee", "set_charger_dynamic_limit"
        )

        resume_calls = async_mock_service(hass, "easee", EASEE_SERVICE_RESUME_CHARGING)

        # 2. ACT & ASSERT - Steg 1: Kl. 19:00 (Solenergiladdning aktiv)
        print("TESTSTEG 1: Kl. 19:00 - Solenergiladdning ska vara aktiv")
        hass.states.async_set(
            STATUS_SENSOR_ID, EASEE_STATUS_CHARGING
        )  # Antag att den redan laddar (t.ex. manuellt startad eller från tidigare)
        # eller ready_to_charge för att trigga start.
        # EASEE_STATUS_CHARGING är bättre för att se om strömmen justeras.

        # Kör en första refresh för att sätta initialt läge
        # Se till att SOLAR_SURPLUS_DELAY_SECONDS passeras för att solenergiladdning ska bli aktiv
        # Vi simulerar detta genom att köra refresh flera gånger med tiden framflyttad
        # eller genom att anta att den redan har varit aktiv.
        # För detta test antar vi att solenergi redan har varit aktiv tillräckligt länge.
        # Detta kan kräva att man manipulerar coordinator._solar_surplus_start_time eller
        # kör flera async_refresh med async_fire_time_changed.
        # För enkelhetens skull, låt oss anta att den blir aktiv direkt om villkoren är uppfyllda
        # efter den initiala fördröjningen är över. Vi kan manuellt sätta den som aktiv i testet
        # eller låta den gå igenom sin delay.

        # Simulera att SOLAR_SURPLUS_DELAY_SECONDS har passerat
        # Detta är en förenkling. Ett mer robust test skulle hantera tiden exakt.
        coordinator._solar_surplus_start_time = start_time_utc - timedelta(
            seconds=SOLAR_SURPLUS_DELAY_SECONDS + 1
        )
        coordinator._solar_session_active = False  # Låt den bli aktiv via logiken

        with patch.object(dt_util, "utcnow", return_value=start_time_utc):
            await coordinator.async_refresh()
            await hass.async_block_till_done()

        assert coordinator.active_control_mode == CONTROL_MODE_SOLAR_SURPLUS, (
            f"Förväntade SOLENERGI kl 19:00, fick {coordinator.active_control_mode}"
        )

        # Förväntad ström från sol: (5000W - 500W - 300W) / 230V*3 = 4200W / 230V *3= ~6A
        # Detta avrundas nedåt till 18A. Den ska vara minst MIN_CHARGE_CURRENT_A (6A)
        # och max MAX_CHARGE_CURRENT_A_HW_DEFAULT (16A)
        # Så den bör försöka sätta 9A.
        # Dock har vi DYN_CURRENT_SENSOR_ID satt till 7.0A, så det är det den kommer utgå från.
        # Nej, logiken beräknar target_charge_current_a och jämför det med CONF_CHARGER_DYNAMIC_CURRENT_SENSOR.
        # Så om calculated_solar_current_a är 6A, och DYN_CURRENT_SENSOR_ID är 7A, ska den uppdatera till 9A.
        expected_solar_current = math.floor((5000 - 500 - 300) / (230 * 3))  # Blir 6A

        assert len(set_charger_dynamic_limit_calls) >= 1, (
            "set_dynamic_current anropades inte för solenergi initialt"
        )
        # Det senaste anropet ska vara för solenergi
        last_set_current_call = set_charger_dynamic_limit_calls[-1]
        assert last_set_current_call.data["current"] == expected_solar_current, (
            f"Förväntade ström {expected_solar_current}A för sol, fick {last_set_current_call.data['current']}A"
        )

        # Nollställ mock-anrop inför nästa steg
        set_charger_dynamic_limit_calls.clear()
        resume_calls.clear()

        # 2. ACT & ASSERT - Steg 2: Klockan slår 20:00 (Pris/Tid tar över)
        print("TESTSTEG 2: Kl. 20:00 - Pris/Tid ska ta över")
        time_at_20_00_utc = datetime(2025, 5, 30, 20, 0, 0, tzinfo=timezone.utc)

        # Uppdatera schemat till PÅ
        hass.states.async_set(PRICE_TIME_SCHEDULE_ID, STATE_ON)
        # Laddarens status är fortfarande 'charging'
        hass.states.async_set(STATUS_SENSOR_ID, EASEE_STATUS_CHARGING)
        # Den dynamiska gränsen är nu satt till `expected_solar_current` från föregående steg
        hass.states.async_set(DYN_CURRENT_SENSOR_ID, str(float(expected_solar_current)))

        # Flytta fram tiden och kör refresh
        with patch.object(dt_util, "utcnow", return_value=time_at_20_00_utc):
            # async_fire_time_changed(hass, time_at_20_00_utc) # Behövs om update_interval triggar
            await coordinator.async_refresh()  # Manuell trigger
            await hass.async_block_till_done()

        assert coordinator.active_control_mode == CONTROL_MODE_PRICE_TIME, (
            f"Förväntade PRIS_TID kl 20:00, fick {coordinator.active_control_mode}"
        )

        assert len(set_charger_dynamic_limit_calls) == 1, (
            "set_dynamic_current anropades inte eller anropades fel antal gånger vid övergång till Pris/Tid"
        )
        # Det nya anropet ska sätta strömmen till max hårdvarugräns
        assert (
            set_charger_dynamic_limit_calls[0].data["current"]
            == MAX_CHARGE_CURRENT_A_HW_DEFAULT
        ), (
            f"Förväntade ström {MAX_CHARGE_CURRENT_A_HW_DEFAULT}A för Pris/Tid, fick {set_charger_dynamic_limit_calls[0].data['current']}A"
        )

        # resume_calls bör inte anropas om laddningen redan pågick
        assert len(resume_calls) == 0, (
            "resume_charging anropades felaktigt vid övergång när laddning redan pågick"
        )

        # Ytterligare loggkontroll om det behövs
        # assert "Tar över från Solenergi till Pris/Tid" in caplog.text # Exempel
