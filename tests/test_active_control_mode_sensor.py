# tests/test_active_control_mode_sensor.py
"""
Tester för att verifiera att sensorn för aktivt styrningsläge
uppdateras korrekt baserat på koordinatorns beslut.
"""

import pytest
import logging
from datetime import timedelta

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
    CONF_CHARGER_ENABLED_SWITCH_ID,
    CONF_PRICE_SENSOR,
    CONF_TIME_SCHEDULE_ENTITY,
    CONF_SOLAR_PRODUCTION_SENSOR,
    CONF_HOUSE_POWER_SENSOR,
    CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR,
    EASEE_SERVICE_SET_DYNAMIC_CURRENT,
    EASEE_SERVICE_ACTION_COMMAND,
    CONTROL_MODE_PRICE_TIME,
    CONTROL_MODE_SOLAR_SURPLUS,
    CONTROL_MODE_MANUAL,
    MIN_CHARGE_CURRENT_A,
    SOLAR_SURPLUS_DELAY_SECONDS,
    EASEE_STATUS_READY_TO_CHARGE,
    ENTITY_ID_SUFFIX_SMART_ENABLE_SWITCH,
    ENTITY_ID_SUFFIX_MAX_PRICE_NUMBER,
    ENTITY_ID_SUFFIX_ENABLE_SOLAR_CHARGING_SWITCH,
    ENTITY_ID_SUFFIX_MIN_SOLAR_CHARGE_CURRENT_A_NUMBER,
    ENTITY_ID_SUFFIX_SOLAR_BUFFER_NUMBER,
    PHASES,  # Importerad för beräkning
    VOLTAGE_PHASE_NEUTRAL,  # Importerad för beräkning
)
from custom_components.smart_ev_charging.coordinator import SmartEVChargingCoordinator


# Mockade entitets-ID:n för externa sensorer
MOCK_PRICE_SENSOR_ID = "sensor.test_price_active_mode"
MOCK_SCHEDULE_ID = "schedule.test_charging_schedule_active_mode"
MOCK_SOLAR_PROD_SENSOR_ID = "sensor.test_solar_production_active_mode"
MOCK_HOUSE_POWER_SENSOR_ID = "sensor.test_house_power_active_mode"
MOCK_STATUS_SENSOR_ID = "sensor.test_charger_status_active_mode"
MOCK_CHARGER_MAX_LIMIT_ID = "sensor.mock_charger_max_limit_active_mode"
MOCK_MAIN_POWER_SWITCH_ID = "switch.mock_main_power_active_mode"

# Dynamiskt ID för sensorn som testas (förblir densamma över config entries)
CONTROL_MODE_SENSOR_ID_DYNAMIC = "sensor.avancerad_elbilsladdning_aktivt_styrningslage"


@pytest.fixture(autouse=True)
def enable_debug_logging():
    logging.getLogger(f"custom_components.{DOMAIN}").setLevel(logging.INFO)


async def test_active_control_mode_sensor_updates(hass: HomeAssistant, freezer):
    """
    Testar att sensorn 'Aktivt Styrningsläge' uppdateras korrekt för de olika
    styrningslägena: PRIS/TID, SOLENERGI och AV (Manuell).

    SYFTE:
        Att säkerställa att användaren i Home Assistant UI alltid kan se
        vilken logik som för närvarande styr laddningen, vilket är kritiskt
        för transparens och felsökning.
    """
    # --- 1. ARRANGE (Global Setup) ---
    # SYFTE: Sätt upp en fullständig konfiguration av integrationen.
    entry_id_for_test = "test_control_mode_sensor_entry"
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_CHARGER_DEVICE: "mock_device_active_mode",
            CONF_STATUS_SENSOR: MOCK_STATUS_SENSOR_ID,
            CONF_CHARGER_ENABLED_SWITCH_ID: MOCK_MAIN_POWER_SWITCH_ID,
            CONF_PRICE_SENSOR: MOCK_PRICE_SENSOR_ID,
            CONF_TIME_SCHEDULE_ENTITY: MOCK_SCHEDULE_ID,
            CONF_SOLAR_PRODUCTION_SENSOR: MOCK_SOLAR_PROD_SENSOR_ID,
            CONF_HOUSE_POWER_SENSOR: MOCK_HOUSE_POWER_SENSOR_ID,
            CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR: MOCK_CHARGER_MAX_LIMIT_ID,
        },
        entry_id=entry_id_for_test,
    )
    entry.add_to_hass(hass)

    # Ladda integrationen och vänta tills den är klar.
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Hämta koordinator-instansen.
    coordinator: SmartEVChargingCoordinator = hass.data[DOMAIN][entry.entry_id].get(
        "coordinator"
    )
    assert coordinator is not None

    # Manuell tilldelning av interna entitets-ID:n.
    smart_switch_id_dyn = (
        f"switch.{DOMAIN}_{entry_id_for_test}_{ENTITY_ID_SUFFIX_SMART_ENABLE_SWITCH}"
    )
    max_price_id_dyn = (
        f"number.{DOMAIN}_{entry_id_for_test}_{ENTITY_ID_SUFFIX_MAX_PRICE_NUMBER}"
    )
    solar_switch_id_dyn = f"switch.{DOMAIN}_{entry_id_for_test}_{ENTITY_ID_SUFFIX_ENABLE_SOLAR_CHARGING_SWITCH}"
    solar_buffer_id_dyn = (
        f"number.{DOMAIN}_{entry_id_for_test}_{ENTITY_ID_SUFFIX_SOLAR_BUFFER_NUMBER}"
    )
    min_solar_current_id_dyn = f"number.{DOMAIN}_{entry_id_for_test}_{ENTITY_ID_SUFFIX_MIN_SOLAR_CHARGE_CURRENT_A_NUMBER}"

    coordinator.smart_enable_switch_entity_id = smart_switch_id_dyn
    coordinator.max_price_entity_id = max_price_id_dyn
    coordinator.solar_enable_switch_entity_id = solar_switch_id_dyn
    coordinator.solar_buffer_entity_id = solar_buffer_id_dyn
    coordinator.min_solar_charge_current_entity_id = min_solar_current_id_dyn
    coordinator._internal_entities_resolved = True

    # Mocka externa sensorer och tjänsteanrop.
    hass.states.async_set(MOCK_CHARGER_MAX_LIMIT_ID, "16")
    hass.states.async_set(MOCK_MAIN_POWER_SWITCH_ID, STATE_ON)
    async_mock_service(
        hass, "easee", EASEE_SERVICE_SET_DYNAMIC_CURRENT
    )  # För set_charger_dynamic_limit
    async_mock_service(
        hass, "easee", EASEE_SERVICE_ACTION_COMMAND
    )  # För action_command (start/pause)


    # --- 2. TESTSTEG 1: PRIS/TID ---
    # SYFTE: Verifiera att sensorn visar PRIS_TID när dessa villkor är uppfyllda.
    print("\nTESTSTEG 1: Verifierar PRIS/TID-läge")
    # FÖRUTSÄTTNINGAR: Laddare redo, lågt pris, maxpris högre, smart-switch PÅ, schema PÅ, sol-switch AV.
    hass.states.async_set(MOCK_STATUS_SENSOR_ID, EASEE_STATUS_READY_TO_CHARGE[0])
    hass.states.async_set(MOCK_PRICE_SENSOR_ID, "0.50")
    hass.states.async_set(max_price_id_dyn, "1.00")
    hass.states.async_set(smart_switch_id_dyn, STATE_ON)
    hass.states.async_set(MOCK_SCHEDULE_ID, STATE_ON)
    hass.states.async_set(solar_switch_id_dyn, STATE_OFF)

    # UTFÖRANDE: Kör en uppdatering.
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    # FÖRVÄNTAT RESULTAT: Sensorn ska visa PRIS_TID.
    sensor_state = hass.states.get(CONTROL_MODE_SENSOR_ID_DYNAMIC)
    assert sensor_state is not None, (
        f"Sensorn {CONTROL_MODE_SENSOR_ID_DYNAMIC} hittades inte."
    )
    assert sensor_state.state == CONTROL_MODE_PRICE_TIME, (
        f"Förväntade {CONTROL_MODE_PRICE_TIME}, men fick {sensor_state.state}"
    )
    print(f"OK: Sensorns status är {sensor_state.state}")

    # --- 3. TESTSTEG 2: SOLENERGI ---
    # SYFTE: Verifiera att sensorn visar SOLENERGI när dessa villkor är uppfyllda.
    print("\nTESTSTEG 2: Verifierar SOLENERGI-läge")
    # FÖRUTSÄTTNINGAR: Högt pris (för att P/T inte ska vara aktivt), sol-switch PÅ, P/T-switch AV,
    #                 god solproduktion, låg husförbrukning, buffer och minsta ström satta.
    hass.states.async_set(MOCK_PRICE_SENSOR_ID, "2.00")
    hass.states.async_set(solar_switch_id_dyn, STATE_ON)
    hass.states.async_set(smart_switch_id_dyn, STATE_OFF)
    hass.states.async_set(
        MOCK_SOLAR_PROD_SENSOR_ID, "7000", {"unit_of_measurement": UnitOfPower.WATT}
    )
    hass.states.async_set(
        MOCK_HOUSE_POWER_SENSOR_ID, "500", {"unit_of_measurement": UnitOfPower.WATT}
    )
    hass.states.async_set(solar_buffer_id_dyn, "300")
    hass.states.async_set(
        min_solar_current_id_dyn, str(MIN_CHARGE_CURRENT_A)
    )  # Använd konstanten
    hass.states.async_set(
        MOCK_STATUS_SENSOR_ID, EASEE_STATUS_READY_TO_CHARGE[0]
    )  # Säkerställ att laddaren är redo

    coordinator._solar_session_active = False  # Nollställ för testet

    # UTFÖRANDE Steg 1: Kör en första refresh för att initiera fördröjningstimern.
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    sensor_state_solar = hass.states.get(CONTROL_MODE_SENSOR_ID_DYNAMIC)
    assert sensor_state_solar is not None
    assert sensor_state_solar.state == CONTROL_MODE_SOLAR_SURPLUS, (
        f"Förväntade {CONTROL_MODE_SOLAR_SURPLUS} direkt, men fick {sensor_state_solar.state}"
    )
    print(f"OK: Sensorns status är {sensor_state_solar.state}")

    # --- 4. TESTSTEG 3: AV (Manuell) ---
    # SYFTE: Verifiera att sensorn visar AV när inga smarta lägen är aktiva.
    print("\nTESTSTEG 3: Verifierar AV (Manuell)-läge")
    # FÖRUTSÄTTNINGAR: Både P/T-switch och sol-switch ställs till AV.
    hass.states.async_set(smart_switch_id_dyn, STATE_OFF)
    hass.states.async_set(solar_switch_id_dyn, STATE_OFF)

    # UTFÖRANDE: Kör en uppdatering.
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    # FÖRVÄNTAT RESULTAT: Sensorn ska visa AV.
    sensor_state_manual = hass.states.get(CONTROL_MODE_SENSOR_ID_DYNAMIC)
    assert sensor_state_manual is not None
    assert sensor_state_manual.state == CONTROL_MODE_MANUAL, (
        f"Förväntade {CONTROL_MODE_MANUAL}, men fick {sensor_state_manual.state}"
    )
    print(f"OK: Sensorns status är {sensor_state_manual.state}")
