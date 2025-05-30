"""Tester för grundläggande setup och unload av Smart EV Charging-integrationen."""

from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_ON, STATE_OFF

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_ev_charging.const import (
    DOMAIN,
    CONF_CHARGER_DEVICE,
    CONF_STATUS_SENSOR,
    CONF_CHARGER_ENABLED_SWITCH_ID,
    CONF_PRICE_SENSOR,
    CONF_DEBUG_LOGGING,
)


async def test_load_and_unload_entry(hass: HomeAssistant):
    """
    Testar att integrationen kan laddas och avladdas korrekt.

    SYFTE:
        Att verifiera den mest grundläggande livscykeln för integrationen:
        att den kan initieras baserat på en konfiguration och sedan
        stängas ner utan fel.

    FÖRUTSÄTTNINGAR (Arrange):
        - En mockad ConfigEntry skapas med de obligatoriska fälten ifyllda.
        - Debug-loggning är aktiverat i konfigurationen.
        - De externa sensorer som krävs för uppstart (status, power, pris)
          får initiala, giltiga tillstånd i den virtuella Home Assistant-instansen.

    UTFÖRANDE (Act):
        - `hass.config_entries.async_setup()` anropas för att starta integrationen.
        - `hass.config_entries.async_unload()` anropas för att stänga ner den.

    FÖRVÄNTAT RESULTAT (Assert):
        - Efter setup ska integrationens status vara `LOADED`.
        - En av de entiteter som integrationen skapar (t.ex. smart-laddning switchen)
          ska finnas i Home Assistant och ha sitt standardtillstånd (AV).
        - Efter unload ska integrationens status vara `NOT_LOADED`.
    """

    # 1. ARRANGE (Förbered)
    mock_config = {
        CONF_CHARGER_DEVICE: "mock_device_id",
        CONF_STATUS_SENSOR: "sensor.mock_charger_status",
        CONF_CHARGER_ENABLED_SWITCH_ID: "switch.mock_charger_power",
        CONF_PRICE_SENSOR: "sensor.mock_nordpool",
        CONF_DEBUG_LOGGING: True,
    }

    entry = MockConfigEntry(domain=DOMAIN, data=mock_config, entry_id="test_entry_1")
    entry.add_to_hass(hass)

    hass.states.async_set("sensor.mock_charger_status", "disconnected")
    hass.states.async_set("switch.mock_charger_power", STATE_ON)
    hass.states.async_set("sensor.mock_nordpool", "1.23")

    # 2. ACT (Agera)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # 3. ASSERT (Verifiera)
    assert entry.state is ConfigEntryState.LOADED
    state = hass.states.get("switch.avancerad_elbilsladdning_smart_laddning_aktiv")
    assert state is not None
    assert state.state == STATE_OFF

    # 4. TEARDOWN (Städning)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
