# tests/test_loggning_vid_frånkoppling.py
"""
Tester för att verifiera korrekt logghantering och tillståndsåterställning
när en pågående laddningssession avbryts genom att bilen kopplas från.
"""

import pytest
import logging
from unittest.mock import patch
from datetime import datetime, timezone

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
    CONF_TIME_SCHEDULE_ENTITY,
    EASEE_STATUS_CHARGING,
    EASEE_STATUS_DISCONNECTED,
    CONTROL_MODE_MANUAL,
    CONTROL_MODE_PRICE_TIME,
)
from custom_components.smart_ev_charging.coordinator import SmartEVChargingCoordinator

# Mockade entitets-ID:n för externa sensorer
MOCK_PRICE_SENSOR_ID = "sensor.test_price_disconnect"
MOCK_SCHEDULE_ID = "schedule.test_charging_schedule_disconnect"
MOCK_STATUS_SENSOR_ID = "sensor.test_charger_status_disconnect"

# Definiera de faktiska entitets-ID:na som Home Assistant kommer att skapa
SMART_SWITCH_ID = "switch.avancerad_elbilsladdning_smart_laddning_aktiv"
SOLAR_SWITCH_ID = "switch.avancerad_elbilsladdning_aktivera_solenergiladdning"
CONTROL_MODE_SENSOR_ID = "sensor.avancerad_elbilsladdning_aktivt_styrningslage"
MAX_PRICE_ID = "number.avancerad_elbilsladdning_max_elpris"


@pytest.fixture(autouse=True)
def enable_debug_logging():
    """Aktivera debug-loggning för att fånga alla relevanta meddelanden."""
    logging.getLogger(f"custom_components.{DOMAIN}").setLevel(logging.INFO)


async def test_logging_and_state_on_disconnect(hass: HomeAssistant, caplog):
    """
    Testar att loggningen är korrekt och inte upprepas vid frånkoppling.

    SYFTE:
        Att verifiera att:
        1. När en bil som laddar kopplas från, loggas "Återställer sessionsdata"
           EN GÅNG.
        2. Efterföljande uppdateringar, medan bilen fortfarande är frånkopplad,
           INTE genererar nya loggmeddelanden om återställning eller varningar
           om att laddning begärs.
        3. Sensorn för aktivt styrningsläge korrekt återställs till "AV"
           (CONTROL_MODE_MANUAL).

    FÖRUTSÄTTNINGAR (Arrange):
        - Båda smarta laddningsswitcharna är PÅ.
        - Villkoren för Pris/Tid-laddning är uppfyllda (lågt pris, schema PÅ).
        - En laddningssession simuleras som aktiv (`coordinator.session_start_time_utc` är satt).
        - Laddaren är initialt i status 'charging'.

    UTFÖRANDE (Act) & FÖRVÄNTAT RESULTAT (Assert):
        - Steg 1 (Frånkoppling):
            - Status ändras från 'charging' till 'disconnected'.
            - Koordinatorn uppdateras.
            - FÖRVÄNTAT: Loggen ska innehålla "Återställer sessionsdata..." exakt en gång.
            - FÖRVÄNTAT: Sensorn för styrningsläge ska bli "AV".
            - FÖRVÄNTAT: Koordinatorns interna sessionsvariabel ska nollställas.

        - Steg 2 (Repeterad kontroll):
            - Koordinatorn uppdateras igen, med status fortfarande 'disconnected'.
            - FÖRVÄNTAT: Inga nya relevanta varnings- eller infomeddelanden ska loggas.
    """
    # --- 1. ARRANGE ---
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_CHARGER_DEVICE: "mock_device_disconnect",
            CONF_STATUS_SENSOR: MOCK_STATUS_SENSOR_ID,
            CONF_CHARGER_ENABLED_SWITCH_ID: "switch.mock_charger_power_disconnect",
            CONF_PRICE_SENSOR: MOCK_PRICE_SENSOR_ID,
            CONF_TIME_SCHEDULE_ENTITY: MOCK_SCHEDULE_ID,
        },
        entry_id="test_disconnect_logging",
    )
    entry.add_to_hass(hass)

    # Ladda integrationen fullständigt för att skapa alla entiteter
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator_data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    coordinator: SmartEVChargingCoordinator = coordinator_data.get("coordinator")
    assert coordinator is not None

    # Sätt initiala tillstånd för att starta en Pris/Tid-laddning
    hass.states.async_set(MOCK_STATUS_SENSOR_ID, EASEE_STATUS_CHARGING)
    hass.states.async_set(MOCK_PRICE_SENSOR_ID, "0.50")
    hass.states.async_set(MAX_PRICE_ID, "1.00")
    hass.states.async_set(SMART_SWITCH_ID, STATE_ON)
    hass.states.async_set(SOLAR_SWITCH_ID, STATE_ON)  # Per instruktion
    hass.states.async_set(MOCK_SCHEDULE_ID, STATE_ON)

    # Simulera en aktiv session
    coordinator.session_start_time_utc = dt_util.utcnow()
    coordinator.active_control_mode_internal = CONTROL_MODE_PRICE_TIME

    # # Kör en första refresh för att säkerställa att allt är som det ska
    # await coordinator.async_refresh()
    # await hass.async_block_till_done()

    # --- 2. ACT & ASSERT - Steg 1: Bilen kopplas från ---
    print("\nTESTSTEG 1: Bilen kopplas från under pågående laddning")
    caplog.clear()  # Rensa eventuella tidigare loggar

    # Ändra status till frånkopplad
    hass.states.async_set(MOCK_STATUS_SENSOR_ID, EASEE_STATUS_DISCONNECTED[0])

    # Kör en uppdatering
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    # Verifiera att styrningsläget har återställts
    sensor_state = hass.states.get(CONTROL_MODE_SENSOR_ID)
    assert sensor_state is not None
    assert sensor_state.state == CONTROL_MODE_MANUAL

    # Verifiera att loggmeddelandet kom exakt en gång
    reset_session_log_msg = "Återställer sessionsdata. Anledning: Laddaren är frånkopplad/offline (status: disconnected)."
    log_count = caplog.text.count(reset_session_log_msg)
    assert log_count == 1, (
        f"Förväntade att sessionsdata skulle återställas exakt en gång, men det loggades {log_count} gånger."
    )

    # Verifiera att den interna sessionstiden har nollställts (VIKTIGT för att förhindra framtida spam)
    # OBS: Detta kräver att `_reset_session_data` sätter `session_start_time_utc` till None.
    assert coordinator.session_start_time_utc is None, (
        "Koordinatorns sessionstid borde vara None efter frånkoppling."
    )

    # --- 3. ACT & ASSERT - Steg 2: Efterföljande kontroll ---
    print("\nTESTSTEG 2: Kör en till uppdatering medan bilen är frånkopplad")
    caplog.clear()  # Rensa loggen inför andra körningen

    # Kör uppdateringen IGEN
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    # Verifiera att INGA nya meddelanden har loggats
    assert reset_session_log_msg not in caplog.text, (
        "Loggmeddelandet om återställning av session upprepades felaktigt."
    )

    warning_log_msg = "Laddning begärd, men laddaren är frånkopplad/offline"
    assert warning_log_msg not in caplog.text, (
        "Varningsmeddelande om frånkopplad laddare upprepades felaktigt."
    )

    print("\nTestet slutfört framgångsrikt!")
