# tests/test_solenergiladdning_livscykel.py
"""
Tester för att verifiera hela livscykeln för solenergiladdning.

Detta testfall säkerställer att koordinatorn korrekt hanterar hela flödet:
1.  Ignorerar ett negativt eller otillräckligt solöverskott.
2.  Väntar på att ett tillräckligt överskott ska vara stabilt över tid.
3.  Startar laddning och beräknar korrekt initial laddström.
4.  Justerar laddströmmen dynamiskt när solproduktionen ändras.
5.  Pausar laddningen när solöverskottet försvinner.
"""

import pytest
import logging
from datetime import timedelta
import math

from homeassistant.core import HomeAssistant
from homeassistant.const import STATE_ON, STATE_OFF, UnitOfPower
from homeassistant.util import dt as dt_util

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.smart_ev_charging.const import (
    DOMAIN,
    CONF_CHARGER_DEVICE,
    CONF_STATUS_SENSOR,
    CONF_SOLAR_PRODUCTION_SENSOR,
    CONF_HOUSE_POWER_SENSOR,
    CONF_CHARGER_ENABLED_SWITCH_ID,
    EASEE_STATUS_READY_TO_CHARGE,
    EASEE_STATUS_CHARGING,  # Används i teststeg 6
    CONTROL_MODE_MANUAL,
    CONTROL_MODE_SOLAR_SURPLUS,  # Används i detta test (hette CONTROL_MODE_SOLAR tidigare i coordinator.py, se kommentar nedan)
    SOLAR_SURPLUS_DELAY_SECONDS,
    MIN_CHARGE_CURRENT_A,
    ENTITY_ID_SUFFIX_SMART_ENABLE_SWITCH,
    ENTITY_ID_SUFFIX_MAX_PRICE_NUMBER,
    ENTITY_ID_SUFFIX_ENABLE_SOLAR_CHARGING_SWITCH,
    ENTITY_ID_SUFFIX_SOLAR_BUFFER_NUMBER,
    ENTITY_ID_SUFFIX_MIN_SOLAR_CHARGE_CURRENT_A_NUMBER,
    PHASES,
    VOLTAGE_PHASE_NEUTRAL,
    EASEE_SERVICE_SET_DYNAMIC_CURRENT,  # Korrekt importerad här
)
from custom_components.smart_ev_charging.coordinator import SmartEVChargingCoordinator

# Mockade entitets-ID:n för externa sensorer
MOCK_SOLAR_SENSOR_ID = "sensor.test_solar_production_lifecycle"
MOCK_HOUSE_POWER_SENSOR_ID = "sensor.test_house_power_lifecycle"
MOCK_STATUS_SENSOR_ID = "sensor.test_charger_status_lifecycle"
MOCK_MAIN_POWER_SWITCH_ID = "switch.mock_charger_power_solar_lifecycle"

CONTROL_MODE_SENSOR_ID = "sensor.avancerad_elbilsladdning_aktivt_styrningslage"


@pytest.fixture(autouse=True)
def enable_debug_logging():
    logging.getLogger(f"custom_components.{DOMAIN}").setLevel(logging.INFO)


async def test_solar_charging_full_lifecycle(hass: HomeAssistant, freezer):
    """Testar hela livscykeln för solenergiladdning."""

    # --- 1. ARRANGE ---
    # SYFTE: Sätt upp den grundläggande konfigurationen för integrationen
    # och mocka nödvändiga entiteter och tjänster.
    entry_id_for_test = "test_solar_lifecycle_entry"
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_CHARGER_DEVICE: "mock_device_solar_lifecycle",
            CONF_STATUS_SENSOR: MOCK_STATUS_SENSOR_ID,
            CONF_SOLAR_PRODUCTION_SENSOR: MOCK_SOLAR_SENSOR_ID,
            CONF_HOUSE_POWER_SENSOR: MOCK_HOUSE_POWER_SENSOR_ID,
            CONF_CHARGER_ENABLED_SWITCH_ID: MOCK_MAIN_POWER_SWITCH_ID,
        },
        entry_id=entry_id_for_test,
    )
    entry.add_to_hass(hass)

    # Ladda integrationen och vänta tills den är klar
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Hämta koordinator-instansen
    coordinator: SmartEVChargingCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    assert coordinator is not None

    # Manuell tilldelning av interna entitets-ID:n för att kringgå väntan på entity registry
    coordinator.smart_enable_switch_entity_id = (
        f"switch.{DOMAIN}_{entry_id_for_test}_{ENTITY_ID_SUFFIX_SMART_ENABLE_SWITCH}"
    )
    coordinator.max_price_entity_id = (
        f"number.{DOMAIN}_{entry_id_for_test}_{ENTITY_ID_SUFFIX_MAX_PRICE_NUMBER}"
    )
    coordinator.solar_enable_switch_entity_id = f"switch.{DOMAIN}_{entry_id_for_test}_{ENTITY_ID_SUFFIX_ENABLE_SOLAR_CHARGING_SWITCH}"
    coordinator.solar_buffer_entity_id = (
        f"number.{DOMAIN}_{entry_id_for_test}_{ENTITY_ID_SUFFIX_SOLAR_BUFFER_NUMBER}"
    )
    coordinator.min_solar_charge_current_entity_id = f"number.{DOMAIN}_{entry_id_for_test}_{ENTITY_ID_SUFFIX_MIN_SOLAR_CHARGE_CURRENT_A_NUMBER}"
    coordinator._internal_entities_resolved = True

    # Mocka tjänsteanrop till Easee-integrationen
    action_command_calls = async_mock_service(
        hass, "easee", "action_command"
    )  # Ersätter resume_calls och pause_calls
    set_current_calls = async_mock_service(
        hass,
        "easee",
        EASEE_SERVICE_SET_DYNAMIC_CURRENT,  # Använder importerad konstant
    )

    # Grundläggande setup för testet:
    # - Solenergiladdning är PÅ.
    # - Pris/Tid-styrd laddning är AV (för att isolera solenergilogiken).
    # - Laddaren är redo att ladda.
    # - Huvudströmbrytaren till laddaren är PÅ.
    # - Minsta laddström för solenergi är 6A.
    # - Solenergi-bufferten är 200W.
    # - Maxpris (för Pris/Tid, inte relevant här men sätts för fullständighet) är 10.0 kr.
    hass.states.async_set(coordinator.solar_enable_switch_entity_id, STATE_ON)
    hass.states.async_set(coordinator.smart_enable_switch_entity_id, STATE_OFF)
    hass.states.async_set(MOCK_STATUS_SENSOR_ID, EASEE_STATUS_READY_TO_CHARGE[0])
    hass.states.async_set(MOCK_MAIN_POWER_SWITCH_ID, STATE_ON)
    hass.states.async_set(coordinator.min_solar_charge_current_entity_id, "6")
    hass.states.async_set(coordinator.solar_buffer_entity_id, "200")
    hass.states.async_set(coordinator.max_price_entity_id, "10.0")

    # --- 2. Teststeg: Inget överskott ---
    # SYFTE: Verifiera att ingen laddning startar om solproduktionen är lägre än husets förbrukning + buffer.
    print("\nTESTSTEG: Inget överskott")
    # FÖRUTSÄTTNINGAR: Solproduktion: 500W, Husförbrukning: 1000W, Buffer: 200W. Överskott = 500-1000-200 = -700W.
    hass.states.async_set(
        MOCK_SOLAR_SENSOR_ID, "500", {"unit_of_measurement": UnitOfPower.WATT}
    )
    hass.states.async_set(
        MOCK_HOUSE_POWER_SENSOR_ID, "1000", {"unit_of_measurement": UnitOfPower.WATT}
    )

    # UTFÖRANDE: Kör en uppdatering av koordinatorn.
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    # FÖRVÄNTAT RESULTAT: Ingen laddning ska ha startats. Styrningsläget ska vara manuellt (AV).
    assert len(action_command_calls) == 0  # Kontrollerar action_command_calls
    assert hass.states.get(CONTROL_MODE_SENSOR_ID).state == CONTROL_MODE_MANUAL

    # --- 3. Teststeg: Otillräckligt överskott ---
    # SYFTE: Verifiera att ingen laddning startar om solöverskottet är positivt men för litet för att uppnå minsta laddström.
    print("\nTESTSTEG: Otillräckligt överskott")
    # FÖRUTSÄTTNINGAR: Minsta laddström 6A. Effekt för 6A trefas = 6A * 3 faser * 230V = 4140W.
    # Produktion sätts för att ge ett överskott strax under detta (t.ex. 4130W).
    # Tillgängligt överskott = Produktion - Husförbrukning - Buffer.
    min_solar_current_amps = 6
    power_for_min_current = (
        min_solar_current_amps * PHASES * VOLTAGE_PHASE_NEUTRAL
    )  # 4140W
    house_consumption = 1000
    solar_buffer = 200
    # Produktion som ger ett överskott på (power_for_min_current - 10W)
    production_for_insufficient = (
        (power_for_min_current - 10) + house_consumption + solar_buffer
    )  # 4130 + 1000 + 200 = 5330W
    # Faktiskt överskott blir: 5330 - 1000 - 200 = 4130W. Ström = floor(4130 / 690) = 5A.

    hass.states.async_set(
        MOCK_SOLAR_SENSOR_ID,
        str(production_for_insufficient),
        {"unit_of_measurement": UnitOfPower.WATT},
    )
    hass.states.async_set(
        MOCK_HOUSE_POWER_SENSOR_ID,
        str(house_consumption),
        {"unit_of_measurement": UnitOfPower.WATT},
    )

    # UTFÖRANDE: Kör en uppdatering.
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    # FÖRVÄNTAT RESULTAT: Ingen laddning. Styrningsläge manuellt.
    assert len(action_command_calls) == 0  # Kontrollerar action_command_calls
    assert hass.states.get(CONTROL_MODE_SENSOR_ID).state == CONTROL_MODE_MANUAL

    # --- 4. Teststeg: Tillräckligt överskott (inom fördröjning) ---
    # SYFTE: Verifiera att laddning inte startar omedelbart vid tillräckligt överskott, utan att fördröjningstiden respekteras.
    print("\nTESTSTEG: Tillräckligt överskott (inom fördröjning)")
    # FÖRUTSÄTTNINGAR: Produktion sätts för att ge 7A överskott.
    # (7A * 3 * 230V) + 1000W (hus) + 200W (buffer) = 4830W + 1200W = 6030W.
    current_target_amps_delay = 7
    production_for_delay = (
        (current_target_amps_delay * PHASES * VOLTAGE_PHASE_NEUTRAL)
        + house_consumption
        + solar_buffer
    )
    hass.states.async_set(
        MOCK_SOLAR_SENSOR_ID,
        str(production_for_delay),
        {"unit_of_measurement": UnitOfPower.WATT},
    )
    hass.states.async_set(
        MOCK_HOUSE_POWER_SENSOR_ID,
        str(house_consumption),
        {"unit_of_measurement": UnitOfPower.WATT},
    )

    # Nollställ interna timers för att säkerställa att fördröjningen testas korrekt.
    coordinator._solar_surplus_start_time = None
    coordinator._solar_session_active = False

    # UTFÖRANDE: Kör en uppdatering.
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    # FÖRVÄNTAT RESULTAT: Ingen laddning än. Fördröjningstimern ska ha startat. Styrningsläge manuellt.
    assert len(action_command_calls) == 0  # Kontrollerar action_command_calls
    assert (
        coordinator._solar_surplus_start_time is not None
    )  # Timern ska ha initierats.
    assert (
        hass.states.get(CONTROL_MODE_SENSOR_ID).state == CONTROL_MODE_MANUAL
    )  # Fortfarande manuellt under fördröjning.

    # --- 5. Teststeg: Laddning Startar efter fördröjning ---
    # SYFTE: Verifiera att laddning startar efter att fördröjningstiden har passerat.
    print("\nTESTSTEG: Laddning startar efter fördröjning")
    # FÖRUTSÄTTNINGAR: Samma produktionsnivå som tidigare (ger 7A). Tiden har nu gått.

    # UTFÖRANDE: Hoppa fram i tiden och kör en uppdatering.
    freezer.tick(timedelta(seconds=SOLAR_SURPLUS_DELAY_SECONDS + 1))
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    # FÖRVÄNTAT RESULTAT: Laddning ska starta. Styrningsläge SOLENERGI. Korrekt ström ska sättas.
    assert len(action_command_calls) == 1, "Laddning startade inte efter fördröjningen."
    assert (
        action_command_calls[0].data["action_command"] == "resume"
    )  # Kontrollerar resume-kommando
    assert hass.states.get(CONTROL_MODE_SENSOR_ID).state == CONTROL_MODE_SOLAR_SURPLUS

    # Förväntad ström är current_target_amps_delay (7A)
    assert len(set_current_calls) == 1, (
        "set_dynamic_current anropades inte korrekt vid start."
    )
    assert set_current_calls[0].data["currentP1"] == current_target_amps_delay
    assert set_current_calls[0].data["currentP2"] == current_target_amps_delay
    assert set_current_calls[0].data["currentP3"] == current_target_amps_delay

    # --- 6. Teststeg: Laddströmmen justeras dynamiskt ---
    # SYFTE: Verifiera att laddströmmen anpassas om solproduktionen ändras medan laddning pågår.
    print("\nTESTSTEG: Laddströmmen justeras dynamiskt")
    # FÖRUTSÄTTNINGAR: Produktionen ökar för att ge 10A överskott.
    # (10A * 3 * 230V) + 1000W (hus) + 200W (buffer) = 6900W + 1200W = 8100W.
    current_target_amps_adjust = 10
    production_for_adjust = (
        (current_target_amps_adjust * PHASES * VOLTAGE_PHASE_NEUTRAL)
        + house_consumption
        + solar_buffer
    )
    hass.states.async_set(
        MOCK_SOLAR_SENSOR_ID,
        str(production_for_adjust),
        {"unit_of_measurement": UnitOfPower.WATT},
    )
    # Simulera att laddaren nu är i 'charging'-status efter föregående steg.
    hass.states.async_set(
        MOCK_STATUS_SENSOR_ID, EASEE_STATUS_CHARGING
    )  # Använder konstanten

    # UTFÖRANDE: Kör en uppdatering.
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    # FÖRVÄNTAT RESULTAT: Ett nytt anrop till set_dynamic_current ska ha gjorts med den nya strömmen (10A).
    assert len(set_current_calls) == 2, (  # Nu 2 anrop totalt (start + justering)
        "set_dynamic_current anropades inte vid justering."
    )
    assert set_current_calls[1].data["currentP1"] == current_target_amps_adjust
    assert set_current_calls[1].data["currentP2"] == current_target_amps_adjust
    assert set_current_calls[1].data["currentP3"] == current_target_amps_adjust

    # --- 7. Teststeg: Laddning pausas när överskottet försvinner ---
    # SYFTE: Verifiera att laddningen pausas om solöverskottet blir för litet.
    print("\nTESTSTEG: Laddning pausas")
    # FÖRUTSÄTTNINGAR: Produktionen sjunker så att överskottet blir för litet (t.ex. 500W).
    # Överskott = 1500W (prod) - 1000W (hus) - 200W (buffer) = 300W. Ström = floor(300/690) = 0A.
    hass.states.async_set(
        MOCK_SOLAR_SENSOR_ID, "1500", {"unit_of_measurement": UnitOfPower.WATT}
    )
    # Status är fortfarande 'charging' från föregående steg, vilket är korrekt för att testa att den aktivt pausas.

    # UTFÖRANDE: Kör en uppdatering.
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    # FÖRVÄNTAT RESULTAT: Laddningen ska pausas. Styrningsläge manuellt. Timers för solenergi ska nollställas.
    # action_command_calls hade 1 anrop (resume). Nu ska ett paus-kommando skickats. Totalt 2.
    assert len(action_command_calls) == 2, "Laddning pausades inte."
    assert (
        action_command_calls[1].data["action_command"] == "pause"
    )  # Sista kommandot ska vara paus

    # Styrningsläget ska vara SOLENERGI, men should_charge_flag blir False, vilket leder till paus.
    # Om inget överskott finns och inget pris/tid är aktivt, faller den tillbaka till MANUELL.
    # Denna logik finns i slutet av _async_update_data i coordinator.py.
    assert hass.states.get(CONTROL_MODE_SENSOR_ID).state == CONTROL_MODE_MANUAL
    assert coordinator._solar_surplus_start_time is None  # Timern ska vara nollställd.
    assert coordinator._solar_session_active is False  # Solsessionen ska vara avslutad.

    print("\nTestet slutfört framgångsrikt!")
