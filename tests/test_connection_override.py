"""Tester för anslutningssekvenser och åsidosättande av extern paus."""

import pytest
import logging
from unittest.mock import patch
from datetime import datetime, timedelta, timezone
from typing import Set

from homeassistant.core import HomeAssistant
from homeassistant.const import STATE_ON, STATE_OFF, STATE_UNAVAILABLE
from homeassistant.config_entries import ConfigEntryState

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
    EASEE_SERVICE_RESUME_CHARGING,
    EASEE_SERVICE_SET_DYNAMIC_CURRENT,
    CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR,
    CONF_DEBUG_LOGGING,
    CONF_CHARGER_DYNAMIC_CURRENT_SENSOR,
    ENTITY_ID_SUFFIX_SMART_ENABLE_SWITCH,
    ENTITY_ID_SUFFIX_MAX_PRICE_NUMBER,
    ENTITY_ID_SUFFIX_ENABLE_SOLAR_CHARGING_SWITCH,
    ENTITY_ID_SUFFIX_SOLAR_BUFFER_NUMBER,
    ENTITY_ID_SUFFIX_MIN_SOLAR_CHARGE_CURRENT_A_NUMBER,
    EASEE_STATUS_DISCONNECTED,
    EASEE_STATUS_AWAITING_START,
    EASEE_STATUS_READY_TO_CHARGE,
    EASEE_STATUS_CHARGING,
    EASEE_SERVICE_PAUSE_CHARGING,
)
from custom_components.smart_ev_charging.coordinator import SmartEVChargingCoordinator


async def test_charger_connection_sequence_and_pause_override(hass: HomeAssistant):
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
        2. ANSLUTNING: 'awaiting_start'. -> Laddning SKA starta (resume och set_current).
        3. LADDNING PÅGÅR: Status sätts till 'charging'.
           -> Ingen ny START/STOPP. `set_current` ska INTE anropas (om optimering är på och ström är korrekt).
        4. EXTERN PAUS: Status ändras till 'awaiting_start' från 'charging'.
           -> Koordinatorn ska omedelbart återuppta laddningen (resume).
           -> `set_current` ska INTE anropas igen om den dynamiska gränsen antas vara oförändrad.
    """  # noqa: D205, D212
    # 1. ARRANGE
    DYN_LIMIT_SENSOR_ID = "sensor.current_dynamic_limit_conn_seq"
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_CHARGER_DEVICE: "easee_123",
            CONF_STATUS_SENSOR: "sensor.easee_status",
            CONF_CHARGER_ENABLED_SWITCH_ID: "switch.easee_power",
            CONF_PRICE_SENSOR: "sensor.nordpool_price",
            CONF_TIME_SCHEDULE_ENTITY: None,
            CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR: "sensor.charger_max_current",
            CONF_DEBUG_LOGGING: True,
            CONF_CHARGER_DYNAMIC_CURRENT_SENSOR: DYN_LIMIT_SENSOR_ID,
        },
        entry_id="test_connection_sequence",
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.smart_ev_charging.coordinator.SmartEVChargingCoordinator._setup_listeners"
    ):
        coordinator = SmartEVChargingCoordinator(hass, entry, 30)
        coordinator._internal_entities_resolved = True
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

        hass.states.async_set("switch.easee_power", STATE_ON)
        hass.states.async_set("sensor.nordpool_price", "0.30")
        hass.states.async_set("sensor.charger_max_current", "16")
        hass.states.async_set(coordinator.smart_enable_switch_entity_id, STATE_ON)
        hass.states.async_set(coordinator.max_price_entity_id, "0.50")
        hass.states.async_set(coordinator.solar_enable_switch_entity_id, STATE_OFF)

        resume_calls = async_mock_service(hass, "easee", EASEE_SERVICE_RESUME_CHARGING)
        pause_calls = async_mock_service(hass, "easee", EASEE_SERVICE_PAUSE_CHARGING)
        set_current_calls = async_mock_service(
            hass, "easee", EASEE_SERVICE_SET_DYNAMIC_CURRENT
        )

        # 2. ACT & ASSERT - STEG FÖR STEG

        # Steg 1: Bilen är frånkopplad
        print("TESTSTEG 1: Disconnected")
        hass.states.async_set("sensor.easee_status", EASEE_STATUS_DISCONNECTED[0])
        hass.states.async_set(DYN_LIMIT_SENSOR_ID, STATE_UNAVAILABLE)
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert len(resume_calls) == 0
        assert len(pause_calls) == 0
        assert len(set_current_calls) == 0

        # Steg 2: Bilen ansluts, status -> awaiting_start. Laddning ska starta.
        print("TESTSTEG 2: Awaiting Start - Förväntar START")
        resume_calls.clear()
        set_current_calls.clear()
        pause_calls.clear()
        hass.states.async_set("sensor.easee_status", EASEE_STATUS_AWAITING_START)
        hass.states.async_set(DYN_LIMIT_SENSOR_ID, STATE_UNAVAILABLE)
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert len(resume_calls) == 1, "Laddning startade inte vid awaiting_start"
        assert len(set_current_calls) == 1, "Ström sattes inte vid awaiting_start"

        # Steg 3: Simulera att laddaren nu faktiskt laddar.
        print("TESTSTEG 3: Charging (efter start) - Förväntar ingen ny åtgärd")
        hass.states.async_set("sensor.easee_status", EASEE_STATUS_CHARGING)
        hass.states.async_set(
            DYN_LIMIT_SENSOR_ID, "16.0"
        )  # Antag att strömmen sattes korrekt till 16A
        resume_calls.clear()
        pause_calls.clear()
        set_current_calls.clear()
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert len(resume_calls) == 0, "Onödig resume när laddning redan pågår"
        assert len(set_current_calls) == 0, (
            "Onödigt set_current när laddning redan pågår med rätt ström"
        )

        # Steg 4: Laddningen pausas externt, status -> awaiting_start (från 'charging')
        print(
            "TESTSTEG 4: Externt pausad (status awaiting_start) - Förväntar ÅTERSTART"
        )
        resume_calls.clear()
        set_current_calls.clear()
        pause_calls.clear()
        # Den dynamiska gränsen på laddaren antas vara oförändrad (fortfarande 16A)
        # eftersom en extern paus inte nödvändigtvis ändrar den.
        hass.states.async_set(DYN_LIMIT_SENSOR_ID, "16.0")
        hass.states.async_set("sensor.easee_status", EASEE_STATUS_AWAITING_START)
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert len(resume_calls) == 1, (
            "Laddning återupptogs inte efter extern paus till awaiting_start"
        )
        # Eftersom DYN_LIMIT_SENSOR_ID fortfarande är 16A, och målet är 16A,
        # ska set_current INTE anropas igen tack vare optimeringen.
        assert len(set_current_calls) == 0, (
            "Ström sattes felaktigt vid återstart när gränsen redan var korrekt"
        )
