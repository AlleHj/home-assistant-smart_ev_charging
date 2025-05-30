"""Tester för SmartEVChargingCoordinator."""

import pytest
import logging
import random
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
    CONF_EV_SOC_SENSOR,
    CONF_TARGET_SOC_LIMIT,
    CONF_DEBUG_LOGGING,
    EASEE_SERVICE_PAUSE_CHARGING,
)
from custom_components.smart_ev_charging.coordinator import SmartEVChargingCoordinator

# En "falsk" konstant för den simulerade sensorn i TDD-testet
CONF_CHARGER_DYNAMIC_CURRENT_SENSOR = "charger_dynamic_current_sensor_id"


async def test_price_time_charging_starts_when_conditions_are_met(hass: HomeAssistant):
    """Testar att koordinatorn startar laddning via Pris/Tid-läget från stillestånd."""
    # 1. ARRANGE
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_CHARGER_DEVICE: "easee_123",
            CONF_STATUS_SENSOR: "sensor.easee_status",
            CONF_CHARGER_ENABLED_SWITCH_ID: "switch.easee_power",
            CONF_PRICE_SENSOR: "sensor.nordpool_price",
            CONF_TIME_SCHEDULE_ENTITY: "schedule.charging_time",
            CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR: "sensor.charger_max_current",
            CONF_DEBUG_LOGGING: True,
        },
        entry_id="test_coordinator_entry_1",
    )
    entry.add_to_hass(hass)

    # Använd "with patch" för att stänga av listeners och undvika timing-problem.
    with patch(
        "custom_components.smart_ev_charging.coordinator.SmartEVChargingCoordinator._setup_listeners"
    ):
        coordinator = SmartEVChargingCoordinator(hass, entry, 30)
        coordinator._internal_entities_resolved = True
        coordinator.smart_enable_switch_entity_id = (
            "switch.avancerad_elbilsladdning_smart_laddning_aktiv"
        )
        coordinator.max_price_entity_id = "number.avancerad_elbilsladdning_max_elpris"

        hass.states.async_set("sensor.easee_status", "ready_to_charge")
        hass.states.async_set("switch.easee_power", STATE_ON)
        hass.states.async_set("sensor.nordpool_price", "0.5")
        hass.states.async_set("schedule.charging_time", STATE_ON)
        hass.states.async_set("sensor.charger_max_current", "16")
        hass.states.async_set(coordinator.smart_enable_switch_entity_id, STATE_ON)
        hass.states.async_set(coordinator.max_price_entity_id, "1.0")

        resume_calls = async_mock_service(hass, "easee", EASEE_SERVICE_RESUME_CHARGING)
        set_current_calls = async_mock_service(
            hass, "easee", EASEE_SERVICE_SET_DYNAMIC_CURRENT
        )

        # 2. ACT
        # Använd async_refresh() för att köra direkt utan timer.
        await coordinator.async_refresh()
        await hass.async_block_till_done()

        # 3. ASSERT
        assert len(resume_calls) == 1
        assert len(set_current_calls) == 1


async def test_price_time_charging_does_not_call_set_current_unnecessarily(
    hass: HomeAssistant,
):
    """Testar att koordinatorn INTE gör onödiga anrop för Pris/Tid-läget."""
    # 1. ARRANGE
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_CHARGER_DEVICE: "easee_123",
            CONF_STATUS_SENSOR: "sensor.easee_status",
            CONF_CHARGER_ENABLED_SWITCH_ID: "switch.easee_power",
            CONF_PRICE_SENSOR: "sensor.nordpool_price",
            CONF_TIME_SCHEDULE_ENTITY: "schedule.charging_time",
            CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR: "sensor.charger_max_current",
            CONF_DEBUG_LOGGING: True,
            CONF_CHARGER_DYNAMIC_CURRENT_SENSOR: "sensor.current_dynamic_limit",
        },
        entry_id="test_coordinator_entry_2",
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.smart_ev_charging.coordinator.SmartEVChargingCoordinator._setup_listeners"
    ):
        coordinator = SmartEVChargingCoordinator(hass, entry, 30)
        coordinator._internal_entities_resolved = True
        coordinator.smart_enable_switch_entity_id = (
            "switch.avancerad_elbilsladdning_smart_laddning_aktiv"
        )
        coordinator.max_price_entity_id = "number.avancerad_elbilsladdning_max_elpris"

        hass.states.async_set("sensor.easee_status", "charging")
        hass.states.async_set("switch.easee_power", STATE_ON)
        hass.states.async_set("sensor.nordpool_price", "0.5")
        hass.states.async_set("schedule.charging_time", STATE_ON)
        hass.states.async_set("sensor.charger_max_current", "16")
        hass.states.async_set("sensor.current_dynamic_limit", "16")
        hass.states.async_set(coordinator.smart_enable_switch_entity_id, STATE_ON)
        hass.states.async_set(coordinator.max_price_entity_id, "1.0")

        set_current_calls = async_mock_service(
            hass, "easee", EASEE_SERVICE_SET_DYNAMIC_CURRENT
        )

        # 2. ACT
        await coordinator.async_refresh()
        await hass.async_block_till_done()

        # 3. ASSERT
        assert len(set_current_calls) == 0


async def test_charging_stops_when_soc_limit_is_reached(hass: HomeAssistant, caplog):
    """Testar att laddning pausas och ett meddelande loggas när SoC-gränsen nås."""
    # 1. ARRANGE
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_CHARGER_DEVICE: "easee_123",
            CONF_STATUS_SENSOR: "sensor.easee_status",
            CONF_EV_SOC_SENSOR: "sensor.ev_soc",
            CONF_TARGET_SOC_LIMIT: 89.0,
            CONF_DEBUG_LOGGING: True,
            CONF_CHARGER_ENABLED_SWITCH_ID: "switch.easee_power",
        },
        entry_id="test_coordinator_entry_3",
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.smart_ev_charging.coordinator.SmartEVChargingCoordinator._setup_listeners"
    ):
        coordinator = SmartEVChargingCoordinator(hass, entry, 30)
        coordinator._internal_entities_resolved = True

        hass.states.async_set("sensor.easee_status", "charging")
        hass.states.async_set("sensor.ev_soc", "90.0")
        hass.states.async_set("switch.easee_power", STATE_ON)

        pause_calls = async_mock_service(hass, "easee", EASEE_SERVICE_PAUSE_CHARGING)

        # 2. ACT
        caplog.set_level(logging.INFO)
        await coordinator.async_refresh()
        await hass.async_block_till_done()

        # 3. ASSERT
        assert len(pause_calls) == 1
        assert "SoC (90.0%) har nått målet (89.0%)" in caplog.text


async def test_full_day_price_time_simulation(hass: HomeAssistant):
    """Testar Pris/Tid-logiken genom att simulera ett helt dygn, timme för timme."""
    # 1. ARRANGE
    max_price = random.uniform(0.2, 0.8)
    active_schedule_hours: Set[int] = set(random.sample(range(24), 12))
    hourly_spot_prices = {hour: random.uniform(0.0, 1.0) for hour in range(24)}

    print(f"\n--- Test-setup ---")
    print(f"Slumpat maxpris: {max_price:.2f} kr")
    print(f"Timmar med aktivt schema: {sorted(list(active_schedule_hours))}")

    MOCK_SCHEDULE_ID = "schedule.test_laddningsschema"
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_CHARGER_DEVICE: "easee_123",
            CONF_STATUS_SENSOR: "sensor.easee_status",
            CONF_CHARGER_ENABLED_SWITCH_ID: "switch.easee_power",
            CONF_PRICE_SENSOR: "sensor.nordpool_price",
            CONF_TIME_SCHEDULE_ENTITY: MOCK_SCHEDULE_ID,
            CONF_DEBUG_LOGGING: True,
        },
        entry_id="test_full_day_sim",
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.smart_ev_charging.coordinator.SmartEVChargingCoordinator._setup_listeners"
    ):
        coordinator = SmartEVChargingCoordinator(hass, entry, 30)
        coordinator._internal_entities_resolved = True
        coordinator.smart_enable_switch_entity_id = (
            "switch.avancerad_elbilsladdning_smart_laddning_aktiv"
        )
        coordinator.max_price_entity_id = "number.avancerad_elbilsladdning_max_elpris"

        hass.states.async_set(coordinator.smart_enable_switch_entity_id, STATE_ON)
        hass.states.async_set(coordinator.max_price_entity_id, f"{max_price:.2f}")

        hass.states.async_set("sensor.easee_status", "ready_to_charge")
        hass.states.async_set("switch.easee_power", STATE_ON)

        resume_calls = async_mock_service(hass, "easee", EASEE_SERVICE_RESUME_CHARGING)
        pause_calls = async_mock_service(hass, "easee", EASEE_SERVICE_PAUSE_CHARGING)
        async_mock_service(hass, "easee", EASEE_SERVICE_SET_DYNAMIC_CURRENT)

        # 2. ACT & ASSERT
        start_of_day = datetime(2025, 5, 30, 0, 0, 0, tzinfo=timezone.utc)
        is_charging = False

        for hour in range(24):
            current_time = start_of_day + timedelta(hours=hour)

            spot_price_this_hour = hourly_spot_prices[hour]
            schedule_active_this_hour = hour in active_schedule_hours

            schedule_state = STATE_ON if schedule_active_this_hour else STATE_OFF
            hass.states.async_set(MOCK_SCHEDULE_ID, schedule_state)

            hass.states.async_set(
                "sensor.nordpool_price", f"{spot_price_this_hour:.2f}"
            )

            current_charger_status = "charging" if is_charging else "ready_to_charge"
            hass.states.async_set("sensor.easee_status", current_charger_status)

            async_fire_time_changed(hass, current_time)
            await hass.async_block_till_done()

            should_be_charging = schedule_active_this_hour and (
                spot_price_this_hour <= max_price
            )

            resume_calls.clear()
            pause_calls.clear()

            await coordinator.async_refresh()

            if should_be_charging and not is_charging:
                print(
                    f"TIMME {hour:02d}: Pris {spot_price_this_hour:.2f} <= {max_price:.2f}, Schema PÅ. Förväntar START."
                )
                assert len(resume_calls) == 1
                is_charging = True
            elif not should_be_charging and is_charging:
                print(f"TIMME {hour:02d}: Pris/Schema ogiltigt. Förväntar STOPP.")
                assert len(pause_calls) == 1
                is_charging = False
            else:
                pass  # Ingen åtgärd förväntad
