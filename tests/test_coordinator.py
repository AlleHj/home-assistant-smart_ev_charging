"""Tester för SmartEVChargingCoordinator."""

import pytest
from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.const import STATE_ON, STATE_OFF, STATE_UNAVAILABLE
from homeassistant.config_entries import ConfigEntryState

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
    EASEE_SERVICE_RESUME_CHARGING,
    EASEE_SERVICE_SET_DYNAMIC_CURRENT,
)
from custom_components.smart_ev_charging.coordinator import SmartEVChargingCoordinator


async def test_price_time_charging_starts_when_conditions_are_met(hass: HomeAssistant):
    """
    Testar att koordinatorn startar laddning via Pris/Tid-läget.

    SYFTE:
        Att verifiera att koordinatorns beslutslogik korrekt initierar en
        laddningssession när alla villkor för Pris/Tid-styrning är uppfyllda.

    FÖRUTSÄTTNINGAR (Arrange):
        - En ConfigEntry har skapats med alla nödvändiga sensorer konfigurerade.
        - Externt tillstånd (mockat):
            - Laddarens status är 'ready_to_charge'.
            - Elpriset är lågt (0.5 kr/kWh).
            - Tidsschemat för laddning är PÅ.
        - Internt tillstånd (mockat via integrationens egna entiteter):
            - Switchen för "Smart Laddning" är PÅ.
            - Maxpriset är satt till 1.0 kr/kWh (vilket är högre än det nuvarande priset).
            - Switchen för Solenergiladdning är AV (för att isolera testet).

    UTFÖRANDE (Act):
        - En uppdatering av koordinatorn (`async_request_refresh`) triggas manuellt.

    FÖRVÄNTAT RESULTAT (Assert):
        - Koordinatorn ska anropa Easee-tjänsten `set_dynamic_charger_circuit_current` en gång.
        - Koordinatorn ska anropa Easee-tjänsten `resume_charging` en gång.
        - Koordinatorns aktiva styrningsläge (`active_control_mode`) ska vara "PRIS_TID".
    """  # noqa: D212

    # 1. ARRANGE (Förbered)
    # ---------------------
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_CHARGER_DEVICE: "easee_123",
            CONF_STATUS_SENSOR: "sensor.easee_status",
            CONF_CHARGER_ENABLED_SWITCH_ID: "switch.easee_power",
            CONF_PRICE_SENSOR: "sensor.nordpool_price",
            CONF_TIME_SCHEDULE_ENTITY: "schedule.charging_time",
        },
        entry_id="test_coordinator_entry_1",
    )
    entry.add_to_hass(hass)

    hass.states.async_set("sensor.easee_status", "ready_to_charge")
    hass.states.async_set("switch.easee_power", STATE_ON)
    hass.states.async_set("sensor.nordpool_price", "0.5")
    hass.states.async_set("schedule.charging_time", STATE_ON)

    coordinator = SmartEVChargingCoordinator(hass, entry, 30)

    coordinator.smart_enable_switch_entity_id = (
        "switch.avancerad_elbilsladdning_smart_laddning_aktiv"
    )
    coordinator.max_price_entity_id = "number.avancerad_elbilsladdning_max_elpris"
    coordinator.solar_enable_switch_entity_id = (
        "switch.avancerad_elbilsladdning_aktivera_solenergiladdning"
    )
    coordinator._internal_entities_resolved = True

    hass.states.async_set(coordinator.smart_enable_switch_entity_id, STATE_ON)
    hass.states.async_set(coordinator.max_price_entity_id, "1.0")
    hass.states.async_set(coordinator.solar_enable_switch_entity_id, STATE_OFF)

    resume_calls = async_mock_service(hass, "easee", EASEE_SERVICE_RESUME_CHARGING)
    set_current_calls = async_mock_service(
        hass, "easee", EASEE_SERVICE_SET_DYNAMIC_CURRENT
    )

    # 2. ACT (Agera)
    # -------------
    await coordinator.async_request_refresh()
    await hass.async_block_till_done()

    # 3. ASSERT (Verifiera)
    # ---------------------
    assert len(resume_calls) == 1
    assert len(set_current_calls) == 1
    assert coordinator.active_control_mode == "PRIS_TID"

    # 4. TEARDOWN (Städning)
    # ----------------------
    await coordinator.async_shutdown()
    await hass.async_block_till_done()

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
