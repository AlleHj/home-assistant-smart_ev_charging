# tests/test_connection_override.py
"""Tester för anslutningssekvenser och åsidosättande av extern paus."""

import pytest
import logging
# from unittest.mock import patch # Tas bort om ej använd
# from datetime import datetime, timedelta, timezone # Tas bort om ej använd
# from typing import Set # Tas bort om ej använd

from homeassistant.core import HomeAssistant
from homeassistant.const import (
    STATE_ON,
    STATE_OFF,
    STATE_UNAVAILABLE,
)  # STATE_UNAVAILABLE används
# from homeassistant.config_entries import ConfigEntryState # Tas bort om ej använd

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,  # Används
    async_mock_service,  # Används
    # async_fire_time_changed, # Tas bort om ej använd
)

from custom_components.smart_ev_charging.const import (
    DOMAIN,
    CONF_CHARGER_DEVICE,  # Korrekt importerad nu
    CONF_STATUS_SENSOR,  # Korrekt importerad nu
    CONF_CHARGER_ENABLED_SWITCH_ID,
    CONF_PRICE_SENSOR,
    CONF_TIME_SCHEDULE_ENTITY,
    CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR,
    CONF_DEBUG_LOGGING,
    CONF_CHARGER_DYNAMIC_CURRENT_SENSOR,
    EASEE_SERVICE_SET_DYNAMIC_CURRENT,
    EASEE_STATUS_DISCONNECTED,
    EASEE_STATUS_AWAITING_START,
    EASEE_STATUS_CHARGING,
    ENTITY_ID_SUFFIX_SMART_ENABLE_SWITCH,
    ENTITY_ID_SUFFIX_MAX_PRICE_NUMBER,
    ENTITY_ID_SUFFIX_ENABLE_SOLAR_CHARGING_SWITCH,
    ENTITY_ID_SUFFIX_SOLAR_BUFFER_NUMBER,
    ENTITY_ID_SUFFIX_MIN_SOLAR_CHARGE_CURRENT_A_NUMBER,
    CONTROL_MODE_PRICE_TIME,
    CONTROL_MODE_MANUAL,
)
from custom_components.smart_ev_charging.coordinator import SmartEVChargingCoordinator

# Lokalt definierade mock-konstanter för detta testfall
MOCK_CHARGER_DEVICE_ID_CONN_OVERRIDE = (
    "easee_123_conn_override"  # Förtydligat namn för att undvika kollision
)
MOCK_STATUS_SENSOR_ID_CONN_OVERRIDE = "sensor.easee_status_conn_override"
MOCK_PRICE_SENSOR_ID_CONN_OVERRIDE = "sensor.nordpool_price_conn_override"
# MOCK_SCHEDULE_ID_CONN_OVERRIDE = "schedule.charging_time_conn_override" # Används inte då CONF_TIME_SCHEDULE_ENTITY är None
MOCK_MAIN_POWER_SWITCH_ID_CONN_OVERRIDE = "switch.easee_power_conn_override"
MOCK_MAX_CURRENT_SENSOR_ID_CONN_OVERRIDE = "sensor.charger_max_current_conn_override"
DYN_LIMIT_SENSOR_ID_CONN_OVERRIDE = "sensor.current_dynamic_limit_conn_override"


@pytest.fixture
async def setup_coordinator_conn_override(hass: HomeAssistant):
    """Fixture för att sätta upp SmartEVChargingCoordinator för dessa specifika tester."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_CHARGER_DEVICE: MOCK_CHARGER_DEVICE_ID_CONN_OVERRIDE,
            CONF_STATUS_SENSOR: MOCK_STATUS_SENSOR_ID_CONN_OVERRIDE,
            CONF_CHARGER_ENABLED_SWITCH_ID: MOCK_MAIN_POWER_SWITCH_ID_CONN_OVERRIDE,
            CONF_PRICE_SENSOR: MOCK_PRICE_SENSOR_ID_CONN_OVERRIDE,
            CONF_TIME_SCHEDULE_ENTITY: None,
            CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR: MOCK_MAX_CURRENT_SENSOR_ID_CONN_OVERRIDE,
            CONF_DEBUG_LOGGING: True,
            CONF_CHARGER_DYNAMIC_CURRENT_SENSOR: DYN_LIMIT_SENSOR_ID_CONN_OVERRIDE,
        },
        entry_id="test_connection_sequence_v2",  # Unikt entry_id
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator: SmartEVChargingCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    assert coordinator is not None

    coordinator.smart_enable_switch_entity_id = (
        f"switch.{DOMAIN}_{entry.entry_id}_{ENTITY_ID_SUFFIX_SMART_ENABLE_SWITCH}"
    )
    coordinator.max_price_entity_id = (
        f"number.{DOMAIN}_{entry.entry_id}_{ENTITY_ID_SUFFIX_MAX_PRICE_NUMBER}"
    )
    coordinator.solar_enable_switch_entity_id = f"switch.{DOMAIN}_{entry.entry_id}_{ENTITY_ID_SUFFIX_ENABLE_SOLAR_CHARGING_SWITCH}"
    coordinator.solar_buffer_entity_id = (
        f"number.{DOMAIN}_{entry.entry_id}_{ENTITY_ID_SUFFIX_SOLAR_BUFFER_NUMBER}"
    )
    coordinator.min_solar_charge_current_entity_id = f"number.{DOMAIN}_{entry.entry_id}_{ENTITY_ID_SUFFIX_MIN_SOLAR_CHARGE_CURRENT_A_NUMBER}"
    coordinator._internal_entities_resolved = True

    hass.states.async_set(coordinator.smart_enable_switch_entity_id, STATE_ON)
    hass.states.async_set(coordinator.max_price_entity_id, "0.50")
    hass.states.async_set(coordinator.solar_enable_switch_entity_id, STATE_OFF)

    return coordinator


async def test_charger_connection_sequence_and_pause_override(
    hass: HomeAssistant, setup_coordinator_conn_override: SmartEVChargingCoordinator
):
    """
    Testar en sekvens där bilen ansluts, laddning startar (Pris/Tid),
    laddning pågår, pausas externt (status ändras till awaiting_start),
    och sedan omedelbart återupptas av integrationen.

    SYFTE:
        Att verifiera att integrationen:
        1. Korrekt hanterar en typisk anslutningssekvens.
        2. Startar laddning när villkoren för Pris/Tid är uppfyllda.
        3. Kan "ta tillbaka" kontrollen och återuppta laddningen om en PÅGÅENDE
           laddning pausas externt.

    FÖRUTSÄTTNINGAR (Arrange):
        - Inget tidsschema är konfigurerat.
        - Elpriset är konstant lågt.
        - Maxpriset är satt högre än spotpriset.
        - Switchen för "Smart Laddning" är PÅ, Solenergiladdning är AV.

    UTFÖRANDE (Act) & FÖRVÄNTAT RESULTAT (Assert) - Stegvis:
        1. INITIALT: 'disconnected'. -> Ingen laddning.
        2. ANSLUTNING: 'awaiting_start'. -> Laddning SKA starta (action_command "resume" och set_current).
        3. LADDNING PÅGÅR: Status sätts till 'charging'.
           -> Ingen ny START/STOPP. `set_current` ska INTE anropas (om optimering är på och ström är korrekt).
        4. EXTERN PAUS: Status ändras till 'awaiting_start' från 'charging'.
           -> Koordinatorn ska omedelbart återuppta laddningen (action_command "resume").
           -> `set_current` ska INTE anropas igen om den dynamiska gränsen antas vara oförändrad.
    """
    coordinator = setup_coordinator_conn_override

    hass.states.async_set(MOCK_MAIN_POWER_SWITCH_ID_CONN_OVERRIDE, STATE_ON)
    hass.states.async_set(MOCK_PRICE_SENSOR_ID_CONN_OVERRIDE, "0.30")
    hass.states.async_set(MOCK_MAX_CURRENT_SENSOR_ID_CONN_OVERRIDE, "16")

    action_command_calls = async_mock_service(hass, "easee", "action_command")
    set_current_calls = async_mock_service(
        hass, "easee", EASEE_SERVICE_SET_DYNAMIC_CURRENT
    )

    # Steg 1: Bilen är frånkopplad
    print("TESTSTEG 1: Disconnected")
    hass.states.async_set(
        MOCK_STATUS_SENSOR_ID_CONN_OVERRIDE, EASEE_STATUS_DISCONNECTED[0]
    )
    hass.states.async_set(DYN_LIMIT_SENSOR_ID_CONN_OVERRIDE, STATE_UNAVAILABLE)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert len(action_command_calls) == 0
    assert len(set_current_calls) == 0
    assert coordinator.active_control_mode == CONTROL_MODE_MANUAL

    # Steg 2: Bilen ansluts, status -> awaiting_start. Laddning ska starta.
    print("TESTSTEG 2: Awaiting Start - Förväntar START")
    action_command_calls.clear()
    set_current_calls.clear()
    hass.states.async_set(
        MOCK_STATUS_SENSOR_ID_CONN_OVERRIDE, EASEE_STATUS_AWAITING_START
    )
    hass.states.async_set(DYN_LIMIT_SENSOR_ID_CONN_OVERRIDE, STATE_UNAVAILABLE)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert len(action_command_calls) == 1, "Laddning startade inte vid awaiting_start"
    assert action_command_calls[0].data["action_command"] == "start"
    assert len(set_current_calls) == 1, "Ström sattes inte vid awaiting_start"
    assert coordinator.active_control_mode == CONTROL_MODE_PRICE_TIME

    # Steg 3: Simulera att laddaren nu faktiskt laddar.
    print("TESTSTEG 3: Charging (efter start) - Förväntar ingen ny åtgärd")
    hass.states.async_set(MOCK_STATUS_SENSOR_ID_CONN_OVERRIDE, EASEE_STATUS_CHARGING)
    hass.states.async_set(DYN_LIMIT_SENSOR_ID_CONN_OVERRIDE, "16.0")
    action_command_calls.clear()
    set_current_calls.clear()
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert len(action_command_calls) == 0, (
        "Onödigt action_command när laddning redan pågår"
    )
    assert len(set_current_calls) == 0, (
        "Onödigt set_current när laddning redan pågår med rätt ström"
    )
    assert coordinator.active_control_mode == CONTROL_MODE_PRICE_TIME

    # Steg 4: Laddningen pausas externt, status -> awaiting_start (från 'charging')
    print("TESTSTEG 4: Externt pausad (status awaiting_start) - Förväntar ÅTERSTART")
    action_command_calls.clear()
    set_current_calls.clear()
    hass.states.async_set(DYN_LIMIT_SENSOR_ID_CONN_OVERRIDE, "0")
    hass.states.async_set(
        MOCK_STATUS_SENSOR_ID_CONN_OVERRIDE, EASEE_STATUS_AWAITING_START
    )
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert len(action_command_calls) == 1, (
        "Laddning återupptogs inte efter extern paus till awaiting_start"
    )
    assert action_command_calls[0].data["action_command"] == "start"
    assert len(set_current_calls) == 1, (
        "Ström sattes inte vid återstart när gränsen redan var korrekt"
    )
    assert coordinator.active_control_mode == CONTROL_MODE_PRICE_TIME
