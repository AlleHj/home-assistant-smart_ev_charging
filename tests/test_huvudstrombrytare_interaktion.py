# tests/test_huvudstrombrytare_interaktion.py
"""
Tester för interaktionen med laddboxens huvudströmbrytare.

Dessa tester verifierar hur SmartEVChargingCoordinator hanterar situationer
där laddboxens huvudströmbrytare (konfigurerad via CONF_CHARGER_ENABLED_SWITCH_ID)
är antingen AV när laddning önskas, eller stängs AV under en pågående laddsession.
"""

import pytest
import logging
from unittest.mock import (
    patch,
    MagicMock,
)  # MagicMock är inte använd här, kan tas bort om den inte behövs senare

from homeassistant.core import HomeAssistant
from homeassistant.const import (
    STATE_ON,
    STATE_OFF,
    SERVICE_TURN_ON,
    ATTR_ENTITY_ID,
)

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.smart_ev_charging.const import (
    DOMAIN,
    CONF_CHARGER_DEVICE,
    CONF_STATUS_SENSOR,
    CONF_CHARGER_ENABLED_SWITCH_ID,
    CONF_PRICE_SENSOR,
    CONF_TIME_SCHEDULE_ENTITY,
    CONF_DEBUG_LOGGING,
    EASEE_SERVICE_SET_DYNAMIC_CURRENT,  # Behövs för mockning
    EASEE_STATUS_READY_TO_CHARGE,
    EASEE_STATUS_CHARGING,
    CONTROL_MODE_MANUAL,
    CONTROL_MODE_PRICE_TIME,
)
from custom_components.smart_ev_charging.coordinator import SmartEVChargingCoordinator

# Mockade externa entitets-ID:n (som definierade i din originalfil)
MOCK_CONFIG_ENTRY_ID = "test_main_switch_interaction_entry"
MOCK_STATUS_SENSOR_ID = "sensor.test_charger_status_main_switch"
MOCK_PRICE_SENSOR_ID = "sensor.test_price_main_switch"
MOCK_SCHEDULE_ID = "schedule.test_charging_schedule_main_switch"
MOCK_MAIN_POWER_SWITCH_ID = "switch.mock_charger_power_main_switch"

# Faktiska entitets-ID:n som Home Assistant kommer att skapa baserat på namngivning.
ACTUAL_CONTROL_MODE_SENSOR_ID = "sensor.avancerad_elbilsladdning_aktivt_styrningslage"
ACTUAL_SMART_SWITCH_ID = "switch.avancerad_elbilsladdning_smart_laddning_aktiv"
ACTUAL_SOLAR_SWITCH_ID = "switch.avancerad_elbilsladdning_aktivera_solenergiladdning"
ACTUAL_MAX_PRICE_ID = "number.avancerad_elbilsladdning_max_elpris"
ACTUAL_SOLAR_BUFFER_ID = "number.avancerad_elbilsladdning_solenergi_buffer"
ACTUAL_MIN_SOLAR_CURRENT_ID = (
    "number.avancerad_elbilsladdning_minsta_laddstrom_solenergi"
)


@pytest.fixture(autouse=True)
def enable_debug_logging_fixture():
    """Aktiverar DEBUG-loggning för komponenten under testkörningen."""
    logging.getLogger(f"custom_components.{DOMAIN}").setLevel(logging.DEBUG)


@pytest.fixture
async def setup_coordinator(hass: HomeAssistant):
    """
    Fixture för att sätta upp SmartEVChargingCoordinator med en grundläggande,
    fungerande konfiguration för dessa tester.
    Returnerar en instans av koordinatorn.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_CHARGER_DEVICE: "mock_device_main_switch",
            CONF_STATUS_SENSOR: MOCK_STATUS_SENSOR_ID,
            CONF_CHARGER_ENABLED_SWITCH_ID: MOCK_MAIN_POWER_SWITCH_ID,  # Viktig för dessa tester
            CONF_PRICE_SENSOR: MOCK_PRICE_SENSOR_ID,
            CONF_TIME_SCHEDULE_ENTITY: MOCK_SCHEDULE_ID,
            CONF_DEBUG_LOGGING: True,  # Säkerställer att integrationen loggar på DEBUG-nivå
        },
        entry_id=MOCK_CONFIG_ENTRY_ID,
    )
    entry.add_to_hass(hass)

    # Ladda integrationen och vänta tills den är klar
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator: SmartEVChargingCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    assert coordinator is not None

    # Manuell tilldelning av de FAKTISKA interna entitets-ID:na till koordinatorn.
    coordinator.smart_enable_switch_entity_id = ACTUAL_SMART_SWITCH_ID
    coordinator.max_price_entity_id = ACTUAL_MAX_PRICE_ID
    coordinator.solar_enable_switch_entity_id = ACTUAL_SOLAR_SWITCH_ID
    coordinator.solar_buffer_entity_id = ACTUAL_SOLAR_BUFFER_ID
    coordinator.min_solar_charge_current_entity_id = ACTUAL_MIN_SOLAR_CURRENT_ID
    coordinator._internal_entities_resolved = (
        True  # Markera att ID:n är "manuellt lösta"
    )

    # Sätt grundläggande tillstånd för de FAKTISKA interna entiteterna
    hass.states.async_set(ACTUAL_SMART_SWITCH_ID, STATE_ON)
    hass.states.async_set(ACTUAL_SOLAR_SWITCH_ID, STATE_OFF)
    hass.states.async_set(ACTUAL_MAX_PRICE_ID, "1.00")
    hass.states.async_set(ACTUAL_SOLAR_BUFFER_ID, "200")
    hass.states.async_set(ACTUAL_MIN_SOLAR_CURRENT_ID, "6")
    hass.states.async_set(ACTUAL_CONTROL_MODE_SENSOR_ID, CONTROL_MODE_MANUAL)

    return coordinator


async def test_main_switch_off_prevents_charging(
    hass: HomeAssistant, setup_coordinator: SmartEVChargingCoordinator, caplog
):
    """
    Testar att laddning förhindras om huvudströmbrytaren är AV.

    SYFTE:
        Att verifiera att integrationen respekterar huvudströmbrytarens AV-läge
        och inte försöker starta laddning eller slå PÅ strömbrytaren, även om
        andra villkor för smart laddning (t.ex. Pris/Tid) är uppfyllda.

    FÖRUTSÄTTNINGAR (Arrange):
        - Koordinatorn är uppsatt och redo.
        - Huvudströmbrytaren för laddboxen (MOCK_MAIN_POWER_SWITCH_ID) är satt till STATE_OFF.
        - Villkoren för Pris/Tid-laddning är uppfyllda (lågt elpris, aktivt schema, smart-switch PÅ).
        - Laddarens status är redo för laddning.

    UTFÖRANDE (Act):
        - Koordinatorn kör en uppdateringscykel (async_refresh).

    FÖRVÄNTAT RESULTAT (Assert):
        - Inget försök görs att slå PÅ huvudströmbrytaren (inga `homeassistant.turn_on`-anrop).
        - Ingen laddning initieras (inga `easee.action_command` eller `easee.set_dynamic_current`-anrop).
        - Sensorn för aktivt styrningsläge visar `CONTROL_MODE_MANUAL` (AV).
        - En loggpost på DEBUG-nivå indikerar att anledningen till ingen laddning är att huvudströmbrytaren är AV.
    """
    coordinator = setup_coordinator

    # ARRANGE: Huvudströmbrytare AV, men Pris/Tid-villkor uppfyllda
    hass.states.async_set(MOCK_MAIN_POWER_SWITCH_ID, STATE_OFF)
    hass.states.async_set(
        MOCK_STATUS_SENSOR_ID,
        EASEE_STATUS_READY_TO_CHARGE[0],
    )
    hass.states.async_set(MOCK_PRICE_SENSOR_ID, "0.50")
    hass.states.async_set(MOCK_SCHEDULE_ID, STATE_ON)

    # Mocka tjänsteanrop
    turn_on_calls = async_mock_service(hass, "homeassistant", SERVICE_TURN_ON)
    action_command_calls = async_mock_service(hass, "easee", "action_command")

    set_charger_dynamic_limit_calls = async_mock_service(
        hass, "easee", "set_charger_dynamic_limit"
    )

    # ACT: Kör en uppdatering av koordinatorn
    caplog.clear()
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    # ASSERT: Verifiera att inga oönskade åtgärder har vidtagits
    assert len(turn_on_calls) == 0, "Försökte felaktigt slå PÅ huvudströmbrytaren."
    assert len(action_command_calls) == 0, (
        "Laddning startades felaktigt trots att huvudströmbrytaren var AV."
    )
    assert len(set_charger_dynamic_limit_calls) == 0, (
        "Laddström sattes felaktigt när ingen laddning ska ske."
    )

    # Verifiera att aktivt styrningsläge är korrekt
    control_mode_state = hass.states.get(ACTUAL_CONTROL_MODE_SENSOR_ID)
    assert control_mode_state is not None, (
        f"Sensor {ACTUAL_CONTROL_MODE_SENSOR_ID} hittades inte."
    )
    assert control_mode_state.state == CONTROL_MODE_MANUAL, (
        f"Förväntade styrningsläge {CONTROL_MODE_MANUAL}, men fick {control_mode_state.state}."
    )

    # Verifiera att korrekt anledning loggades (eller att should_charge är False och anledningen är korrekt)
    # Notera: Den exakta loggtexten kan variera beroende på hur _async_update_data formulerar "reason_for_action".
    # Det viktiga är att `coordinator.should_charge_flag` är False och anledningen är relaterad till huvudströmbrytaren.
    assert coordinator.should_charge_flag is False
    assert "Huvudströmbrytare för laddbox är AV" in coordinator.data.get(
        "should_charge_reason", ""
    )


async def test_manual_turn_off_main_switch_stops_charging(
    hass: HomeAssistant, setup_coordinator: SmartEVChargingCoordinator, caplog
):
    """
    Testar att en pågående smart laddning pausas korrekt om huvudströmbrytaren stängs av.

    SYFTE:
        Att verifiera att integrationen reagerar på en extern avstängning av
        huvudströmbrytaren genom att återställa sitt styrningsläge till manuellt
        och INTE försöka skicka kommandon till en strömlös laddare.

    FÖRUTSÄTTNINGAR (Arrange):
        - Steg 1: En Pris/Tid-styrd laddningssession startas framgångsrikt.
            - Huvudströmbrytaren är PÅ.
            - Villkor för Pris/Tid-laddning är uppfyllda.
            - Laddarens status är initialt redo, sedan 'charging'.
        - Steg 2: Huvudströmbrytaren stängs AV manuellt (simuleras).

    UTFÖRANDE (Act):
        - Koordinatorn kör en uppdateringscykel (async_refresh) efter att strömbrytaren stängts av.

    FÖRVÄNTAT RESULTAT (Assert):
        - INGEN tjänst `easee.action_command` (varken pause eller resume) ska anropas EFTER att strömmen brutits.
        - Inga försök görs att återuppta laddning eller sätta ström.
        - Sensorn för aktivt styrningsläge visar `CONTROL_MODE_MANUAL` (AV).
        - En loggpost på INFO-nivå indikerar att huvudströmbrytaren stängts av och att man återgår till manuellt läge.
    """
    coordinator = setup_coordinator

    # ARRANGE - Steg 1: Starta en Pris/Tid-laddning
    hass.states.async_set(MOCK_MAIN_POWER_SWITCH_ID, STATE_ON)
    hass.states.async_set(
        MOCK_STATUS_SENSOR_ID,
        EASEE_STATUS_READY_TO_CHARGE[0],
    )
    hass.states.async_set(MOCK_PRICE_SENSOR_ID, "0.50")
    hass.states.async_set(MOCK_SCHEDULE_ID, STATE_ON)

    action_command_calls = async_mock_service(hass, "easee", "action_command")
    set_charger_dynamic_limit_calls = async_mock_service(
        hass, "easee", "set_charger_dynamic_limit"
    )

    turn_on_calls = async_mock_service(hass, "homeassistant", SERVICE_TURN_ON)

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert len(action_command_calls) == 1, "Laddning startade inte initialt."
    assert action_command_calls[0].data["action_command"] == "start"
    assert len(set_charger_dynamic_limit_calls) == 1, "Laddström sattes inte initialt."
    assert (
        hass.states.get(ACTUAL_CONTROL_MODE_SENSOR_ID).state == CONTROL_MODE_PRICE_TIME
    )

    # ARRANGE - Steg 2: Simulera att laddning pågår och huvudströmbrytaren stängs av
    hass.states.async_set(MOCK_STATUS_SENSOR_ID, EASEE_STATUS_CHARGING)
    hass.states.async_set(MOCK_MAIN_POWER_SWITCH_ID, STATE_OFF)

    action_command_calls.clear()  # Rensa tidigare anrop för att verifiera nya åtgärder
    set_charger_dynamic_limit_calls.clear()
    turn_on_calls.clear()
    caplog.clear()

    # ACT
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    # ASSERT
    assert (
        len(action_command_calls) == 0
    ), (  # Viktigt: Inget paus-kommando ska skickas till en strömlös enhet
        "Försökte skicka kommando till laddaren efter att strömmen brutits."
    )
    assert len(set_charger_dynamic_limit_calls) == 0
    assert len(turn_on_calls) == 0

    assert hass.states.get(ACTUAL_CONTROL_MODE_SENSOR_ID).state == CONTROL_MODE_MANUAL
    # Verifiera att korrekt loggmeddelande skrevs när _control_charger avbröt pga huvudströmbrytaren
    expected_log_message = (
        "Huvudströmbrytare är AV. Inga kommandon skickas till laddaren."
    )
    assert expected_log_message in caplog.text, (
        f"Förväntade loggmeddelande '{expected_log_message}' hittades inte i caplog."
    )
