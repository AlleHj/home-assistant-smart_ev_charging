# test_solar_to_price_time_on_price_drop.py
"""
Testar övergång från Solenergiladdning till Pris/Tid-laddning
när elpriset sjunker under max acceptabelt pris.
"""

import pytest
import logging
from unittest.mock import patch
from datetime import datetime, timedelta, timezone
import math

from homeassistant.core import HomeAssistant
from homeassistant.const import STATE_ON, STATE_OFF
from homeassistant.util import dt as dt_util

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
    CONF_TIME_SCHEDULE_ENTITY,  # Behövs i config, men sätts till None för "alltid aktivt"
    CONF_SOLAR_PRODUCTION_SENSOR,
    CONF_HOUSE_POWER_SENSOR,
    CONF_SOLAR_SCHEDULE_ENTITY,  # Behövs i config, men sätts till None
    CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR,
    CONF_CHARGER_DYNAMIC_CURRENT_SENSOR,
    CONF_DEBUG_LOGGING,
    ENTITY_ID_SUFFIX_SMART_ENABLE_SWITCH,
    ENTITY_ID_SUFFIX_MAX_PRICE_NUMBER,
    ENTITY_ID_SUFFIX_ENABLE_SOLAR_CHARGING_SWITCH,
    ENTITY_ID_SUFFIX_SOLAR_BUFFER_NUMBER,
    ENTITY_ID_SUFFIX_MIN_SOLAR_CHARGE_CURRENT_A_NUMBER,
    EASEE_SERVICE_SET_DYNAMIC_CURRENT,
    EASEE_SERVICE_RESUME_CHARGING,
    EASEE_STATUS_CHARGING,
    CONTROL_MODE_SOLAR_SURPLUS,
    CONTROL_MODE_PRICE_TIME,
    MIN_CHARGE_CURRENT_A,
    MAX_CHARGE_CURRENT_A_HW_DEFAULT,  # Hårdvarumax
    SOLAR_SURPLUS_DELAY_SECONDS,
)
from custom_components.smart_ev_charging.coordinator import SmartEVChargingCoordinator

# Konstanter för testet
CHARGER_DEVICE_ID = "easee_price_drop_test"
STATUS_SENSOR_ID = "sensor.easee_status_price_drop"
POWER_SWITCH_ID = "switch.easee_power_price_drop"
PRICE_SENSOR_ID = "sensor.nordpool_price_price_drop"
SOLAR_PROD_SENSOR_ID = "sensor.solar_production_price_drop"
HOUSE_POWER_SENSOR_ID = "sensor.house_power_price_drop"
MAX_CURRENT_SENSOR_ID = "sensor.charger_max_current_price_drop"
DYN_CURRENT_SENSOR_ID = "sensor.charger_dynamic_current_price_drop"

# Interna entitets-ID:n
SMART_ENABLE_SWITCH_ID = (
    f"switch.{DOMAIN}_test_price_drop_{ENTITY_ID_SUFFIX_SMART_ENABLE_SWITCH}"
)
MAX_PRICE_NUMBER_ID = (
    f"number.{DOMAIN}_test_price_drop_{ENTITY_ID_SUFFIX_MAX_PRICE_NUMBER}"
)
SOLAR_ENABLE_SWITCH_ID = (
    f"switch.{DOMAIN}_test_price_drop_{ENTITY_ID_SUFFIX_ENABLE_SOLAR_CHARGING_SWITCH}"
)
SOLAR_BUFFER_NUMBER_ID = (
    f"number.{DOMAIN}_test_price_drop_{ENTITY_ID_SUFFIX_SOLAR_BUFFER_NUMBER}"
)
MIN_SOLAR_CURRENT_NUMBER_ID = f"number.{DOMAIN}_test_price_drop_{ENTITY_ID_SUFFIX_MIN_SOLAR_CHARGE_CURRENT_A_NUMBER}"


@pytest.fixture(autouse=True)
def enable_debug_logging():
    logging.getLogger(f"custom_components.{DOMAIN}").setLevel(logging.DEBUG)


async def test_solar_to_price_time_on_price_drop(hass: HomeAssistant, caplog):
    """
    Testar övergång från Solenergi till Pris/Tid när elpriset sjunker.

    SYFTE:
    1. Solenergiladdning är aktiv initialt (pris för högt för Pris/Tid, inga scheman).
       Dynamisk ström sätts baserat på solöverskott.
    2. När elpriset sjunker under max acceptabelt pris, tar Pris/Tid över.
       Dynamisk ström sätts till hårdvarumax.

    FÖRUTSÄTTNINGAR:
    - Initialt spotpris: 1.0 kr/kWh. Max acceptabelt pris: 0.6 kr/kWh.
    - Solproduktion: 8000 W. Husets förbrukning: 500 W. Buffer: 0 W. Min solar current: 6 A.
    - Båda laddningstyperna (Pris/Tid, Solenergi) är PÅ via sina switchar.
    - CONF_TIME_SCHEDULE_ENTITY och CONF_SOLAR_SCHEDULE_ENTITY är None (alltid aktiva).
    - Laddaren är i 'charging'-status.
    - Sensor för dynamisk ström finns. Hårdvarumax är 16A.
    """
    # 1. ARRANGE
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_CHARGER_DEVICE: CHARGER_DEVICE_ID,
            CONF_STATUS_SENSOR: STATUS_SENSOR_ID,
            CONF_CHARGER_ENABLED_SWITCH_ID: POWER_SWITCH_ID,
            CONF_PRICE_SENSOR: PRICE_SENSOR_ID,
            CONF_TIME_SCHEDULE_ENTITY: None,  # Inget schema = alltid aktivt för Pris/Tid
            CONF_SOLAR_PRODUCTION_SENSOR: SOLAR_PROD_SENSOR_ID,
            CONF_HOUSE_POWER_SENSOR: HOUSE_POWER_SENSOR_ID,
            CONF_SOLAR_SCHEDULE_ENTITY: None,  # Inget schema = alltid aktivt för Solenergi
            CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR: MAX_CURRENT_SENSOR_ID,
            CONF_CHARGER_DYNAMIC_CURRENT_SENSOR: DYN_CURRENT_SENSOR_ID,
            CONF_DEBUG_LOGGING: True,
        },
        entry_id="test_price_drop_scenario",
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.smart_ev_charging.coordinator.SmartEVChargingCoordinator._setup_listeners"
        ),
        patch(
            "custom_components.smart_ev_charging.coordinator.SmartEVChargingCoordinator._resolve_internal_entities",
            return_value=True,
        ),
    ):
        coordinator = SmartEVChargingCoordinator(hass, entry, 30)  # 30s scan interval

        coordinator.smart_enable_switch_entity_id = SMART_ENABLE_SWITCH_ID
        coordinator.max_price_entity_id = MAX_PRICE_NUMBER_ID
        coordinator.solar_enable_switch_entity_id = SOLAR_ENABLE_SWITCH_ID
        coordinator.solar_buffer_entity_id = SOLAR_BUFFER_NUMBER_ID
        coordinator.min_solar_charge_current_entity_id = MIN_SOLAR_CURRENT_NUMBER_ID
        coordinator._internal_entities_resolved = True

        # Externa sensorer
        hass.states.async_set(POWER_SWITCH_ID, STATE_ON)
        hass.states.async_set(PRICE_SENSOR_ID, "1.0")  # Initialt högt pris
        hass.states.async_set(SOLAR_PROD_SENSOR_ID, "8000")  # 8 kWh -> 8000W
        hass.states.async_set(HOUSE_POWER_SENSOR_ID, "500")  # 0.5 kWh -> 500W
        hass.states.async_set(
            MAX_CURRENT_SENSOR_ID, str(MAX_CHARGE_CURRENT_A_HW_DEFAULT)
        )  # 16A
        hass.states.async_set(
            DYN_CURRENT_SENSOR_ID, "6.0"
        )  # Initialt, kan vara vad som helst

        # Interna entiteter
        hass.states.async_set(SMART_ENABLE_SWITCH_ID, STATE_ON)  # Pris/Tid PÅ
        hass.states.async_set(MAX_PRICE_NUMBER_ID, "0.6")  # Max acceptabelt pris
        hass.states.async_set(SOLAR_ENABLE_SWITCH_ID, STATE_ON)  # Solenergi PÅ
        hass.states.async_set(SOLAR_BUFFER_NUMBER_ID, "0")  # Ingen buffert
        hass.states.async_set(
            MIN_SOLAR_CURRENT_NUMBER_ID, str(MIN_CHARGE_CURRENT_A)
        )  # 6A

        start_time_utc = datetime(2025, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
        hass.states.async_set(STATUS_SENSOR_ID, EASEE_STATUS_CHARGING)

        set_charger_dynamic_limit_calls = async_mock_service(
            hass, "easee", "set_charger_dynamic_limit"
        )

        resume_calls = async_mock_service(hass, "easee", EASEE_SERVICE_RESUME_CHARGING)

        # 2. ACT & ASSERT - Steg 1: Högt elpris, Solenergi aktiv
        print("TESTSTEG 1: Högt elpris (1.0 kr/kWh) - Solenergiladdning ska vara aktiv")

        # Simulera att SOLAR_SURPLUS_DELAY_SECONDS har passerat
        coordinator._solar_surplus_start_time = start_time_utc - timedelta(
            seconds=SOLAR_SURPLUS_DELAY_SECONDS + 1
        )
        coordinator._solar_session_active = False  # Låt logiken aktivera den

        with patch.object(dt_util, "utcnow", return_value=start_time_utc):
            await coordinator.async_refresh()
            await hass.async_block_till_done()

        assert coordinator.active_control_mode == CONTROL_MODE_SOLAR_SURPLUS, (
            f"Förväntade SOLENERGI (högt pris), fick {coordinator.active_control_mode}"
        )

        # Förväntad ström från sol: (8000W - 500W - 0W) / 230V = 7500W / 230V = ~32.6A
        # Begränsas av MAX_CHARGE_CURRENT_A_HW_DEFAULT (16A)
        calculated_current_3phase = math.floor(8000 / (3 * 230))  # 7500W / 690V = 10A
        expected_solar_current_initial = min(
            calculated_current_3phase, MAX_CHARGE_CURRENT_A_HW_DEFAULT
        )  # Ska bli min(10, 16) = 10A

        assert len(set_charger_dynamic_limit_calls) >= 1, (
            "set_dynamic_current anropades inte för solenergi initialt"
        )
        last_set_current_call = set_charger_dynamic_limit_calls[-1]
        assert (
            last_set_current_call.data["current"] == expected_solar_current_initial
        ), (
            f"Förväntade ström {expected_solar_current_initial}A för sol, fick {last_set_current_call.data['current']}A"
        )

        # Uppdatera DYN_CURRENT_SENSOR_ID med det värde som sattes
        hass.states.async_set(
            DYN_CURRENT_SENSOR_ID, str(float(expected_solar_current_initial))
        )

        set_charger_dynamic_limit_calls.clear()
        resume_calls.clear()

        # 3. ACT & ASSERT - Steg 2: Elpriset sjunker, Pris/Tid tar över
        print("TESTSTEG 2: Lågt elpris (0.5 kr/kWh) - Pris/Tid ska ta över")
        time_after_price_drop_utc = start_time_utc + timedelta(hours=1)

        hass.states.async_set(
            PRICE_SENSOR_ID, "0.5"
        )  # Priset sjunker under maxgränsen (0.6)
        hass.states.async_set(
            STATUS_SENSOR_ID, EASEE_STATUS_CHARGING
        )  # Fortfarande laddande

        with patch.object(dt_util, "utcnow", return_value=time_after_price_drop_utc):
            await coordinator.async_refresh()
            await hass.async_block_till_done()

        assert coordinator.active_control_mode == CONTROL_MODE_PRICE_TIME, (
            f"Förväntade PRIS_TID (lågt pris), fick {coordinator.active_control_mode}"
        )

        assert len(set_charger_dynamic_limit_calls) == 1, (
            "set_dynamic_current anropades inte eller fel antal gånger vid övergång till Pris/Tid"
        )

        # Strömmen ska nu sättas till hårdvarumax (16A)
        assert (
            set_charger_dynamic_limit_calls[0].data["current"]
            == MAX_CHARGE_CURRENT_A_HW_DEFAULT
        ), (
            f"Förväntade ström {MAX_CHARGE_CURRENT_A_HW_DEFAULT}A för Pris/Tid, fick {set_charger_dynamic_limit_calls[0].data['current']}A"
        )

        assert len(resume_calls) == 0, (
            "resume_charging anropades felaktigt när laddning redan pågick"
        )
