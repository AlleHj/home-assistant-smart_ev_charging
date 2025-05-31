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
    EASEE_SERVICE_RESUME_CHARGING,
    EASEE_SERVICE_PAUSE_CHARGING,
    EASEE_SERVICE_SET_DYNAMIC_CURRENT,
    EASEE_STATUS_READY_TO_CHARGE,
    EASEE_STATUS_CHARGING,
    CONTROL_MODE_MANUAL,
    CONTROL_MODE_PRICE_TIME,
    # Följande suffix används för att bygga de faktiska ID:na, kan vara bra att ha kvar för referens
    # ENTITY_ID_SUFFIX_SMART_ENABLE_SWITCH,
    # ENTITY_ID_SUFFIX_MAX_PRICE_NUMBER,
    # ENTITY_ID_SUFFIX_ENABLE_SOLAR_CHARGING_SWITCH,
    # ENTITY_ID_SUFFIX_SOLAR_BUFFER_NUMBER,
    # ENTITY_ID_SUFFIX_MIN_SOLAR_CHARGE_CURRENT_A_NUMBER,
)
from custom_components.smart_ev_charging.coordinator import SmartEVChargingCoordinator

# Mockade externa entitets-ID:n
MOCK_CONFIG_ENTRY_ID = "test_main_switch_interaction_entry"
MOCK_STATUS_SENSOR_ID = "sensor.test_charger_status_main_switch"
MOCK_PRICE_SENSOR_ID = "sensor.test_price_main_switch"
MOCK_SCHEDULE_ID = "schedule.test_charging_schedule_main_switch"
MOCK_MAIN_POWER_SWITCH_ID = "switch.mock_charger_power_main_switch"  # Denna switchs tillstånd manipuleras i testerna

# Faktiska entitets-ID:n som Home Assistant kommer att skapa baserat på namngivning.
# Dessa används för att interagera med de entiteter som integrationen själv skapar.
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
    # Detta är nödvändigt eftersom _resolve_internal_entities kan köras innan
    # entiteterna är fullt registrerade i en testmiljö.
    coordinator.smart_enable_switch_entity_id = ACTUAL_SMART_SWITCH_ID
    coordinator.max_price_entity_id = ACTUAL_MAX_PRICE_ID
    coordinator.solar_enable_switch_entity_id = ACTUAL_SOLAR_SWITCH_ID
    coordinator.solar_buffer_entity_id = ACTUAL_SOLAR_BUFFER_ID
    coordinator.min_solar_charge_current_entity_id = ACTUAL_MIN_SOLAR_CURRENT_ID
    coordinator._internal_entities_resolved = (
        True  # Markera att ID:n är "manuellt lösta"
    )

    # Sätt grundläggande tillstånd för de FAKTISKA interna entiteterna
    # så att koordinatorn kan läsa dem korrekt.
    hass.states.async_set(
        ACTUAL_SMART_SWITCH_ID, STATE_ON
    )  # Smart laddning (Pris/Tid) PÅ som default
    hass.states.async_set(
        ACTUAL_SOLAR_SWITCH_ID, STATE_OFF
    )  # Solenergiladdning AV som default
    hass.states.async_set(ACTUAL_MAX_PRICE_ID, "1.00")  # Maxpris för Pris/Tid
    hass.states.async_set(ACTUAL_SOLAR_BUFFER_ID, "200")  # Solenergi buffert
    hass.states.async_set(
        ACTUAL_MIN_SOLAR_CURRENT_ID, "6"
    )  # Minsta ström för solenergi

    # Säkerställ att sensorn för aktivt styrningsläge har ett initialt värde.
    # Denna uppdateras normalt av koordinatorn efter första körningen.
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
        - Ingen laddning initieras (inga `easee.resume_charging` eller `easee.set_dynamic_current`-anrop).
        - Sensorn för aktivt styrningsläge visar `CONTROL_MODE_MANUAL` (AV).
        - En loggpost på DEBUG-nivå indikerar att anledningen till ingen laddning är att huvudströmbrytaren är AV.
    """
    coordinator = setup_coordinator

    # ARRANGE: Huvudströmbrytare AV, men Pris/Tid-villkor uppfyllda
    hass.states.async_set(MOCK_MAIN_POWER_SWITCH_ID, STATE_OFF)
    hass.states.async_set(
        MOCK_STATUS_SENSOR_ID,
        EASEE_STATUS_READY_TO_CHARGE[0],  # Laddaren är redo
    )
    hass.states.async_set(MOCK_PRICE_SENSOR_ID, "0.50")  # Lågt pris
    hass.states.async_set(MOCK_SCHEDULE_ID, STATE_ON)  # Schema aktivt

    # Mocka tjänsteanrop för att verifiera att de INTE anropas som de inte ska
    turn_on_calls = async_mock_service(hass, "homeassistant", SERVICE_TURN_ON)
    resume_calls = async_mock_service(hass, "easee", EASEE_SERVICE_RESUME_CHARGING)
    set_current_calls = async_mock_service(
        hass, "easee", EASEE_SERVICE_SET_DYNAMIC_CURRENT
    )

    # ACT: Kör en uppdatering av koordinatorn
    caplog.clear()  # Rensa tidigare loggar
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    # ASSERT: Verifiera att inga oönskade åtgärder har vidtagits
    assert len(turn_on_calls) == 0, "Försökte felaktigt slå PÅ huvudströmbrytaren."
    assert len(resume_calls) == 0, (
        "Laddning startades felaktigt trots att huvudströmbrytaren var AV."
    )
    assert len(set_current_calls) == 0, (
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

    # Verifiera att korrekt anledning loggades
    expected_log_message = "Huvudströmbrytare för laddbox är AV."
    # Detta meddelande sätts som `reason_for_action` och loggas i DEBUG-raden i slutet av _async_update_data
    assert expected_log_message in caplog.text, (
        f"Förväntad loggpost '{expected_log_message}' saknas. Caplog: {caplog.text}"
    )
    print("\nTest OK: Huvudströmbrytare AV förhindrade laddning som förväntat.")


async def test_manual_turn_off_main_switch_stops_charging(
    hass: HomeAssistant, setup_coordinator: SmartEVChargingCoordinator, caplog
):
    """
    Testar att en pågående smart laddning pausas korrekt om huvudströmbrytaren stängs av.

    SYFTE:
        Att verifiera att integrationen reagerar på en extern avstängning av
        huvudströmbrytaren genom att pausa laddningen och återställa sitt
        styrningsläge till manuellt.

    FÖRUTSÄTTNINGAR (Arrange):
        - Steg 1: En Pris/Tid-styrd laddningssession startas framgångsrikt.
            - Huvudströmbrytaren är PÅ.
            - Villkor för Pris/Tid-laddning är uppfyllda.
            - Laddarens status är initialt redo, sedan 'charging'.
        - Steg 2: Huvudströmbrytaren stängs AV manuellt (simuleras).

    UTFÖRANDE (Act):
        - Koordinatorn kör en uppdateringscykel (async_refresh) efter att strömbrytaren stängts av.

    FÖRVÄNTAT RESULTAT (Assert):
        - Laddningen pausas (tjänsten `easee.pause_charging` anropas).
        - Inga försök görs att återuppta laddning eller sätta ström.
        - Sensorn för aktivt styrningsläge visar `CONTROL_MODE_MANUAL` (AV).
        - En loggpost på DEBUG-nivå indikerar att anledningen är att huvudströmbrytaren är AV.
    """
    coordinator = setup_coordinator

    # ARRANGE - Steg 1: Starta en Pris/Tid-laddning
    hass.states.async_set(MOCK_MAIN_POWER_SWITCH_ID, STATE_ON)  # Huvudströmbrytare PÅ
    hass.states.async_set(
        MOCK_STATUS_SENSOR_ID,
        EASEE_STATUS_READY_TO_CHARGE[0],  # Laddare redo
    )
    hass.states.async_set(MOCK_PRICE_SENSOR_ID, "0.50")  # Lågt pris
    hass.states.async_set(MOCK_SCHEDULE_ID, STATE_ON)  # Schema aktivt

    # Mocka tjänster för initial start
    resume_calls = async_mock_service(hass, "easee", EASEE_SERVICE_RESUME_CHARGING)
    set_current_calls = async_mock_service(
        hass, "easee", EASEE_SERVICE_SET_DYNAMIC_CURRENT
    )
    # Pause-tjänsten behövs först senare, men mockas här för fullständighet
    pause_calls = async_mock_service(hass, "easee", EASEE_SERVICE_PAUSE_CHARGING)
    turn_on_calls = async_mock_service(
        hass, "homeassistant", SERVICE_TURN_ON
    )  # För att verifiera att den INTE anropas

    # Kör en första refresh för att initiera laddningen
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    # Verifiera att laddningen startade korrekt
    assert len(resume_calls) == 1, "Laddning startade inte initialt som förväntat."
    assert len(set_current_calls) == 1, "Laddström sattes inte initialt som förväntat."
    control_mode_state_initial = hass.states.get(ACTUAL_CONTROL_MODE_SENSOR_ID)
    assert control_mode_state_initial is not None, (
        f"Sensor {ACTUAL_CONTROL_MODE_SENSOR_ID} hittades inte initialt."
    )
    assert control_mode_state_initial.state == CONTROL_MODE_PRICE_TIME, (
        f"Styrningsläge var inte {CONTROL_MODE_PRICE_TIME} efter initial start."
    )

    # ARRANGE - Steg 2: Simulera att laddning pågår och huvudströmbrytaren stängs av
    hass.states.async_set(
        MOCK_STATUS_SENSOR_ID, EASEE_STATUS_CHARGING
    )  # Uppdatera status till att laddning nu pågår
    hass.states.async_set(
        MOCK_MAIN_POWER_SWITCH_ID, STATE_OFF
    )  # Användaren stänger AV huvudströmbrytaren

    # Rensa tidigare anropsräknare och loggar för att verifiera nya åtgärder
    resume_calls.clear()
    set_current_calls.clear()
    pause_calls.clear()
    turn_on_calls.clear()
    caplog.clear()

    # ACT: Koordinatorn reagerar på det nya tillståndet för huvudströmbrytaren
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    # ASSERT: Verifiera att laddningen har pausats och läget återställts
    assert len(pause_calls) == 1, (
        "Laddning pausades inte när huvudströmbrytaren stängdes av."
    )
    assert len(resume_calls) == 0, (
        "Försökte felaktigt återuppta laddning efter avstängning."
    )
    assert len(set_current_calls) == 0, (
        "Försökte felaktigt sätta ström efter avstängning."
    )
    assert len(turn_on_calls) == 0, "Försökte felaktigt slå PÅ huvudströmbrytaren."

    control_mode_state_final = hass.states.get(ACTUAL_CONTROL_MODE_SENSOR_ID)
    assert control_mode_state_final is not None, (
        f"Sensor {ACTUAL_CONTROL_MODE_SENSOR_ID} hittades inte efter avstängning."
    )
    assert control_mode_state_final.state == CONTROL_MODE_MANUAL, (
        f"Förväntade styrningsläge {CONTROL_MODE_MANUAL} efter avstängning, men fick {control_mode_state_final.state}."
    )

    expected_log_message = "Huvudströmbrytare för laddbox är AV."
    assert expected_log_message in caplog.text, (
        f"Förväntad loggpost '{expected_log_message}' saknas efter avstängning. Caplog: {caplog.text}"
    )
    print(
        "\nTest OK: Manuell avstängning av huvudströmbrytare stoppade laddning som förväntat."
    )
