# tests/test_soc_limit_prevents_charging_start.py
"""
Test för att verifiera att laddning inte startar om SoC-gränsen redan är nådd.
"""

import pytest
import logging
from unittest.mock import patch

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
    CONF_EV_SOC_SENSOR,
    CONF_TARGET_SOC_LIMIT,
    CONF_DEBUG_LOGGING,  # Importera om den ska användas i MockConfigEntry
    EASEE_STATUS_READY_TO_CHARGE,
    CONTROL_MODE_MANUAL,
    ENTITY_ID_SUFFIX_SMART_ENABLE_SWITCH,
    ENTITY_ID_SUFFIX_MAX_PRICE_NUMBER,
    ENTITY_ID_SUFFIX_ENABLE_SOLAR_CHARGING_SWITCH,
    ENTITY_ID_SUFFIX_SOLAR_BUFFER_NUMBER,
    ENTITY_ID_SUFFIX_MIN_SOLAR_CHARGE_CURRENT_A_NUMBER,
)
from custom_components.smart_ev_charging.coordinator import SmartEVChargingCoordinator

# Mockade entitets-ID:n
MOCK_STATUS_SENSOR_ID = "sensor.test_charger_status_soc_prevent"
MOCK_PRICE_SENSOR_ID = "sensor.test_price_soc_prevent"
MOCK_SCHEDULE_ID = "schedule.test_charging_schedule_soc_prevent"
MOCK_SOC_SENSOR_ID = "sensor.test_ev_soc_soc_prevent"
MOCK_MAIN_POWER_SWITCH_ID = "switch.mock_charger_power_soc_prevent"

CONTROL_MODE_SENSOR_ID = "sensor.avancerad_elbilsladdning_aktivt_styrningslage"


@pytest.fixture(autouse=True)
def enable_debug_logging():
    # Sätt loggnivån till DEBUG för att fånga upp detaljerade loggar
    logging.getLogger(f"custom_components.{DOMAIN}").setLevel(logging.DEBUG)


async def test_charging_is_prevented_by_soc_limit(hass: HomeAssistant, caplog):
    """
    Testar att ingen laddning startar när SoC-gränsen är uppnådd,
    trots att villkoren för Pris/Tid-laddning är uppfyllda.

    SYFTE:
        Att säkerställa att SoC-gränsen har högsta prioritet och kan
        förhindra att en laddningssession initieras.

    FÖRUTSÄTTNINGAR (Arrange):
        - En fullständig konfiguration av integrationen skapas.
        - SoC-gränsen är satt till 85%.
        - Bilens faktiska SoC rapporteras vara 86% (dvs. över gränsen).
        - Alla andra villkor för att starta Pris/Tid-laddning är uppfyllda:
          lågt elpris, schema aktivt, smart-switch PÅ, och laddaren är redo.

    UTFÖRANDE (Act):
        - Koordinatorn kör en uppdatering.

    FÖRVÄNTAT RESULTAT (Assert):
        - Inga tjänsteanrop för att starta (`resume_charging`) eller sätta ström
          (`set_dynamic_current`) ska göras.
        - Det aktiva styrningsläget ska förbli manuellt ("AV").
        - Ett informativt meddelande ska loggas som förklarar varför laddning
          inte startas.
    """
    caplog.set_level(logging.DEBUG, logger="custom_components.smart_ev_charging")

    # --- 1. ARRANGE ---
    entry_id_for_test = "test_soc_prevent_start_entry"
    target_soc_limit = 85.0
    actual_soc = 86.0

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_CHARGER_DEVICE: "mock_device_soc_prevent",
            CONF_STATUS_SENSOR: MOCK_STATUS_SENSOR_ID,
            CONF_CHARGER_ENABLED_SWITCH_ID: MOCK_MAIN_POWER_SWITCH_ID,
            CONF_PRICE_SENSOR: MOCK_PRICE_SENSOR_ID,
            CONF_TIME_SCHEDULE_ENTITY: MOCK_SCHEDULE_ID,
            CONF_EV_SOC_SENSOR: MOCK_SOC_SENSOR_ID,
            CONF_TARGET_SOC_LIMIT: target_soc_limit,
            CONF_DEBUG_LOGGING: True,  # Försäkra att komponenten startar i debug-läge
        },
        entry_id=entry_id_for_test,
    )
    entry.add_to_hass(hass)

    # Ladda integrationen och vänta tills den är klar
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Hämta koordinator-instansen
    coordinator: SmartEVChargingCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    assert coordinator is not None

    # Manuell tilldelning av interna entitets-ID:n
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

    # Sätt upp förutsättningar för att Pris/Tid SKULLE ha startat
    hass.states.async_set(
        MOCK_STATUS_SENSOR_ID, EASEE_STATUS_READY_TO_CHARGE[0]
    )  # Laddaren är redo
    hass.states.async_set(smart_switch_id_dyn, STATE_ON)  # Smart laddning PÅ
    hass.states.async_set(
        solar_switch_id_dyn, STATE_OFF
    )  # Solenergi AV för att isolera
    hass.states.async_set(MOCK_PRICE_SENSOR_ID, "0.50")  # Lågt pris
    hass.states.async_set(max_price_id_dyn, "1.00")  # Maxpris är högre
    hass.states.async_set(MOCK_SCHEDULE_ID, STATE_ON)  # Schemat är aktivt
    hass.states.async_set(MOCK_MAIN_POWER_SWITCH_ID, STATE_ON)  # Huvudbrytare är PÅ

    # Mocka de interna entiteter som lades till ovan så att de har ett värde
    hass.states.async_set(solar_buffer_id_dyn, "200")
    hass.states.async_set(min_solar_current_id_dyn, "6")

    # Den kritiska förutsättningen: SoC är redan över gränsen
    hass.states.async_set(MOCK_SOC_SENSOR_ID, str(actual_soc))

    # Mocka tjänsteanrop
    set_current_calls = async_mock_service(hass, "easee", "set_charger_dynamic_limit")
    action_command_calls = async_mock_service(hass, "easee", "action_command")

    # --- 2. ACT ---
    caplog.clear()
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    # --- 3. ASSERT ---
    # Inga anrop för att starta eller pausa ska ha gjorts
    assert len(set_current_calls) == 0, "Laddning startades felaktigt."
    assert len(action_command_calls) == 0, (
        "Laddström sattes felaktigt när ingen laddning ska ske."
    )

    # Styrningsläget ska vara manuellt (AV)
    control_mode_state = hass.states.get(CONTROL_MODE_SENSOR_ID)
    assert control_mode_state is not None, (
        f"Sensor {CONTROL_MODE_SENSOR_ID} hittades inte."
    )
    assert control_mode_state.state == CONTROL_MODE_MANUAL, (
        f"Förväntade styrningsläge {CONTROL_MODE_MANUAL}, men fick {control_mode_state.state}."
    )

    # --- START PÅ DIAGNOSTIK ---
    print(f"DEBUG: Koordinatorns data efter refresh: {coordinator.data}")
    print(
        f"DEBUG: Koordinatorns active_control_mode: {coordinator.active_control_mode}"
    )
    print(f"DEBUG: Caplog text: '{caplog.text}'")
    all_log_records = "\n".join([record.getMessage() for record in caplog.records])
    print(f"DEBUG: Alla loggmeddelanden i caplog:\n{all_log_records}")
    # --- SLUT PÅ DIAGNOSTIK ---

    # Kontrollera att en förklarande loggpost finns
    expected_log_message = f"SoC ({actual_soc}%) har nått målet ({target_soc_limit}%)."
    assert expected_log_message in caplog.text, (
        "En förklarande loggpost om att SoC-gränsen har nåtts saknas."
    )
    print(f"\nTestet lyckades: Laddning förhindrades korrekt av SoC-gränsen.")
