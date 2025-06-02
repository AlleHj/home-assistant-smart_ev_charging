#
# tests/test_coordinator.py
#
"""Testfil för grundläggande funktioner i SmartEVChargingCoordinator."""

from datetime import timedelta, datetime, timezone
import pytest
import logging
import random
from unittest.mock import patch
from typing import Set

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    async_mock_service,
)

from homeassistant.core import HomeAssistant
from homeassistant.const import STATE_ON, STATE_OFF, STATE_UNAVAILABLE
import homeassistant.util.dt as dt_util
from freezegun.api import FrozenDateTimeFactory

from custom_components.smart_ev_charging.const import (
    DOMAIN,
    CONF_CHARGER_DEVICE,
    CONF_STATUS_SENSOR,
    CONF_CHARGER_ENABLED_SWITCH_ID,
    CONF_PRICE_SENSOR,
    CONF_TIME_SCHEDULE_ENTITY,
    CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR,
    CONF_CHARGER_DYNAMIC_CURRENT_SENSOR,
    CONF_DEBUG_LOGGING,
    CONF_EV_SOC_SENSOR,
    CONF_TARGET_SOC_LIMIT,
    EASEE_STATUS_AWAITING_START,
    EASEE_STATUS_CHARGING,
    EASEE_STATUS_PAUSED,
    EASEE_STATUS_READY_TO_CHARGE,
    EASEE_SERVICE_SET_DYNAMIC_CURRENT,
    # REASON_SOC_LIMIT_REACHED, # Borttagen, används som sträng
    ENTITY_ID_SUFFIX_SMART_ENABLE_SWITCH,
    ENTITY_ID_SUFFIX_MAX_PRICE_NUMBER,
    ENTITY_ID_SUFFIX_ENABLE_SOLAR_CHARGING_SWITCH,
    ENTITY_ID_SUFFIX_SOLAR_BUFFER_NUMBER,
    ENTITY_ID_SUFFIX_MIN_SOLAR_CHARGE_CURRENT_A_NUMBER,
)
from custom_components.smart_ev_charging.coordinator import SmartEVChargingCoordinator

# Lokalt definierade mock-konstanter för denna fil
MOCK_PRICE_SENSOR_ID = "sensor.test_price_coordinator"
MOCK_SCHEDULE_ID = "schedule.test_charging_schedule_coordinator"
MOCK_STATUS_SENSOR_ID = "sensor.test_charger_status_coordinator"
MOCK_MAIN_POWER_SWITCH_ID = "switch.mock_charger_power_coordinator"
MOCK_SOC_SENSOR_ID = "sensor.test_ev_soc_coordinator"
MOCK_SOC_LIMIT_INPUT_NUMBER_ID = "input_number.test_soc_limit_coordinator"


@pytest.fixture
async def setup_coordinator(hass: HomeAssistant):
    """Grundläggande setup för koordinator-tester."""
    entry_id = "test_coordinator_fixture_1"
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_CHARGER_DEVICE: "easee_123_coord_test",
            CONF_STATUS_SENSOR: MOCK_STATUS_SENSOR_ID,
            CONF_CHARGER_ENABLED_SWITCH_ID: MOCK_MAIN_POWER_SWITCH_ID,
            CONF_PRICE_SENSOR: MOCK_PRICE_SENSOR_ID,
            CONF_TIME_SCHEDULE_ENTITY: MOCK_SCHEDULE_ID,
            CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR: "sensor.charger_max_current_coord_test",
            CONF_CHARGER_DYNAMIC_CURRENT_SENSOR: "sensor.dynamic_current_coord_test",
            CONF_DEBUG_LOGGING: True,
        },
        entry_id=entry_id,
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    coordinator.smart_enable_switch_entity_id = (
        f"switch.{DOMAIN}_{entry_id}_{ENTITY_ID_SUFFIX_SMART_ENABLE_SWITCH}"
    )
    coordinator.max_price_entity_id = (
        f"number.{DOMAIN}_{entry_id}_{ENTITY_ID_SUFFIX_MAX_PRICE_NUMBER}"
    )
    coordinator.solar_enable_switch_entity_id = (
        f"switch.{DOMAIN}_{entry_id}_{ENTITY_ID_SUFFIX_ENABLE_SOLAR_CHARGING_SWITCH}"
    )
    coordinator.solar_buffer_entity_id = (
        f"number.{DOMAIN}_{entry_id}_{ENTITY_ID_SUFFIX_SOLAR_BUFFER_NUMBER}"
    )
    coordinator.min_solar_charge_current_entity_id = f"number.{DOMAIN}_{entry_id}_{ENTITY_ID_SUFFIX_MIN_SOLAR_CHARGE_CURRENT_A_NUMBER}"
    coordinator._internal_entities_resolved = True

    hass.states.async_set(coordinator.smart_enable_switch_entity_id, STATE_ON)
    hass.states.async_set(coordinator.max_price_entity_id, "1.0")
    hass.states.async_set(coordinator.solar_enable_switch_entity_id, STATE_OFF)
    hass.states.async_set("sensor.charger_max_current_coord_test", "16")
    return coordinator


@pytest.fixture
async def setup_coordinator_with_soc(hass: HomeAssistant):
    """Setup för koordinator-tester som inkluderar SoC-hantering."""
    entry_id = "test_coordinator_fixture_soc"
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_CHARGER_DEVICE: "easee_456_soc_test",
            CONF_STATUS_SENSOR: MOCK_STATUS_SENSOR_ID,
            CONF_CHARGER_ENABLED_SWITCH_ID: MOCK_MAIN_POWER_SWITCH_ID,
            CONF_PRICE_SENSOR: MOCK_PRICE_SENSOR_ID,
            CONF_TIME_SCHEDULE_ENTITY: MOCK_SCHEDULE_ID,
            CONF_EV_SOC_SENSOR: MOCK_SOC_SENSOR_ID,
            CONF_TARGET_SOC_LIMIT: 80.0,
            CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR: "sensor.charger_max_current_soc_test",
            CONF_CHARGER_DYNAMIC_CURRENT_SENSOR: "sensor.dynamic_current_soc_test",
            CONF_DEBUG_LOGGING: True,
        },
        entry_id=entry_id,
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    coordinator.smart_enable_switch_entity_id = (
        f"switch.{DOMAIN}_{entry_id}_{ENTITY_ID_SUFFIX_SMART_ENABLE_SWITCH}"
    )
    coordinator.max_price_entity_id = (
        f"number.{DOMAIN}_{entry_id}_{ENTITY_ID_SUFFIX_MAX_PRICE_NUMBER}"
    )
    coordinator.solar_enable_switch_entity_id = (
        f"switch.{DOMAIN}_{entry_id}_{ENTITY_ID_SUFFIX_ENABLE_SOLAR_CHARGING_SWITCH}"
    )
    coordinator.solar_buffer_entity_id = (
        f"number.{DOMAIN}_{entry_id}_{ENTITY_ID_SUFFIX_SOLAR_BUFFER_NUMBER}"
    )
    coordinator.min_solar_charge_current_entity_id = f"number.{DOMAIN}_{entry_id}_{ENTITY_ID_SUFFIX_MIN_SOLAR_CHARGE_CURRENT_A_NUMBER}"
    coordinator._internal_entities_resolved = True

    hass.states.async_set(coordinator.smart_enable_switch_entity_id, STATE_ON)
    hass.states.async_set(
        coordinator.max_price_entity_id, "1.0"
    )  # Maxpris satt i fixturen
    hass.states.async_set(coordinator.solar_enable_switch_entity_id, STATE_OFF)
    hass.states.async_set("sensor.charger_max_current_soc_test", "16")
    return coordinator


@pytest.mark.asyncio
async def test_price_time_charging_starts_when_conditions_are_met(
    hass: HomeAssistant, setup_coordinator: SmartEVChargingCoordinator
):
    """Testar att laddning startar när pris och tidsschema är uppfyllda."""
    coordinator = setup_coordinator

    action_command_calls = async_mock_service(hass, "easee", "action_command")
    set_charger_dynamic_limit_calls = async_mock_service(
        hass, "easee", "set_charger_dynamic_limit"
    )

    hass.states.async_set(MOCK_PRICE_SENSOR_ID, "0.5")
    hass.states.async_set(MOCK_SCHEDULE_ID, STATE_ON)
    hass.states.async_set(MOCK_STATUS_SENSOR_ID, EASEE_STATUS_AWAITING_START)
    hass.states.async_set(MOCK_MAIN_POWER_SWITCH_ID, STATE_ON)

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert len(action_command_calls) == 1, (
        "Tjänsten för att starta laddning anropades inte."
    )
    assert action_command_calls[0].data["action_command"] == "start"
    assert len(set_charger_dynamic_limit_calls) == 1, (
        "Tjänsten för att sätta ström anropades inte."
    )


@pytest.mark.asyncio
async def test_charging_stops_when_price_is_too_high(
    hass: HomeAssistant, setup_coordinator: SmartEVChargingCoordinator
):
    """Testar att laddning stoppas när elpriset överstiger maxgränsen."""
    coordinator = setup_coordinator
    action_command_calls = async_mock_service(hass, "easee", "action_command")
    set_charger_dynamic_limit_calls = async_mock_service(
        hass, "easee", "set_charger_dynamic_limit"
    )

    hass.states.async_set(MOCK_PRICE_SENSOR_ID, "0.5")
    hass.states.async_set(MOCK_SCHEDULE_ID, STATE_ON)
    hass.states.async_set(MOCK_STATUS_SENSOR_ID, EASEE_STATUS_AWAITING_START)
    hass.states.async_set(MOCK_MAIN_POWER_SWITCH_ID, STATE_ON)

    await coordinator.async_refresh()
    await hass.async_block_till_done()
    hass.states.async_set(MOCK_STATUS_SENSOR_ID, EASEE_STATUS_CHARGING)

    assert len(action_command_calls) == 1
    assert action_command_calls[0].data["action_command"] == "start"
    assert len(set_charger_dynamic_limit_calls) == 1

    action_command_calls.clear()
    set_charger_dynamic_limit_calls.clear()

    hass.states.async_set(
        MOCK_PRICE_SENSOR_ID, "2.0"
    )  # Pris över maxgräns (1.0 från fixture)

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert len(action_command_calls) == 1, (
        "Tjänsten för att pausa laddning anropades inte eller fel antal gånger."
    )
    assert action_command_calls[0].data["action_command"] == "pause"
    assert len(set_charger_dynamic_limit_calls) == 0


@pytest.mark.asyncio
async def test_charging_stops_when_schedule_is_off(
    hass: HomeAssistant, setup_coordinator: SmartEVChargingCoordinator
):
    """Testar att laddning stoppas när tidsschemat stängs av."""
    coordinator = setup_coordinator
    action_command_calls = async_mock_service(hass, "easee", "action_command")
    set_charger_dynamic_limit_calls = async_mock_service(
        hass, "easee", "set_charger_dynamic_limit"
    )

    hass.states.async_set(MOCK_PRICE_SENSOR_ID, "0.5")
    hass.states.async_set(MOCK_SCHEDULE_ID, STATE_ON)
    hass.states.async_set(MOCK_STATUS_SENSOR_ID, EASEE_STATUS_AWAITING_START)
    hass.states.async_set(MOCK_MAIN_POWER_SWITCH_ID, STATE_ON)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    hass.states.async_set(MOCK_STATUS_SENSOR_ID, EASEE_STATUS_CHARGING)
    assert len(action_command_calls) == 1
    assert action_command_calls[0].data["action_command"] == "start"
    assert len(set_charger_dynamic_limit_calls) == 1

    action_command_calls.clear()
    set_charger_dynamic_limit_calls.clear()

    hass.states.async_set(MOCK_SCHEDULE_ID, STATE_OFF)

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert len(action_command_calls) == 1
    assert action_command_calls[0].data["action_command"] == "pause"
    assert len(set_charger_dynamic_limit_calls) == 0


@pytest.mark.asyncio
async def test_charging_stops_when_soc_limit_is_reached(
    hass: HomeAssistant, setup_coordinator_with_soc: SmartEVChargingCoordinator
):
    """Testar att laddning stoppas när SOC-gränsen uppnås."""
    coordinator = setup_coordinator_with_soc
    action_command_calls = async_mock_service(hass, "easee", "action_command")

    set_charger_dynamic_limit_calls = async_mock_service(
        hass, "easee", "set_charger_dynamic_limit"
    )

    # ARRANGE - Steg 1: Starta laddning, SOC är under gränsen
    hass.states.async_set(MOCK_PRICE_SENSOR_ID, "0.5")  # Lågt pris
    hass.states.async_set(
        MOCK_SCHEDULE_ID, STATE_ON
    )  # Schema PÅ (från fixturens config, men vi sätter här för tydlighet)
    hass.states.async_set(MOCK_MAIN_POWER_SWITCH_ID, STATE_ON)
    hass.states.async_set(MOCK_STATUS_SENSOR_ID, EASEE_STATUS_AWAITING_START)
    hass.states.async_set(
        MOCK_SOC_SENSOR_ID, "70.0"
    )  # SoC under gränsen (80.0 från fixture)

    await coordinator.async_refresh()
    await hass.async_block_till_done()
    hass.states.async_set(MOCK_STATUS_SENSOR_ID, EASEE_STATUS_CHARGING)

    assert len(action_command_calls) == 1
    assert action_command_calls[0].data["action_command"] == "start"
    assert len(set_charger_dynamic_limit_calls) == 1

    # Förväntad anledning när laddning startar (baserat på Pris/Tid)
    # Antag att surcharge är 0 och max_price är 1.0 från fixturen
    # Priset är 0.5, schemat är PÅ.
    expected_initial_reason = (
        "Pris/Tid-laddning aktiv (Pris: 0.50 <= 1.00 kr, Tidsschema PÅ)."
    )
    actual_initial_reason = coordinator.data.get("should_charge_reason", "")
    assert actual_initial_reason == expected_initial_reason, (
        f"Förväntad anledning '{expected_initial_reason}', fick '{actual_initial_reason}'"
    )

    # Rensa anrop för nästa steg
    action_command_calls.clear()
    set_charger_dynamic_limit_calls.clear()

    # ARRANGE - Steg 2: SOC når gränsen
    hass.states.async_set(MOCK_SOC_SENSOR_ID, "81.0")

    # ACT
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    # ASSERT
    assert len(action_command_calls) == 1, (
        "Paus-tjänsten anropades inte eller fel antal gånger när SOC-gränsen nåddes."
    )
    assert action_command_calls[0].data["action_command"] == "pause"
    assert (
        len(set_charger_dynamic_limit_calls) == 0
    )  # Ska inte försöka sätta ström när den pausar pga SoC

    expected_soc_reason = "SoC (81.0%) har nått målet (80.0%)."  # Baserat på fixturens CONF_TARGET_SOC_LIMIT = 80.0
    actual_soc_reason = coordinator.data.get("should_charge_reason", "")
    assert actual_soc_reason == expected_soc_reason, (
        f"Förväntad SoC-anledning '{expected_soc_reason}', fick '{actual_soc_reason}'"
    )


@pytest.mark.asyncio
async def test_full_day_price_time_simulation(
    hass: HomeAssistant,
    setup_coordinator: SmartEVChargingCoordinator,
    freezer: FrozenDateTimeFactory,
):
    """Simulerar en hel dag och verifierar att laddningen startar och stoppar vid rätt tidpunkter baserat på pris och schema."""
    coordinator = setup_coordinator
    action_command_calls = async_mock_service(hass, "easee", "action_command")

    set_charger_dynamic_limit_calls = async_mock_service(
        hass, "easee", "set_charger_dynamic_limit"
    )

    prices = [2.0] * 3 + [0.5] * 3 + [2.0] * 2 + [2.0] * 15 + [0.5] * 1
    schedule_states = [STATE_ON] * 6 + [STATE_OFF] * 2 + [STATE_ON] * 16

    hass.states.async_set(MOCK_STATUS_SENSOR_ID, EASEE_STATUS_READY_TO_CHARGE)
    hass.states.async_set(MOCK_MAIN_POWER_SWITCH_ID, STATE_ON)

    start_time = dt_util.now().replace(hour=0, minute=0, second=0, microsecond=0)
    freezer.move_to(start_time)

    max_price_state = hass.states.get(coordinator.max_price_entity_id)
    assert max_price_state is not None
    max_price_from_entity = float(max_price_state.state)

    for hour in range(24):
        current_time = start_time + timedelta(hours=hour)
        freezer.move_to(current_time)

        hass.states.async_set(MOCK_PRICE_SENSOR_ID, str(prices[hour]))
        hass.states.async_set(MOCK_SCHEDULE_ID, schedule_states[hour])

        if (
            coordinator.should_charge_flag
        ):  # Använd koordinatorns flagga från föregående iteration
            hass.states.async_set(MOCK_STATUS_SENSOR_ID, EASEE_STATUS_CHARGING)
        else:
            hass.states.async_set(MOCK_STATUS_SENSOR_ID, EASEE_STATUS_PAUSED)

        await coordinator.async_refresh()
        await hass.async_block_till_done()

        should_be_charging_this_hour = (
            prices[hour] <= max_price_from_entity and schedule_states[hour] == STATE_ON
        )

        assert coordinator.should_charge_flag == should_be_charging_this_hour, (
            f"Fel timme {hour}: Förväntade should_charge={should_be_charging_this_hour}, fick {coordinator.should_charge_flag}. "
            f"Pris: {prices[hour]}, Maxpris: {max_price_from_entity}, Schema: {schedule_states[hour]}"
        )

    num_resume_expected = 0
    num_pause_expected = 0
    currently_charging_sim = False

    for hour in range(24):
        should_charge_now = (
            prices[hour] <= max_price_from_entity and schedule_states[hour] == STATE_ON
        )
        if should_charge_now and not currently_charging_sim:
            num_resume_expected += 1
            currently_charging_sim = True
        elif not should_charge_now and currently_charging_sim:
            num_pause_expected += 1
            currently_charging_sim = False

    total_expected_calls = num_resume_expected + num_pause_expected

    assert len(action_command_calls) == total_expected_calls, (
        f"Fel antal start/stopp-anrop. Fick {len(action_command_calls)}, förväntade {total_expected_calls}. ResumeExp: {num_resume_expected}, PauseExp: {num_pause_expected}. Anrop: {action_command_calls}"
    )
