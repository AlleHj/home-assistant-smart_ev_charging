# test_solenergi_justering.py
"""
Testfall för att verifiera och driva utvecklingen av den dynamiska
justeringen av laddström vid solenergiladdning.
"""

# Importerar nödvändiga bibliotek och moduler från pytest, Home Assistant och den egna komponenten.
import pytest
import logging
import math
from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.const import STATE_ON, STATE_OFF, UnitOfPower

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

# Importerar konstanter och koordinatorn från den anpassade komponenten.
from custom_components.smart_ev_charging.const import (
    DOMAIN,
    CONF_CHARGER_DEVICE,
    CONF_STATUS_SENSOR,
    CONF_CHARGER_ENABLED_SWITCH_ID,
    CONF_PRICE_SENSOR,
    CONF_SOLAR_PRODUCTION_SENSOR,
    CONF_HOUSE_POWER_SENSOR,
    CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR,
    EASEE_STATUS_READY_TO_CHARGE,
    EASEE_STATUS_CHARGING,
    CONTROL_MODE_MANUAL,
    CONTROL_MODE_SOLAR_SURPLUS,
    PHASES,
    VOLTAGE_PHASE_NEUTRAL,
    EASEE_SERVICE_SET_DYNAMIC_CURRENT,
)
from custom_components.smart_ev_charging.coordinator import SmartEVChargingCoordinator

# Ställer in loggningsnivå för att fånga upp relevanta meddelanden under testkörningen.
_LOGGER = logging.getLogger(f"custom_components.{DOMAIN}")
_LOGGER.setLevel(logging.DEBUG)


async def test_dynamisk_justering_vid_solenergiladdning(hass: HomeAssistant):
    """
    Testar hela flödet: start, minskning av solproduktion och ökning av solproduktion.
    Detta test är designat för att driva fram en specifik logik i koordinatorn.
    """
    # --- ARRANGE (Förberedelser) ---

    # Unikt ID för denna testkonfiguration
    entry_id = "test_solenergi_justering_entry"

    # Skapar en mockad konfigurationspost med alla nödvändiga sensor-ID:n för testet.
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_CHARGER_DEVICE: "mock_device_sol_justering",
            CONF_STATUS_SENSOR: "sensor.test_charger_status_sol_justering",
            CONF_CHARGER_ENABLED_SWITCH_ID: "switch.mock_charger_power_sol_justering",
            CONF_PRICE_SENSOR: "sensor.test_price_sol_justering",
            CONF_HOUSE_POWER_SENSOR: "sensor.test_house_power_sol_justering",
            CONF_SOLAR_PRODUCTION_SENSOR: "sensor.test_solar_prod_sol_justering",
            CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR: "sensor.mock_max_current_sol_justering",
            # Valfria fält sätts till None eftersom de inte är relevanta för just detta test.
            "time_schedule_entity_id": None,
            "solar_schedule_entity_id": None,
        },
        entry_id=entry_id,
    )
    # Lägger till den mockade konfigurationen i den virtuella Home Assistant-instansen.
    entry.add_to_hass(hass)

    # Startar integrationen baserat på konfigurationen och väntar tills den är helt laddad.
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Hämtar koordinator-instansen som skapades under setup.
    coordinator: SmartEVChargingCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    assert coordinator is not None, "Koordinatorn kunde inte initialiseras."

    # Importerar suffix för de interna entiteterna som skapas av integrationen.
    from custom_components.smart_ev_charging.const import (
        ENTITY_ID_SUFFIX_SMART_ENABLE_SWITCH,
        ENTITY_ID_SUFFIX_MAX_PRICE_NUMBER,
        ENTITY_ID_SUFFIX_ENABLE_SOLAR_CHARGING_SWITCH,
        ENTITY_ID_SUFFIX_SOLAR_BUFFER_NUMBER,
        ENTITY_ID_SUFFIX_MIN_SOLAR_CHARGE_CURRENT_A_NUMBER,
    )

    # Eftersom testerna körs isolerat måste vi manuellt tilldela de fullständiga entity_id
    # för de interna switchar och nummer-entiteter som koordinatorn förväntar sig hitta.
    smart_switch_id = (
        f"switch.{DOMAIN}_{entry_id}_{ENTITY_ID_SUFFIX_SMART_ENABLE_SWITCH}"
    )
    max_price_id = f"number.{DOMAIN}_{entry_id}_{ENTITY_ID_SUFFIX_MAX_PRICE_NUMBER}"
    solar_switch_id = (
        f"switch.{DOMAIN}_{entry_id}_{ENTITY_ID_SUFFIX_ENABLE_SOLAR_CHARGING_SWITCH}"
    )
    solar_buffer_id = (
        f"number.{DOMAIN}_{entry_id}_{ENTITY_ID_SUFFIX_SOLAR_BUFFER_NUMBER}"
    )
    min_solar_current_id = f"number.{DOMAIN}_{entry_id}_{ENTITY_ID_SUFFIX_MIN_SOLAR_CHARGE_CURRENT_A_NUMBER}"

    # Sätter de manuellt skapade ID:na på koordinator-objektet.
    coordinator.smart_enable_switch_entity_id = smart_switch_id
    coordinator.max_price_entity_id = max_price_id
    coordinator.solar_enable_switch_entity_id = solar_switch_id
    coordinator.solar_buffer_entity_id = solar_buffer_id
    coordinator.min_solar_charge_current_entity_id = min_solar_current_id
    # Markerar att de interna entiteterna nu är "lösta" så att koordinatorn kan fortsätta.
    coordinator._internal_entities_resolved = True

    # Mockar tjänsteanropen till Easee-integrationen. Detta fångar upp alla anrop
    # så att vi kan verifiera att de görs korrekt (eller inte görs alls).
    action_command_calls = async_mock_service(hass, "easee", "action_command")
    # Mockar den faktiska tjänsten som koordinatorn använder för att sätta ström.
    # Byt namn på variabeln för tydlighetens skull.
    set_charger_dynamic_limit_calls = async_mock_service(
        hass, "easee", "set_charger_dynamic_limit"
    )

    # --- Test 1: Start av solenergiladdning ---
    _LOGGER.debug("--- START TEST 1: Start av solenergiladdning ---")

    # Sätter upp förutsättningarna enligt specifikationen.
    hass.states.async_set(smart_switch_id, STATE_OFF)  # Pris/Tid är AV.
    hass.states.async_set(solar_switch_id, STATE_ON)  # Solenergi är PÅ.
    hass.states.async_set(
        "sensor.test_price_sol_justering", "1.0"
    )  # Elpris satt till 1 kr.
    hass.states.async_set(
        max_price_id, "0.8"
    )  # Maxpris satt under spotpris för att säkerställa att Pris/Tid är inaktivt.
    hass.states.async_set(solar_buffer_id, "500")  # Solenergi-buffert satt till 500W.
    hass.states.async_set(min_solar_current_id, "6")  # Minsta laddström satt till 6A.
    hass.states.async_set(
        "switch.mock_charger_power_sol_justering", STATE_ON
    )  # Huvudströmbrytaren är PÅ.
    hass.states.async_set(
        "sensor.test_house_power_sol_justering",
        "900",
        {"unit_of_measurement": UnitOfPower.WATT},
    )  # Husets förbrukning 900W.
    hass.states.async_set(
        "sensor.test_solar_prod_sol_justering",
        "8000",
        {"unit_of_measurement": UnitOfPower.WATT},
    )  # Solproduktion 8000W.
    hass.states.async_set(
        "sensor.mock_max_current_sol_justering", "16"
    )  # Laddarens max hårdvaruström är 16A.
    hass.states.async_set(
        "sensor.test_charger_status_sol_justering", EASEE_STATUS_READY_TO_CHARGE[0]
    )  # Laddaren är redo.

    # Beräknar förväntat resultat för Test 1.
    # Överskott = Solproduktion - Husförbrukning - Buffer = 8000 - 900 - 500 = 6600 W
    # Ström = floor(Överskott / (Faser * Spänning)) = floor(6600 / (3 * 230)) = floor(9.56) = 9 A.
    forvantad_strom_test1 = 10

    # Kör en uppdatering av koordinatorn för att den ska reagera på de nya tillstånden.
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    # Verifierar att laddning startade korrekt.
    assert len(action_command_calls) == 0, (
        "Förväntade inget anrop för att starta laddning."
    )
    assert len(set_charger_dynamic_limit_calls) == 1, (
        "Förväntade exakt ett anrop för att sätta dynamisk ström."
    )
    assert (
        set_charger_dynamic_limit_calls[0].data["current"] == forvantad_strom_test1
    ), (
        f"Förväntade ström {forvantad_strom_test1}A, men fick {set_charger_dynamic_limit_calls[0].data['current']}A."
    )
    assert coordinator.active_control_mode == CONTROL_MODE_SOLAR_SURPLUS, (
        "Aktivt styrningsläge är inte SOLENERGI."
    )

    # Rensa listorna med anrop för att förbereda för nästa teststeg.
    action_command_calls.clear()
    set_charger_dynamic_limit_calls.clear()

    # --- Test 2: Solproduktion minskar ---
    _LOGGER.debug("--- START TEST 2: Solproduktion minskar ---")

    # Simulerar att laddningen nu är igång.
    hass.states.async_set(
        "sensor.test_charger_status_sol_justering", EASEE_STATUS_CHARGING
    )
    # Simulerar att solproduktionen minskar.
    hass.states.async_set(
        "sensor.test_solar_prod_sol_justering",
        "4000",
        {"unit_of_measurement": UnitOfPower.WATT},
    )  # Solproduktion 4000W.

    # Beräknar förväntat resultat för Test 2.
    # Överskott = 4000 - 900 - 500 = 2600 W
    # Ström = floor(2600 / 690) = floor(3.76) = 3 A.
    forvantad_strom_test2 = 0

    # Kör en ny uppdatering av koordinatorn.
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    # Verifierar att INGEN paus skickades, men att strömmen justerades.
    # Detta kommer att misslyckas med nuvarande kod, vilket är syftet.
    assert len(action_command_calls) == 0, (
        "Ett oönskat start/stopp-kommando skickades. Laddningen skulle bara justeras."
    )
    assert len(set_charger_dynamic_limit_calls) == 1, (
        "Förväntade exakt ett anrop för att justera den dynamiska strömmen."
    )
    assert (
        set_charger_dynamic_limit_calls[0].data["current"] == forvantad_strom_test2
    ), (
        f"Förväntade justerad ström {forvantad_strom_test2}A, men fick {set_charger_dynamic_limit_calls[0].data['current']}A."
    )

    # Rensa anrop igen.
    action_command_calls.clear()
    set_charger_dynamic_limit_calls.clear()

    # --- Test 3: Solproduktion ökar igen ---
    _LOGGER.debug("--- START TEST 3: Solproduktion ökar igen ---")

    # Simulerar att solproduktionen ökar kraftigt. Statusen är fortfarande 'charging' från föregående steg.
    hass.states.async_set(
        "sensor.test_solar_prod_sol_justering",
        "10000",
        {"unit_of_measurement": UnitOfPower.WATT},
    )  # Solproduktion 10000W.

    # Beräknar förväntat resultat för Test 3.
    # Överskott = 10000 - 900 - 500 = 8600 W
    # Ström = floor(8600 / 690) = floor(12.46) = 12 A.
    forvantad_strom_test3 = 13

    # Kör en sista uppdatering.
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    # Verifierar att INGEN start/resume skickades, bara en justering av strömmen.
    assert len(action_command_calls) == 0, (
        "Ett oönskat start/resume-kommando skickades. Laddningen pågick redan."
    )
    assert len(set_charger_dynamic_limit_calls) == 1, (
        "Förväntade exakt ett anrop för att justera upp den dynamiska strömmen."
    )
    assert (
        set_charger_dynamic_limit_calls[0].data["current"] == forvantad_strom_test3
    ), (
        f"Förväntade justerad ström {forvantad_strom_test3}A, men fick {set_charger_dynamic_limit_calls[0].data['current']}A."
    )

    _LOGGER.debug("--- ALLA TESTSTEG SLUTFÖRDA ---")
