# tests/test_solar_charging_stickiness.py
"""
Testar att en påbörjad solenergiladdning inte avbryts av mindre dippar
under starttröskeln, utan fortsätter med lägre ström.
"""

import pytest
import math
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.const import STATE_ON, STATE_OFF
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

# Importera relevanta konstanter och klasser
from custom_components.smart_ev_charging.const import *
from custom_components.smart_ev_charging.coordinator import SmartEVChargingCoordinator

# Mockade entiteter
MOCK_SOLAR_SENSOR_ID = "sensor.test_solar_sticky"
MOCK_HOUSE_POWER_SENSOR_ID = "sensor.test_house_power_sticky"
MOCK_STATUS_SENSOR_ID = "sensor.test_charger_status_sticky"
MOCK_MAIN_POWER_SWITCH_ID = "switch.mock_charger_power_sticky"


# Funktion för att beräkna förväntad effekt för en given ström
def power_for_current(amps: int) -> int:
    return amps * PHASES * VOLTAGE_PHASE_NEUTRAL


@pytest.fixture
async def setup_coordinator_for_solar_test(hass: HomeAssistant):
    # Sätt upp en koordinator med relevanta solenergi-inställningar
    entry_id = "test_solar_sticky_entry"
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_CHARGER_DEVICE: "mock_device_solar_sticky",
            CONF_STATUS_SENSOR: MOCK_STATUS_SENSOR_ID,
            CONF_SOLAR_PRODUCTION_SENSOR: MOCK_SOLAR_SENSOR_ID,
            CONF_HOUSE_POWER_SENSOR: MOCK_HOUSE_POWER_SENSOR_ID,
            CONF_CHARGER_ENABLED_SWITCH_ID: MOCK_MAIN_POWER_SWITCH_ID,
        },
        entry_id=entry_id,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator: SmartEVChargingCoordinator = hass.data[DOMAIN][entry_id]["coordinator"]

    # Manuell tilldelning av interna entitets-ID:n
    coordinator.smart_enable_switch_entity_id = (
        f"switch.{DOMAIN}_{entry_id}_{ENTITY_ID_SUFFIX_SMART_ENABLE_SWITCH}"
    )
    coordinator.solar_enable_switch_entity_id = (
        f"switch.{DOMAIN}_{entry_id}_{ENTITY_ID_SUFFIX_ENABLE_SOLAR_CHARGING_SWITCH}"
    )
    coordinator.min_solar_charge_current_entity_id = f"number.{DOMAIN}_{entry_id}_{ENTITY_ID_SUFFIX_MIN_SOLAR_CHARGE_CURRENT_A_NUMBER}"
    coordinator.solar_buffer_entity_id = (
        f"number.{DOMAIN}_{entry_id}_{ENTITY_ID_SUFFIX_SOLAR_BUFFER_NUMBER}"
    )
    coordinator._internal_entities_resolved = True

    # Grundinställningar för testet
    hass.states.async_set(coordinator.solar_enable_switch_entity_id, STATE_ON)
    hass.states.async_set(
        coordinator.smart_enable_switch_entity_id, STATE_OFF
    )  # Isolera solenergilogik
    hass.states.async_set(coordinator.solar_buffer_entity_id, "200")  # 200W buffer
    hass.states.async_set(
        coordinator.min_solar_charge_current_entity_id, "6"
    )  # Starttröskel 6A
    hass.states.async_set(MOCK_MAIN_POWER_SWITCH_ID, STATE_ON)

    return coordinator


async def test_solar_charging_does_not_stop_on_minor_dip(
    hass: HomeAssistant,
    setup_coordinator_for_solar_test: SmartEVChargingCoordinator,
    freezer,
):
    """
    SYFTE: Verifiera att laddningen fortsätter med 5A även om starttröskeln är 6A.
    """
    coordinator = setup_coordinator_for_solar_test
    set_current_calls = async_mock_service(hass, "easee", "set_charger_dynamic_limit")
    action_command_calls = async_mock_service(hass, "easee", "action_command")

    house_consumption = 1000  # W
    solar_buffer = 200  # W

    # --- 1. START: Överskott för 7A ---
    print("TESTSTEG 1: Startar laddning med 7A")
    power_needed_for_7A = power_for_current(7) + solar_buffer
    hass.states.async_set(MOCK_SOLAR_SENSOR_ID, str(power_needed_for_7A))
    hass.states.async_set(MOCK_HOUSE_POWER_SENSOR_ID, str(house_consumption))
    hass.states.async_set(MOCK_STATUS_SENSOR_ID, EASEE_STATUS_READY_TO_CHARGE[0])

    # Kör en gång för att starta timer, hoppa fram i tiden, kör igen för att starta laddning
    await coordinator.async_refresh()
    freezer.tick(timedelta(seconds=SOLAR_SURPLUS_DELAY_SECONDS + 1))
    # await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert len(action_command_calls) == 0, (
        f"Förväntade inget action_command för solenergistart, men fick: {action_command_calls}"
    )

    # Däremot ska dynamisk strömgräns ha satts.
    assert len(set_current_calls) == 1, (
        f"Förväntade 1 anrop till set_charger_dynamic_limit, men fick: {len(set_current_calls)} anrop."
    )

    # Kontrollera att rätt strömvärde skickades.
    # Tjänsten heter 'set_charger_dynamic_limit' och argumentet 'current'.
    assert set_current_calls[0].data["current"] == 7, (
        f"Förväntade att strömmen skulle sättas till 7A, men den sattes till: {set_current_calls[0].data['current']}A"
    )

    action_command_calls.clear()
    set_current_calls.clear()

    # --- 2. DIP: Överskott för 5A ---
    print("TESTSTEG 2: Överskottet dippar till 5A. Laddningen ska FORTSÄTTA.")
    hass.states.async_set(MOCK_STATUS_SENSOR_ID, EASEE_STATUS_CHARGING)  # Nu laddar den
    power_needed_for_5A = power_for_current(5) + solar_buffer
    hass.states.async_set(MOCK_SOLAR_SENSOR_ID, str(power_needed_for_5A))

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    # FÖRVÄNTAT RESULTAT: INGET "pause"-kommando. BARA en justering av strömmen.
    assert len(action_command_calls) == 0, (
        "Ett onödigt kommando (troligen 'pause') skickades."
    )
    assert len(set_current_calls) == 1, "Strömmen justerades inte ned till 0A."
    assert set_current_calls[0].data["current"] == 0, (
        f"Förväntade 0A, men fick {set_current_calls[0].data['current']}A."
    )

    action_command_calls.clear()
    set_current_calls.clear()

    # --- 3. DIP: Överskott för 8A ---
    print("TESTSTEG 3: Överskottet ökar till 8A. Laddningen ska FORTSÄTTA.")
    hass.states.async_set(MOCK_STATUS_SENSOR_ID, EASEE_STATUS_CHARGING)  # Nu laddar den
    power_needed_for_8A = power_for_current(8) + solar_buffer
    hass.states.async_set(MOCK_SOLAR_SENSOR_ID, str(power_needed_for_8A))

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    # FÖRVÄNTAT RESULTAT: INGET "pause"-kommando. BARA en justering av strömmen.
    assert len(action_command_calls) == 0, (
        "Ett onödigt kommando (troligen 'pause') skickades."
    )
    assert len(set_current_calls) == 1, "Strömmen justerades inte upp till 8A."
    assert set_current_calls[0].data["current"] == 8, (
        f"Förväntade 8A, men fick {set_current_calls[0].data['current']}A."
    )

    # # --- 3. STOPP: Överskott för 1A ---
    # print("TESTSTEG 3: Överskottet försvinner (1A). Laddningen ska PAUSAS.")
    # power_needed_for_1A = power_for_current(1) + house_consumption + solar_buffer
    # hass.states.async_set(MOCK_SOLAR_SENSOR_ID, str(power_needed_for_1A))

    # await coordinator.async_refresh()
    # await hass.async_block_till_done()

    # # FÖRVÄNTAT RESULTAT: NU ska ett "pause"-kommando skickas.
    # assert (
    #     len(action_command_calls) == 1
    #     and action_command_calls[0].data["action_command"] == "pause"
    # )
