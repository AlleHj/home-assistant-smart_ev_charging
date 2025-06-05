# test_config_flow_and_options_persistence.py
"""
Testar hela flödet från initial konfiguration till ändringar via alternativ,
med fokus på att verifiera att valda sensorer och värden sparas och
återläses korrekt.
"""

import pytest
import random
import logging
from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import STATE_ON, STATE_OFF

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_ev_charging.const import (
    DOMAIN,
    CONF_CHARGER_DEVICE,
    CONF_STATUS_SENSOR,
    CONF_CHARGER_ENABLED_SWITCH_ID,
    CONF_PRICE_SENSOR,
    CONF_EV_SOC_SENSOR,
    CONF_TARGET_SOC_LIMIT,
    CONF_SCAN_INTERVAL,
    CONF_DEBUG_LOGGING,
    DEFAULT_SCAN_INTERVAL_SECONDS,
    CONF_TIME_SCHEDULE_ENTITY,
    CONF_HOUSE_POWER_SENSOR,
    CONF_SOLAR_PRODUCTION_SENSOR,
    CONF_SOLAR_SCHEDULE_ENTITY,
    CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR,
    CONF_CHARGER_DYNAMIC_CURRENT_SENSOR,
)
# from custom_components.smart_ev_charging.config_flow import (
#     OPTIONAL_ENTITY_CONF_KEYS # Används inte explicit just nu, men bra att ha om man itererar
# )


MOCK_EASEE_DEVICE_ID = "easee_mock_device_for_flow_test"
MOCK_STATUS_SENSOR_ID = "sensor.mock_charger_status_flow"
MOCK_POWER_SWITCH_ID = "switch.mock_charger_power_flow"
MOCK_PRICE_SENSOR_ID = "sensor.mock_price_sensor_flow"
MOCK_SOC_SENSOR_ID_INITIAL = "sensor.mock_ev_soc_initial"
MOCK_SURCHARGE_HELPER_ID = "input_number.mock_surcharge"
MOCK_TIME_SCHEDULE_ID = "schedule.mock_charging_time"
MOCK_HOUSE_POWER_ID = "sensor.mock_house_power"
MOCK_SOLAR_PROD_ID = "sensor.mock_solar_production"
MOCK_SOLAR_SCHEDULE_ID = "schedule.mock_solar_time"
MOCK_MAX_CURRENT_LIMIT_ID = "sensor.mock_charger_max_limit"
MOCK_DYN_CURRENT_LIMIT_ID = "sensor.mock_charger_dyn_limit"


@pytest.fixture(autouse=True)
def enable_debug_logging():
    logging.getLogger(f"custom_components.{DOMAIN}").setLevel(logging.DEBUG)
    logging.getLogger("homeassistant.config_entries").setLevel(logging.DEBUG)


async def test_setup_and_options_modification_flow(hass: HomeAssistant):
    """
    Testar konfigurationsflödet (initial setup) och alternativflödet,
    med fokus på persistens av data.

    SYFTE:
        Att verifiera att:
        1. Integrationen kan konfigureras initialt med specifika värden,
           inklusive obligatoriska fält, en SoC-sensor och en slumpmässigt
           angiven SoC-gräns.
        2. De initialt angivna värdena sparas korrekt i `ConfigEntry.data`.
        3. Alternativflödet kan öppnas och korrekt reflektera de initialt
           sparade värdena (implicit genom att formuläret byggs från `entry.data`
           och initialt tomma `entry.options`).
        4. Värden kan modifieras i alternativflödet:
            a. En befintlig sensor (SoC-sensorn) kan tas bort (sättas till None).
            b. En ny sensor (EV Power-sensor) kan läggas till.
        5. De modifierade värdena sparas korrekt i `ConfigEntry.options`.
        6. Om alternativflödet öppnas igen, reflekterar det de senast sparade
           ändringarna från `ConfigEntry.options`.

    FÖRUTSÄTTNINGAR (Arrange):
        - Nödvändiga mock-entiteter (sensorer, switchar) sätts upp i `hass.states`
          för att simulera en miljö där konfigurationsfälten kan populeras.
        - En slumpmässig SoC-gräns mellan 50% och 90% genereras.

    UTFÖRANDE (Act) & FÖRVÄNTAT RESULTAT (Assert) - Stegvis:
        1. INITIAL SETUP:
           - Starta konfigurationsflödet för `smart_ev_charging`.
           - Mata in värden för obligatoriska fält, `CONF_EV_SOC_SENSOR` och den
             slumpade `CONF_TARGET_SOC_LIMIT`. Andra valfria fält lämnas tomma (None).
           - Slutför flödet.
           - FÖRVÄNTAT: En `ConfigEntry` skapas. `entry.data` ska innehålla de
             angivna värdena. `entry.options` ska vara tom.

        2. ÖPPNA OPTIONS (Första kontrollen):
           - Initiera alternativflödet för den skapade `ConfigEntry`.
           - FÖRVÄNTAT: Flödet ska starta och visa ett formulär. Detta formulär
             ska (implicit) vara populerat baserat på `entry.data`.

        3. MODIFIERA OPTIONS:
           - I det öppnade alternativflödet, förbered ny input:
             - `CONF_EV_SOC_SENSOR` sätts till `None` (simulerar borttagning).
             - `CONF_CHARGER_DYNAMIC_CURRENT_SENSOR` får ett nytt sensor-ID.
             - Andra tidigare ifyllda värden (som SoC-gräns och obligatoriska fält)
               behålls. Ytterligare valfria fält fylls i med mock-värden för
               att simulera ett mer komplett formulär, då options-flödet sparar alla fält.
           - Skicka in den modifierade datan.
           - Slutför flödet.
           - FÖRVÄNTAT: Alternativen sparas. `entry.options` ska nu innehålla
             alla fält, med de gjorda ändringarna (SoC-sensor är None, EV Power-sensor
             är ifylld, SoC-gräns är oförändrad).

        4. ÖPPNA OPTIONS (Andra kontrollen):
           - Initiera alternativflödet igen för samma `ConfigEntry`.
           - FÖRVÄNTAT: Flödet ska starta och visa ett formulär. Detta formulär
             ska (implicit) vara populerat baserat på de senast sparade värdena
             i `entry.options`.
    """  # noqa: D205, D212
    hass.states.async_set(MOCK_STATUS_SENSOR_ID, "charging")
    hass.states.async_set(MOCK_POWER_SWITCH_ID, STATE_ON)
    hass.states.async_set(MOCK_PRICE_SENSOR_ID, "0.50")
    hass.states.async_set(MOCK_SOC_SENSOR_ID_INITIAL, "75")
    hass.states.async_set(MOCK_SURCHARGE_HELPER_ID, "0.1")
    hass.states.async_set(MOCK_TIME_SCHEDULE_ID, STATE_ON)
    hass.states.async_set(MOCK_HOUSE_POWER_ID, "1000")
    hass.states.async_set(MOCK_SOLAR_PROD_ID, "2000")
    hass.states.async_set(MOCK_SOLAR_SCHEDULE_ID, STATE_OFF)
    hass.states.async_set(MOCK_MAX_CURRENT_LIMIT_ID, "16")
    hass.states.async_set(MOCK_DYN_CURRENT_LIMIT_ID, "10")

    # --- Del 1: Initial Setup ---
    print("TESTDEL 1: Initial Setup")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result is not None
    assert result["type"] == "form"
    assert result["step_id"] == "user"

    random_soc_limit = round(random.uniform(50.0, 90.0), 1)

    initial_user_input = {
        CONF_CHARGER_DEVICE: MOCK_EASEE_DEVICE_ID,
        CONF_STATUS_SENSOR: MOCK_STATUS_SENSOR_ID,
        CONF_CHARGER_ENABLED_SWITCH_ID: MOCK_POWER_SWITCH_ID,
        CONF_PRICE_SENSOR: MOCK_PRICE_SENSOR_ID,
        CONF_EV_SOC_SENSOR: MOCK_SOC_SENSOR_ID_INITIAL,
        CONF_TARGET_SOC_LIMIT: random_soc_limit,
        CONF_TIME_SCHEDULE_ENTITY: None,
        CONF_HOUSE_POWER_SENSOR: None,
        CONF_SOLAR_PRODUCTION_SENSOR: None,
        CONF_SOLAR_SCHEDULE_ENTITY: None,
        CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR: None,
        CONF_CHARGER_DYNAMIC_CURRENT_SENSOR: None,
        CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL_SECONDS,
        CONF_DEBUG_LOGGING: False,
    }

    with patch(f"custom_components.{DOMAIN}.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], initial_user_input
        )
        await hass.async_block_till_done()

    assert result is not None
    assert result["type"] == "create_entry"
    entry: ConfigEntry = result["result"]
    assert entry.domain == DOMAIN
    assert entry.data[CONF_CHARGER_DEVICE] == MOCK_EASEE_DEVICE_ID
    assert entry.data[CONF_EV_SOC_SENSOR] == MOCK_SOC_SENSOR_ID_INITIAL
    assert entry.data[CONF_TARGET_SOC_LIMIT] == random_soc_limit
    assert entry.data[CONF_CHARGER_DYNAMIC_CURRENT_SENSOR] is None
    assert not entry.options  # Inga options satta initialt

    # --- Del 2: Öppna Options första gången ---
    print("TESTDEL 2: Öppna Options (verifiera initiala värden implicit)")
    result_options_check = await hass.config_entries.options.async_init(entry.entry_id)
    assert result_options_check is not None
    assert result_options_check["type"] == "form"

    # --- Del 3: Modifiera i Options ---
    print("TESTDEL 3: Modifiera i Options")
    # Options-formuläret kommer att populeras med en kombination av entry.data och entry.options.
    # Vi bygger input baserat på vad som finns i entry.data och gör våra ändringar.
    options_input_modified = {
        CONF_CHARGER_DEVICE: entry.data.get(CONF_CHARGER_DEVICE),
        CONF_STATUS_SENSOR: entry.data.get(CONF_STATUS_SENSOR),
        CONF_CHARGER_ENABLED_SWITCH_ID: entry.data.get(CONF_CHARGER_ENABLED_SWITCH_ID),
        CONF_PRICE_SENSOR: entry.data.get(CONF_PRICE_SENSOR),
        CONF_TARGET_SOC_LIMIT: entry.data.get(CONF_TARGET_SOC_LIMIT),
        CONF_SCAN_INTERVAL: entry.data.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_SECONDS
        ),
        CONF_DEBUG_LOGGING: entry.data.get(CONF_DEBUG_LOGGING, False),
        # Ändringar:
        CONF_EV_SOC_SENSOR: None,  # Simulerar rensat fält
        # Fyll i andra valfria fält som din config_flow.py:s OptionsFlow hanterar
        # (den sparar ALL_CONF_KEYS i options).
        # Om de var None i entry.data, och ska förbli "tomma" för EntitySelector,
        # är None korrekt input här om schemat är vol.Maybe(EntitySelector).
        CONF_TIME_SCHEDULE_ENTITY: MOCK_TIME_SCHEDULE_ID,  # Fyll i
        CONF_HOUSE_POWER_SENSOR: MOCK_HOUSE_POWER_ID,  # Fyll i
        CONF_SOLAR_PRODUCTION_SENSOR: MOCK_SOLAR_PROD_ID,  # Fyll i
        CONF_SOLAR_SCHEDULE_ENTITY: MOCK_SOLAR_SCHEDULE_ID,  # Fyll i
        CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR: MOCK_MAX_CURRENT_LIMIT_ID,  # Fyll i
        CONF_CHARGER_DYNAMIC_CURRENT_SENSOR: MOCK_DYN_CURRENT_LIMIT_ID,  # Fyll i
    }

    with (
        patch(f"custom_components.{DOMAIN}.async_setup_entry", return_value=True),
        patch(f"custom_components.{DOMAIN}.async_unload_entry", return_value=True),
    ):
        result_options_save = await hass.config_entries.options.async_configure(
            result_options_check["flow_id"], options_input_modified
        )
        await hass.async_block_till_done()  # För att hantera eventuell omladdning

    assert result_options_save is not None
    assert result_options_save["type"] == "create_entry"

    # Hämta den uppdaterade config entry för att kontrollera options
    updated_entry = hass.config_entries.async_get_entry(entry.entry_id)
    assert updated_entry is not None

    # Nu ska alla värden finnas i updated_entry.options
    assert (
        updated_entry.options[CONF_EV_SOC_SENSOR] is None
    )  # Verifiera att den är borttagen/None
    assert (
        updated_entry.options[CONF_CHARGER_DYNAMIC_CURRENT_SENSOR] == MOCK_DYN_CURRENT_LIMIT_ID
    )  # Verifiera nytt värde
    assert (
        updated_entry.options[CONF_TARGET_SOC_LIMIT] == random_soc_limit
    )  # Ska vara kvar
    assert (
        updated_entry.options[CONF_CHARGER_DEVICE] == MOCK_EASEE_DEVICE_ID
    )  # Obligatoriska fält finns nu i options

    # --- Del 4: Öppna Options igen (verifiera modifierade värden implicit) ---
    print("TESTDEL 4: Öppna Options igen (verifiera modifierade värden implicit)")
    result_options_final_check = await hass.config_entries.options.async_init(
        updated_entry.entry_id
    )
    assert result_options_final_check is not None
    assert result_options_final_check["type"] == "form"
    # Formuläret här skulle populeras från updated_entry.options,
    # så det faktum att vi kunde öppna det och att updated_entry.options är korrekta
    # är en tillräcklig verifiering för detta teststeg.

    print("Testet slutfört framgångsrikt!")
