#
# tests/test_dynamisk_justering_solenergi.py
#
"""
Testfil för att verifiera den dynamiska justeringen av laddström vid solenergiladdning.
Fokuserar på beräkning av överskott och anrop till set_dynamic_current.
"""

from datetime import timedelta
import pytest
import logging

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from homeassistant.core import HomeAssistant
from homeassistant.const import STATE_ON, STATE_OFF
from homeassistant.util.dt import (
    UTC,
    as_utc,
)  # Importerad men oanvänd i den här versionen
from freezegun.api import FrozenDateTimeFactory

from custom_components.smart_ev_charging.const import (
    DOMAIN,
    CONF_CHARGER_DEVICE,
    CONF_STATUS_SENSOR,
    CONF_HOUSE_POWER_SENSOR,
    CONF_SOLAR_PRODUCTION_SENSOR,
    CONF_CHARGER_ENABLED_SWITCH_ID,
    CONF_DEBUG_LOGGING,
    EASEE_STATUS_READY_TO_CHARGE,
    EASEE_STATUS_CHARGING,  # Lade till denna för att använda i testet
    EASEE_SERVICE_SET_DYNAMIC_CURRENT,
    SOLAR_SURPLUS_DELAY_SECONDS,
    ENTITY_ID_SUFFIX_SOLAR_BUFFER_NUMBER,
)
from custom_components.smart_ev_charging.coordinator import SmartEVChargingCoordinator

# Mockade entitets-ID:n och config-data definieras lokalt för detta test
MOCK_SOLAR_PRODUCTION_SENSOR_ID = "sensor.test_solar_prod_dynamic_solar"
MOCK_HOUSE_POWER_SENSOR_ID = "sensor.test_house_power_dynamic_solar"
MOCK_STATUS_SENSOR_ID = "sensor.test_charger_status_dynamic_solar"
MOCK_MAIN_POWER_SWITCH_ID_SOLAR = "switch.mock_charger_power_dynamic_solar"

ACTUAL_SOLAR_BUFFER_ID = (
    f"number.{DOMAIN}_test_dynamic_solar_entry_{ENTITY_ID_SUFFIX_SOLAR_BUFFER_NUMBER}"
)

MOCK_CONFIG_SOLAR_DATA = {
    CONF_CHARGER_DEVICE: "mock_device_dynamic_solar",
    CONF_STATUS_SENSOR: MOCK_STATUS_SENSOR_ID,
    CONF_HOUSE_POWER_SENSOR: MOCK_HOUSE_POWER_SENSOR_ID,
    CONF_SOLAR_PRODUCTION_SENSOR: MOCK_SOLAR_PRODUCTION_SENSOR_ID,
    CONF_DEBUG_LOGGING: True,
    CONF_CHARGER_ENABLED_SWITCH_ID: MOCK_MAIN_POWER_SWITCH_ID_SOLAR,
    "price_sensor_id": "sensor.dummy_price_for_solar_test",
}


@pytest.fixture
async def setup_solar_charging_test(hass: HomeAssistant):
    """Sätter upp en grundläggande konfiguration för solenergiladdningstester."""
    entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG_SOLAR_DATA, entry_id="test_dynamic_solar_entry"
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator: SmartEVChargingCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    assert coordinator is not None
    from custom_components.smart_ev_charging.const import (
        ENTITY_ID_SUFFIX_SMART_ENABLE_SWITCH,
        ENTITY_ID_SUFFIX_MAX_PRICE_NUMBER,
        ENTITY_ID_SUFFIX_ENABLE_SOLAR_CHARGING_SWITCH,
        ENTITY_ID_SUFFIX_MIN_SOLAR_CHARGE_CURRENT_A_NUMBER,
    )

    coordinator.smart_enable_switch_entity_id = (
        f"switch.{DOMAIN}_{entry.entry_id}_{ENTITY_ID_SUFFIX_SMART_ENABLE_SWITCH}"
    )
    coordinator.max_price_entity_id = (
        f"number.{DOMAIN}_{entry.entry_id}_{ENTITY_ID_SUFFIX_MAX_PRICE_NUMBER}"
    )
    coordinator.solar_enable_switch_entity_id = f"switch.{DOMAIN}_{entry.entry_id}_{ENTITY_ID_SUFFIX_ENABLE_SOLAR_CHARGING_SWITCH}"
    coordinator.solar_buffer_entity_id = ACTUAL_SOLAR_BUFFER_ID
    coordinator.min_solar_charge_current_entity_id = f"number.{DOMAIN}_{entry.entry_id}_{ENTITY_ID_SUFFIX_MIN_SOLAR_CHARGE_CURRENT_A_NUMBER}"
    coordinator._internal_entities_resolved = True

    hass.states.async_set(coordinator.solar_enable_switch_entity_id, STATE_ON)
    hass.states.async_set(coordinator.smart_enable_switch_entity_id, STATE_OFF)
    hass.states.async_set(ACTUAL_SOLAR_BUFFER_ID, "500")
    hass.states.async_set(coordinator.min_solar_charge_current_entity_id, "6")
    return coordinator


@pytest.mark.asyncio
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

    action_command_calls = async_mock_service(hass, "easee", "action_command")
    set_charger_dynamic_limit_calls = async_mock_service(
        hass, "easee", "set_charger_dynamic_limit"
    )

    # --- ARRANGE & ACT - Steg 1: Högt överskott ---
    hass.states.async_set(MOCK_SOLAR_PRODUCTION_SENSOR_ID, "7000")
    hass.states.async_set(MOCK_HOUSE_POWER_SENSOR_ID, "500")
    hass.states.async_set(MOCK_STATUS_SENSOR_ID, EASEE_STATUS_READY_TO_CHARGE[0])
    hass.states.async_set(MOCK_MAIN_POWER_SWITCH_ID_SOLAR, STATE_ON)

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert len(action_command_calls) == 0
    assert len(set_charger_dynamic_limit_calls) == 1
    assert set_charger_dynamic_limit_calls[0].data["current"] == 9

    action_command_calls.clear()
    set_charger_dynamic_limit_calls.clear()

    # --- ARRANGE & ACT - Steg 2: Minskat överskott ---
    hass.states.async_set(MOCK_STATUS_SENSOR_ID, EASEE_STATUS_CHARGING)
    hass.states.async_set(MOCK_HOUSE_POWER_SENSOR_ID, "1500")

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    # --- ASSERT - Steg 2 ---
    assert len(action_command_calls) == 0
    assert len(set_charger_dynamic_limit_calls) == 1
    assert set_charger_dynamic_limit_calls[0].data["current"] == 9

    action_command_calls.clear()
    set_charger_dynamic_limit_calls.clear()

    # --- ARRANGE & ACT - Steg 3: Buffert ändras ---
    hass.states.async_set(MOCK_STATUS_SENSOR_ID, EASEE_STATUS_CHARGING)
    hass.states.async_set(ACTUAL_SOLAR_BUFFER_ID, "1500")

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    # --- ASSERT - Steg 3 ---
    assert len(action_command_calls) == 0
    assert len(set_charger_dynamic_limit_calls) == 1
    assert set_charger_dynamic_limit_calls[0].data["current"] == 7
