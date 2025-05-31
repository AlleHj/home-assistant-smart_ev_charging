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
import math  # Importera math för math.floor

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
    CONTROL_MODE_MANUAL,
    CONTROL_MODE_SOLAR_SURPLUS,
    SOLAR_SURPLUS_DELAY_SECONDS,
    MIN_CHARGE_CURRENT_A,
    ENTITY_ID_SUFFIX_SMART_ENABLE_SWITCH,
    ENTITY_ID_SUFFIX_MAX_PRICE_NUMBER,
    ENTITY_ID_SUFFIX_ENABLE_SOLAR_CHARGING_SWITCH,
    ENTITY_ID_SUFFIX_SOLAR_BUFFER_NUMBER,
    ENTITY_ID_SUFFIX_MIN_SOLAR_CHARGE_CURRENT_A_NUMBER,
    PHASES,
    VOLTAGE_PHASE_NEUTRAL,
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

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator: SmartEVChargingCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    assert coordinator is not None

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

    resume_calls = async_mock_service(hass, "easee", "resume_charging")
    pause_calls = async_mock_service(hass, "easee", "pause_charging")
    set_current_calls = async_mock_service(
        hass, "easee", "set_dynamic_charger_circuit_current"
    )

    hass.states.async_set(coordinator.solar_enable_switch_entity_id, STATE_ON)
    hass.states.async_set(coordinator.smart_enable_switch_entity_id, STATE_OFF)
    hass.states.async_set(MOCK_STATUS_SENSOR_ID, EASEE_STATUS_READY_TO_CHARGE)
    hass.states.async_set(MOCK_MAIN_POWER_SWITCH_ID, STATE_ON)
    hass.states.async_set(coordinator.min_solar_charge_current_entity_id, "6")
    hass.states.async_set(coordinator.solar_buffer_entity_id, "200")
    hass.states.async_set(coordinator.max_price_entity_id, "10.0")

    # --- 2. Teststeg: Inget överskott ---
    print("\nTESTSTEG: Inget överskott")
    hass.states.async_set(
        MOCK_SOLAR_SENSOR_ID, "500", {"unit_of_measurement": UnitOfPower.WATT}
    )
    hass.states.async_set(
        MOCK_HOUSE_POWER_SENSOR_ID, "1000", {"unit_of_measurement": UnitOfPower.WATT}
    )
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert len(resume_calls) == 0
    assert hass.states.get(CONTROL_MODE_SENSOR_ID).state == CONTROL_MODE_MANUAL

    # --- 3. Teststeg: Otillräckligt överskott ---
    print("\nTESTSTEG: Otillräckligt överskott")
    min_solar_current_amps = 6
    power_for_min_current = min_solar_current_amps * PHASES * VOLTAGE_PHASE_NEUTRAL

    production_for_insufficient = (power_for_min_current - 10) + 1000 + 200

    hass.states.async_set(
        MOCK_SOLAR_SENSOR_ID,
        str(production_for_insufficient),
        {"unit_of_measurement": UnitOfPower.WATT},
    )
    hass.states.async_set(
        MOCK_HOUSE_POWER_SENSOR_ID, "1000", {"unit_of_measurement": UnitOfPower.WATT}
    )
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert len(resume_calls) == 0
    assert hass.states.get(CONTROL_MODE_SENSOR_ID).state == CONTROL_MODE_MANUAL

    # --- 4. Teststeg: Tillräckligt överskott (inom fördröjning) ---
    print("\nTESTSTEG: Tillräckligt överskott (inom fördröjning)")
    current_target_amps_delay = 7
    production_for_delay = (
        (current_target_amps_delay * PHASES * VOLTAGE_PHASE_NEUTRAL) + 1000 + 200
    )
    hass.states.async_set(
        MOCK_SOLAR_SENSOR_ID,
        str(production_for_delay),
        {"unit_of_measurement": UnitOfPower.WATT},
    )
    hass.states.async_set(
        MOCK_HOUSE_POWER_SENSOR_ID, "1000", {"unit_of_measurement": UnitOfPower.WATT}
    )

    coordinator._solar_surplus_start_time = None
    coordinator._solar_session_active = False

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert len(resume_calls) == 0
    assert coordinator._solar_surplus_start_time is not None
    assert hass.states.get(CONTROL_MODE_SENSOR_ID).state == CONTROL_MODE_MANUAL

    # --- 5. Teststeg: Laddning Startar efter fördröjning ---
    print("\nTESTSTEG: Laddning startar efter fördröjning")
    freezer.tick(timedelta(seconds=SOLAR_SURPLUS_DELAY_SECONDS + 1))
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert len(resume_calls) == 1, "Laddning startade inte efter fördröjningen."
    assert hass.states.get(CONTROL_MODE_SENSOR_ID).state == CONTROL_MODE_SOLAR_SURPLUS

    assert len(set_current_calls) == 1, (
        "set_dynamic_current anropades inte korrekt vid start."
    )
    assert set_current_calls[0].data["currentP1"] == current_target_amps_delay
    assert set_current_calls[0].data["currentP2"] == current_target_amps_delay
    assert set_current_calls[0].data["currentP3"] == current_target_amps_delay

    # --- 6. Teststeg: Laddströmmen justeras dynamiskt ---
    print("\nTESTSTEG: Laddströmmen justeras dynamiskt")
    current_target_amps_adjust = 10
    production_for_adjust = (
        (current_target_amps_adjust * PHASES * VOLTAGE_PHASE_NEUTRAL) + 1000 + 200
    )
    hass.states.async_set(
        MOCK_SOLAR_SENSOR_ID,
        str(production_for_adjust),
        {"unit_of_measurement": UnitOfPower.WATT},
    )
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert len(set_current_calls) == 2, (
        "set_dynamic_current anropades inte vid justering."
    )
    assert set_current_calls[1].data["currentP1"] == current_target_amps_adjust

    # --- 7. Teststeg: Laddning pausas när överskottet försvinner ---
    print("\nTESTSTEG: Laddning pausas")
    hass.states.async_set(
        MOCK_SOLAR_SENSOR_ID, "1500", {"unit_of_measurement": UnitOfPower.WATT}
    )
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert len(pause_calls) == 1, "Laddning pausades inte."
    assert hass.states.get(CONTROL_MODE_SENSOR_ID).state == CONTROL_MODE_MANUAL
    assert coordinator._solar_surplus_start_time is None
    assert coordinator._solar_session_active is False

    print("\nTestet slutfört framgångsrikt!")
