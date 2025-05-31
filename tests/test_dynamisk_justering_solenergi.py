# tests/test_dynamisk_justering_solenergi.py
"""
Tester för dynamisk justering av laddström vid solenergiladdning.

Dessa tester verifierar att laddströmmen beräknas och justeras korrekt
baserat på tillgängligt solenergiöverskott, med hänsyn till husets
förbrukning och den inställda bufferten.
"""

import pytest
import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.const import STATE_ON, STATE_OFF

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)
from freezegun import freeze_time
from freezegun.api import FrozenDateTimeFactory

from custom_components.smart_ev_charging.const import (
    DOMAIN,
    CONF_CHARGER_DEVICE,
    CONF_STATUS_SENSOR,
    CONF_HOUSE_POWER_SENSOR,
    CONF_SOLAR_PRODUCTION_SENSOR,
    CONF_DEBUG_LOGGING,
    CONF_CHARGER_ENABLED_SWITCH_ID,  # <-- Importera konstanten
    EASEE_SERVICE_RESUME_CHARGING,
    EASEE_SERVICE_PAUSE_CHARGING,
    EASEE_SERVICE_SET_DYNAMIC_CURRENT,
    EASEE_STATUS_READY_TO_CHARGE,
    EASEE_STATUS_CHARGING,
    CONTROL_MODE_MANUAL,
    CONTROL_MODE_SOLAR_SURPLUS,
    SOLAR_SURPLUS_DELAY_SECONDS,
)
from custom_components.smart_ev_charging.coordinator import SmartEVChargingCoordinator

# Mockade externa entitets-ID:n
MOCK_CONFIG_ENTRY_ID = "test_dynamic_solar_entry"
MOCK_STATUS_SENSOR_ID = "sensor.test_charger_status_dynamic_solar"
MOCK_HOUSE_POWER_SENSOR_ID = "sensor.test_house_power_dynamic_solar"
MOCK_SOLAR_PRODUCTION_SENSOR_ID = "sensor.test_solar_prod_dynamic_solar"
MOCK_MAIN_POWER_SWITCH_SOLAR_ID = (
    "switch.mock_charger_power_dynamic_solar"  # <-- Nytt ID för testet
)

# Faktiska entitets-ID:n som Home Assistant skapar
ACTUAL_CONTROL_MODE_SENSOR_ID = "sensor.avancerad_elbilsladdning_aktivt_styrningslage"
ACTUAL_SMART_SWITCH_ID = "switch.avancerad_elbilsladdning_smart_laddning_aktiv"
ACTUAL_SOLAR_SWITCH_ID = "switch.avancerad_elbilsladdning_aktivera_solenergiladdning"
ACTUAL_MAX_PRICE_ID = "number.avancerad_elbilsladdning_max_elpris"  # Behövs för fullständig init av koordinator
ACTUAL_SOLAR_BUFFER_ID = "number.avancerad_elbilsladdning_solenergi_buffer"
ACTUAL_MIN_SOLAR_CURRENT_ID = (
    "number.avancerad_elbilsladdning_minsta_laddstrom_solenergi"
)


@pytest.fixture(autouse=True)
def enable_debug_logging_fixture():
    """Aktiverar DEBUG-loggning för komponenten under testkörningen."""
    logging.getLogger(f"custom_components.{DOMAIN}").setLevel(logging.DEBUG)


@pytest.fixture
async def setup_solar_charging_test(hass: HomeAssistant):
    """
    Fixture för att sätta upp koordinatorn med en konfiguration anpassad
    för att testa solenergiladdning.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_CHARGER_DEVICE: "mock_device_dynamic_solar",
            CONF_STATUS_SENSOR: MOCK_STATUS_SENSOR_ID,
            CONF_HOUSE_POWER_SENSOR: MOCK_HOUSE_POWER_SENSOR_ID,
            CONF_SOLAR_PRODUCTION_SENSOR: MOCK_SOLAR_PRODUCTION_SENSOR_ID,
            CONF_DEBUG_LOGGING: True,
            CONF_CHARGER_ENABLED_SWITCH_ID: MOCK_MAIN_POWER_SWITCH_SOLAR_ID,  # <-- Lägg till i config
        },
        entry_id=MOCK_CONFIG_ENTRY_ID,
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator: SmartEVChargingCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    assert coordinator is not None

    # Manuell tilldelning av de FAKTISKA interna entitets-ID:na
    coordinator.smart_enable_switch_entity_id = ACTUAL_SMART_SWITCH_ID
    coordinator.max_price_entity_id = (
        ACTUAL_MAX_PRICE_ID  # Viktigt för _resolve_internal_entities
    )
    coordinator.solar_enable_switch_entity_id = ACTUAL_SOLAR_SWITCH_ID
    coordinator.solar_buffer_entity_id = ACTUAL_SOLAR_BUFFER_ID
    coordinator.min_solar_charge_current_entity_id = ACTUAL_MIN_SOLAR_CURRENT_ID
    coordinator._internal_entities_resolved = True

    # Sätt grundläggande tillstånd för interna entiteter för att isolera solenergiladdning
    hass.states.async_set(ACTUAL_SMART_SWITCH_ID, STATE_OFF)
    hass.states.async_set(ACTUAL_SOLAR_SWITCH_ID, STATE_ON)
    hass.states.async_set(ACTUAL_MIN_SOLAR_CURRENT_ID, "6")
    hass.states.async_set(
        ACTUAL_MAX_PRICE_ID, "1.00"
    )  # Ge ett värde för fullständig init
    # ACTUAL_SOLAR_BUFFER_ID sätts i testfunktionen för tydlighetens skull

    # Sätt tillstånd för den mockade huvudströmbrytaren
    hass.states.async_set(
        MOCK_MAIN_POWER_SWITCH_SOLAR_ID, STATE_ON
    )  # <-- Se till att den är PÅ

    hass.states.async_set(ACTUAL_CONTROL_MODE_SENSOR_ID, CONTROL_MODE_MANUAL)

    return coordinator


async def test_dynamic_current_adjustment_for_solar_charging(
    hass: HomeAssistant,
    setup_solar_charging_test: SmartEVChargingCoordinator,
    freezer: FrozenDateTimeFactory,
):
    """
    Testar att laddströmmen justeras dynamiskt baserat på solöverskott.

    SYFTE:
        Att verifiera den matematiska beräkningen av tillgänglig laddström från
        solenergi och att koordinatorn korrekt justerar laddarens dynamiska
        strömgräns när förutsättningarna (husets förbrukning) ändras.

    FÖRUTSÄTTNINGAR (Arrange):
        - Steg 1: Ett stort solöverskott skapas.
            - Solproduktion: 7000 W
            - Husförbrukning: 500 W
            - Buffert: 500 W (inställt i testet via ACTUAL_SOLAR_BUFFER_ID)
            - Förväntat överskott för laddning: 7000-500-500 = 6000 W.
            - Förväntad ström: floor(6000W / 690) = 8 A.
        - Steg 2: Husets förbrukning ökar, vilket minskar överskottet.
            - Solproduktion: 7000 W (samma)
            - Husförbrukning: 1500 W (ökat)
            - Buffert: 500 W (samma)
            - Förväntat överskott för laddning: 7000-1500-500 = 5000 W.
            - Förväntad ström: floor(5000W / 690) = 7 A.

    UTFÖRANDE (Act):
        - Steg 1: Koordinatorn körs för att upptäcka överskott, tiden flyttas fram
          förbi fördröjningen, och koordinatorn körs igen för att starta laddning.
        - Steg 2: Husets förbrukning uppdateras och koordinatorn körs igen.

    FÖRVÄNTAT RESULTAT (Assert):
        - Steg 1: Laddningen startar och `set_dynamic_current` anropas med 8A.
        - Steg 2: Laddningen fortsätter och `set_dynamic_current` anropas med 7A.
    """
    coordinator = setup_solar_charging_test

    # Mocka tjänsteanrop
    resume_calls = async_mock_service(hass, "easee", EASEE_SERVICE_RESUME_CHARGING)
    set_current_calls = async_mock_service(
        hass, "easee", EASEE_SERVICE_SET_DYNAMIC_CURRENT
    )

    # --- ARRANGE & ACT - Steg 1: Högt överskott ---
    # Sätt initiala värden
    hass.states.async_set(MOCK_SOLAR_PRODUCTION_SENSOR_ID, "7000")  # 7 kW
    hass.states.async_set(MOCK_HOUSE_POWER_SENSOR_ID, "500")
    hass.states.async_set(ACTUAL_SOLAR_BUFFER_ID, "500")  # 500W buffert
    hass.states.async_set(MOCK_STATUS_SENSOR_ID, EASEE_STATUS_READY_TO_CHARGE[0])

    # Kör en första refresh för att detektera överskott och starta fördröjningstimern
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    # Verifiera att ingen laddning har startat än (väntar på fördröjning)
    assert len(resume_calls) == 0
    assert len(set_current_calls) == 0

    # Flytta fram klockan förbi fördröjningen
    # Not: Freezer.tick() flyttar fram tiden och kör eventuella timers som schemalagts inom den tiden.
    # Koordinatorns _async_update_data körs inte automatiskt av detta i detta fall,
    # så vi behöver en till async_refresh() efteråt.
    freezer.tick(timedelta(seconds=SOLAR_SURPLUS_DELAY_SECONDS))

    # Kör en andra refresh för att starta laddningen
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    # --- ASSERT - Steg 1 ---
    # Verifiera att laddningen nu har startat med korrekt ström (8A)
    assert len(resume_calls) == 1, "Laddning återupptogs inte efter fördröjningen."
    assert len(set_current_calls) == 1, "Ström sattes inte efter fördröjningen."

    # Kontrollera att rätt strömvärde skickades i set_current-anropet
    set_current_call = set_current_calls[0]
    assert set_current_call.data.get("currentP1") == 8.0
    assert set_current_call.data.get("currentP2") == 8.0
    assert set_current_call.data.get("currentP3") == 8.0

    # Verifiera styrningsläget
    control_mode_state = hass.states.get(ACTUAL_CONTROL_MODE_SENSOR_ID)
    assert control_mode_state is not None
    assert control_mode_state.state == CONTROL_MODE_SOLAR_SURPLUS
    print("\nTest OK (Steg 1): Solenergiladdning startad med 8A.")

    # --- ARRANGE & ACT - Steg 2: Minskat överskott ---
    # Rensa mock-anrop för att förbereda nästa verifiering
    resume_calls.clear()
    set_current_calls.clear()

    # Simulera att husets förbrukning ökar och att laddning nu pågår
    hass.states.async_set(MOCK_HOUSE_POWER_SENSOR_ID, "1500")  # Förbrukning ökar
    hass.states.async_set(
        MOCK_STATUS_SENSOR_ID, EASEE_STATUS_CHARGING
    )  # Laddning pågår

    # Kör en refresh för att justera laddströmmen
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    # --- ASSERT - Steg 2 ---
    # Verifiera att laddningen INTE återupptogs igen (den pågick redan)
    assert len(resume_calls) == 0, "Laddning återupptogs felaktigt igen."

    # Verifiera att strömmen justerades
    assert len(set_current_calls) == 1, (
        "Strömmen justerades inte när förbrukningen ändrades."
    )

    # Kontrollera att det nya, lägre strömvärdet (7A) skickades
    set_current_call_2 = set_current_calls[0]
    assert set_current_call_2.data.get("currentP1") == 7.0
    assert set_current_call_2.data.get("currentP2") == 7.0
    assert set_current_call_2.data.get("currentP3") == 7.0

    # Verifiera att styrningsläget fortfarande är solenergi
    control_mode_state_2 = hass.states.get(ACTUAL_CONTROL_MODE_SENSOR_ID)
    assert control_mode_state_2 is not None
    assert control_mode_state_2.state == CONTROL_MODE_SOLAR_SURPLUS
    print("Test OK (Steg 2): Laddströmmen justerades korrekt till 7A.")
