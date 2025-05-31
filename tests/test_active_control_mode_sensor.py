# tests/test_active_control_mode_sensor.py
"""
Tester för att verifiera att sensorn för aktivt styrningsläge
uppdateras korrekt baserat på koordinatorns beslut.
"""

import pytest
# from unittest.mock import patch # Tas bort då den inte används i denna version

from homeassistant.core import HomeAssistant
from homeassistant.const import STATE_ON, STATE_OFF

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
    EASEE_SERVICE_PAUSE_CHARGING,
    EASEE_SERVICE_RESUME_CHARGING,
    # ENTITY_ID_SUFFIX_SMART_ENABLE_SWITCH, # Används inte direkt för ID-konstruktion nu
    # ENTITY_ID_SUFFIX_MAX_PRICE_NUMBER,
    # ENTITY_ID_SUFFIX_ENABLE_SOLAR_CHARGING_SWITCH,
    # ENTITY_ID_SUFFIX_MIN_SOLAR_CHARGE_CURRENT_A_NUMBER,
    # ENTITY_ID_SUFFIX_SOLAR_BUFFER_NUMBER,
    # ENTITY_ID_SUFFIX_ACTIVE_CONTROL_MODE_SENSOR, # Används inte direkt för ID-konstruktion nu
    CONTROL_MODE_PRICE_TIME,
    CONTROL_MODE_SOLAR_SURPLUS,
    CONTROL_MODE_MANUAL,
    # DEFAULT_NAME, # Används inte direkt för ID-konstruktion nu
    MIN_CHARGE_CURRENT_A,
)

# Skapa mockade entitets-ID:n för externa sensorer
MOCK_PRICE_SENSOR_ID = "sensor.test_price"
MOCK_SCHEDULE_ID = "schedule.test_charging_schedule"
MOCK_SOLAR_PROD_SENSOR_ID = "sensor.test_solar_production"
MOCK_HOUSE_POWER_SENSOR_ID = "sensor.test_house_power"
MOCK_STATUS_SENSOR_ID = "sensor.test_charger_status"
MOCK_CHARGER_MAX_LIMIT_ID = "sensor.mock_charger_max_limit"  # För konfigurationen

# Definiera de faktiska entitets-ID:na som Home Assistant kommer att skapa
# Dessa baseras på hur entiteternas `_attr_name` slugifieras.
SMART_SWITCH_ID = "switch.avancerad_elbilsladdning_smart_laddning_aktiv"
MAX_PRICE_ID = "number.avancerad_elbilsladdning_max_elpris"
SOLAR_SWITCH_ID = "switch.avancerad_elbilsladdning_aktivera_solenergiladdning"
SOLAR_BUFFER_ID = "number.avancerad_elbilsladdning_solenergi_buffer"
MIN_SOLAR_CURRENT_ID = "number.avancerad_elbilsladdning_minsta_laddstrom_solenergi"
CONTROL_MODE_SENSOR_ID = "sensor.avancerad_elbilsladdning_aktivt_styrningslage"


async def test_active_control_mode_sensor_updates(hass: HomeAssistant):
    """
    Testar att sensorn 'Aktivt Styrningsläge' uppdateras korrekt för de olika
    styrningslägena: PRIS/TID, SOLENERGI och AV (Manuell).

    SYFTE:
        Att säkerställa att användaren i Home Assistant UI alltid kan se
        vilken logik som för närvarande styr laddningen, vilket är kritiskt
        för transparens och felsökning.

    FÖRUTSÄTTNINGAR (Arrange):
        - En fullständig konfiguration av integrationen skapas, inklusive
          alla nödvändiga sensorer för både Pris/Tid och Solenergi.
        - Integrationen laddas fullständigt via `async_setup_entry` så att
          alla entiteter, inklusive sensorn för aktivt styrningsläge, skapas.
        - Tjänsteanrop till laddaren (start, stopp, etc.) är mockade för att
          isolera testet till koordinatorns logik och sensorns tillstånd.

    UTFÖRANDE (Act) & FÖRVÄNTAT RESULTAT (Assert) - Stegvis:
        1.  **PRIS/TID-läge:**
            - Parametrar sätts för att uppfylla villkoren för Pris/Tid-laddning
              (lågt pris, aktivt schema, smart-switch PÅ, sol-switch AV).
            - En uppdatering av koordinatorn triggas.
            - FÖRVÄNTAT: Sensorns tillstånd ska bli `CONTROL_MODE_PRICE_TIME`.

        2.  **SOLENERGI-läge:**
            - Parametrar ändras för att istället uppfylla villkoren för
              Solenergiladdning (högt pris, tillräcklig solproduktion,
              sol-switch PÅ).
            - En uppdatering av koordinatorn triggas.
            - FÖRVÄNTAT: Sensorns tillstånd ska uppdateras till `CONTROL_MODE_SOLAR_SURPLUS`.

        3.  **AV (Manuell)-läge:**
            - Parametrar ändras så att inga smarta laddningsvillkor är uppfyllda
              (både smart-switch och sol-switch ställs till AV).
            - En uppdatering av koordinatorn triggas.
            - FÖRVÄNTAT: Sensorns tillstånd ska uppdateras till `CONTROL_MODE_MANUAL`.
    """
    # --- 1. ARRANGE (Global Setup) ---
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_CHARGER_DEVICE: "mock_device_id",
            CONF_STATUS_SENSOR: MOCK_STATUS_SENSOR_ID,
            CONF_CHARGER_ENABLED_SWITCH_ID: "switch.mock_charger_power",
            CONF_PRICE_SENSOR: MOCK_PRICE_SENSOR_ID,
            CONF_TIME_SCHEDULE_ENTITY: MOCK_SCHEDULE_ID,
            CONF_SOLAR_PRODUCTION_SENSOR: MOCK_SOLAR_PROD_SENSOR_ID,
            CONF_HOUSE_POWER_SENSOR: MOCK_HOUSE_POWER_SENSOR_ID,
            CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR: MOCK_CHARGER_MAX_LIMIT_ID,
        },
        entry_id="test_control_mode_sensor",
    )
    entry.add_to_hass(hass)

    # Mocka externa sensorer som används av koordinatorn
    hass.states.async_set(MOCK_CHARGER_MAX_LIMIT_ID, "16")  # Sätt ett värde för denna

    # Mocka tjänsteanrop
    async_mock_service(hass, "easee", EASEE_SERVICE_SET_DYNAMIC_CURRENT)
    async_mock_service(hass, "easee", EASEE_SERVICE_PAUSE_CHARGING)
    async_mock_service(hass, "easee", EASEE_SERVICE_RESUME_CHARGING)

    # Ladda integrationen fullständigt för att skapa alla entiteter
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator_data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    coordinator = coordinator_data.get("coordinator")
    assert coordinator is not None

    # --- 2. TESTSTEG 1: PRIS/TID ---
    print("\nTESTSTEG 1: Verifierar PRIS/TID-läge")
    hass.states.async_set(MOCK_STATUS_SENSOR_ID, "ready_to_charge")
    hass.states.async_set(MOCK_PRICE_SENSOR_ID, "0.50")
    hass.states.async_set(MAX_PRICE_ID, "1.00")
    hass.states.async_set(SMART_SWITCH_ID, STATE_ON)
    hass.states.async_set(MOCK_SCHEDULE_ID, STATE_ON)
    hass.states.async_set(SOLAR_SWITCH_ID, STATE_OFF)

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    sensor_state = hass.states.get(CONTROL_MODE_SENSOR_ID)
    assert sensor_state is not None, f"Sensorn {CONTROL_MODE_SENSOR_ID} hittades inte."
    assert sensor_state.state == CONTROL_MODE_PRICE_TIME, (
        f"Förväntade {CONTROL_MODE_PRICE_TIME}, men fick {sensor_state.state}"
    )
    print(f"OK: Sensorns status är {sensor_state.state}")

    # --- 3. TESTSTEG 2: SOLENERGI ---
    print("\nTESTSTEG 2: Verifierar SOLENERGI-läge")
    hass.states.async_set(MOCK_PRICE_SENSOR_ID, "2.00")
    hass.states.async_set(SOLAR_SWITCH_ID, STATE_ON)
    hass.states.async_set(SMART_SWITCH_ID, STATE_OFF)
    hass.states.async_set(MOCK_SOLAR_PROD_SENSOR_ID, "5000")
    hass.states.async_set(MOCK_HOUSE_POWER_SENSOR_ID, "500")
    hass.states.async_set(SOLAR_BUFFER_ID, "300")
    hass.states.async_set(MIN_SOLAR_CURRENT_ID, str(MIN_CHARGE_CURRENT_A))

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    sensor_state = hass.states.get(CONTROL_MODE_SENSOR_ID)
    assert sensor_state is not None
    assert sensor_state.state == CONTROL_MODE_SOLAR_SURPLUS, (
        f"Förväntade {CONTROL_MODE_SOLAR_SURPLUS}, men fick {sensor_state.state}"
    )
    print(f"OK: Sensorns status är {sensor_state.state}")

    # --- 4. TESTSTEG 3: AV (Manuell) ---
    print("\nTESTSTEG 3: Verifierar AV (Manuell)-läge")
    hass.states.async_set(SMART_SWITCH_ID, STATE_OFF)
    hass.states.async_set(SOLAR_SWITCH_ID, STATE_OFF)

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    sensor_state = hass.states.get(CONTROL_MODE_SENSOR_ID)
    assert sensor_state is not None
    assert sensor_state.state == CONTROL_MODE_MANUAL, (
        f"Förväntade {CONTROL_MODE_MANUAL}, men fick {sensor_state.state}"
    )
    print(f"OK: Sensorns status är {sensor_state.state}")
