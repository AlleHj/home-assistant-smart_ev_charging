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
    """  # noqa: D212

    # 1. ARRANGE (Förbered)
    # Skapa en mockad konfiguration, som om en användare fyllt i formuläret.
    mock_config = {
        CONF_CHARGER_DEVICE: "mock_device_id",
        CONF_STATUS_SENSOR: "sensor.mock_charger_status",
        CONF_CHARGER_ENABLED_SWITCH_ID: "switch.mock_charger_power",
        CONF_PRICE_SENSOR: "sensor.mock_nordpool",
    }

    # Skapa en fejkad ConfigEntry i Home Assistant
    entry = MockConfigEntry(domain=DOMAIN, data=mock_config, entry_id="test_entry_1")
    entry.add_to_hass(hass)

    # "Mocka" de externa sensorer som din integration kräver för att starta.
    hass.states.async_set("sensor.mock_charger_status", "disconnected")
    hass.states.async_set("switch.mock_charger_power", STATE_ON)
    hass.states.async_set("sensor.mock_nordpool", "1.23")

    # 2. ACT (Agera)
    # Nu startar vi uppsättningen av integrationen
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # 3. ASSERT (Verifiera)
    # Kontrollera att integrationen har laddats
    assert entry.state is ConfigEntryState.LOADED

    # Kontrollera att en av dina switchar har skapats
    state = hass.states.get("switch.avancerad_elbilsladdning_smart_laddning_aktiv")
    assert state is not None
    assert state.state == STATE_OFF

    # 4. TEARDOWN (Städning)
    # Avlasta integrationen
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
