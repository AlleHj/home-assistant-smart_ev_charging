"""Tester för SmartEVChargingCoordinator."""

import pytest
import logging
import random
from unittest.mock import patch

# Korrigering: Lägg till 'timezone' i denna import
from datetime import datetime, timedelta, timezone

# Korrigering: Import av HomeAssistant med stort A
from homeassistant.core import HomeAssistant
from homeassistant.const import STATE_ON, STATE_OFF, STATE_UNAVAILABLE
from homeassistant.config_entries import ConfigEntryState

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
    async_fire_time_changed,
)

from custom_components.smart_ev_charging.const import (
    DOMAIN,
    CONF_CHARGER_DEVICE,
    CONF_STATUS_SENSOR,
    CONF_CHARGER_ENABLED_SWITCH_ID,
    CONF_PRICE_SENSOR,
    CONF_TIME_SCHEDULE_ENTITY,
    EASEE_SERVICE_RESUME_CHARGING,
    EASEE_SERVICE_SET_DYNAMIC_CURRENT,
    CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR,
    CONF_EV_SOC_SENSOR,
    CONF_TARGET_SOC_LIMIT,
    CONF_DEBUG_LOGGING,
    EASEE_SERVICE_PAUSE_CHARGING,
)
from custom_components.smart_ev_charging.coordinator import SmartEVChargingCoordinator

# Vi definierar en "falsk" konstant för den nya sensorn vi simulerar
CONF_CHARGER_DYNAMIC_CURRENT_SENSOR = "charger_dynamic_current_sensor_id"


# Korrigering: Homeassistant -> HomeAssistant
async def test_price_time_charging_starts_when_conditions_are_met(hass: HomeAssistant):
    """
    Testar att koordinatorn startar laddning via Pris/Tid-läget från stillestånd.

    SYFTE:
        Att verifiera att koordinatorns beslutslogik korrekt initierar en
        laddningssession när alla villkor för Pris/Tid-styrning är uppfyllda.

    FÖRUTSÄTTNINGAR (Arrange):
        - En ConfigEntry har skapats med alla nödvändiga sensorer konfigurerade.
        - Debug-loggning är aktiverat i konfigurationen.
        - Laddarens status är 'ready_to_charge' (redo men laddar inte).
        - Elpriset är lågt (0.5 kr/kWh).
        - Tidsschemat för laddning är PÅ.
        - Switchen för "Smart Laddning" är PÅ.
        - Maxpriset är satt till 1.0 kr/kWh (högre än det nuvarande priset).

    UTFÖRANDE (Act):
        - En uppdatering av koordinatorn triggas manuellt via `async_request_refresh`.

    FÖRVÄNTAT RESULTAT (Assert):
        - Tjänsten `set_dynamic_charger_circuit_current` anropas för att sätta max ström.
        - Tjänsten `resume_charging` anropas för att starta laddningen.
        - Koordinatorns aktiva styrningsläge (`active_control_mode`) blir "PRIS_TID".
    """
    # 1. ARRANGE
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_CHARGER_DEVICE: "easee_123",
            CONF_STATUS_SENSOR: "sensor.easee_status",
            CONF_CHARGER_ENABLED_SWITCH_ID: "switch.easee_power",
            CONF_PRICE_SENSOR: "sensor.nordpool_price",
            CONF_TIME_SCHEDULE_ENTITY: "schedule.charging_time",
            CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR: "sensor.charger_max_current",
            CONF_DEBUG_LOGGING: True,
        },
        entry_id="test_coordinator_entry_1",
    )
    entry.add_to_hass(hass)
    hass.states.async_set("sensor.easee_status", "ready_to_charge")
    hass.states.async_set("switch.easee_power", STATE_ON)
    hass.states.async_set("sensor.nordpool_price", "0.5")
    hass.states.async_set("schedule.charging_time", STATE_ON)
    hass.states.async_set("sensor.charger_max_current", "16")
    coordinator = SmartEVChargingCoordinator(hass, entry, 30)
    coordinator.smart_enable_switch_entity_id = (
        "switch.avancerad_elbilsladdning_smart_laddning_aktiv"
    )
    coordinator.max_price_entity_id = "number.avancerad_elbilsladdning_max_elpris"
    coordinator.solar_enable_switch_entity_id = (
        "switch.avancerad_elbilsladdning_aktivera_solenergiladdning"
    )
    coordinator._internal_entities_resolved = True
    hass.states.async_set(coordinator.smart_enable_switch_entity_id, STATE_ON)
    hass.states.async_set(coordinator.max_price_entity_id, "1.0")
    hass.states.async_set(coordinator.solar_enable_switch_entity_id, STATE_OFF)
    resume_calls = async_mock_service(hass, "easee", EASEE_SERVICE_RESUME_CHARGING)
    set_current_calls = async_mock_service(
        hass, "easee", EASEE_SERVICE_SET_DYNAMIC_CURRENT
    )

    # 2. ACT
    await coordinator.async_request_refresh()
    await hass.async_block_till_done()

    # 3. ASSERT
    assert len(resume_calls) == 1
    assert len(set_current_calls) == 1
    assert coordinator.active_control_mode == "PRIS_TID"

    # 4. TEARDOWN
    await coordinator.async_shutdown()
    await hass.async_block_till_done()
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


# Korrigering: Homeassistant -> HomeAssistant
async def test_price_time_charging_does_not_call_set_current_unnecessarily(
    hass: HomeAssistant,
):
    """
    Testar att koordinatorn INTE gör onödiga anrop för Pris/Tid-läget.

    SYFTE:
        Att specifikt testa optimeringslogiken för Pris/Tid-läget. Testet verifierar
        att `set_dynamic_charger_circuit_current` INTE anropas om laddning redan
        pågår och den aktiva dynamiska strömgränsen redan är lika med målvärdet.
        OBS: Detta test är designat för att misslyckas tills optimeringen är
        implementerad i `coordinator.py`.

    FÖRUTSÄTTNINGAR (Arrange):
        - Solenergiladdning är explicit satt till AV för att isolera testet.
        - Alla villkor för Pris/Tid-laddning är uppfyllda (lågt pris, schema PÅ etc.).
        - Laddarens status är 'charging' (laddning pågår).
        - En simulerad sensor för den *nuvarande dynamiska gränsen* är satt till 16A.
        - Koordinatorns målvärde för ström är också 16A.

    UTFÖRANDE (Act):
        - En uppdatering av koordinatorn triggas.

    FÖRVÄNTAT RESULTAT (Assert):
        - Tjänsten `set_dynamic_charger_circuit_current` ska INTE anropas, eftersom
          nuvarande värde (16A) är lika med målvärdet (16A).
    """
    # 1. ARRANGE
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_CHARGER_DEVICE: "easee_123",
            CONF_STATUS_SENSOR: "sensor.easee_status",
            CONF_CHARGER_ENABLED_SWITCH_ID: "switch.easee_power",
            CONF_PRICE_SENSOR: "sensor.nordpool_price",
            CONF_TIME_SCHEDULE_ENTITY: "schedule.charging_time",
            CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR: "sensor.charger_max_current",
            CONF_DEBUG_LOGGING: True,
            CONF_CHARGER_DYNAMIC_CURRENT_SENSOR: "sensor.current_dynamic_limit",
        },
        entry_id="test_coordinator_entry_2",
    )
    entry.add_to_hass(hass)
    hass.states.async_set("sensor.easee_status", "charging")
    hass.states.async_set("switch.easee_power", STATE_ON)
    hass.states.async_set("sensor.nordpool_price", "0.5")
    hass.states.async_set("schedule.charging_time", STATE_ON)
    hass.states.async_set("sensor.charger_max_current", "16")
    hass.states.async_set("sensor.current_dynamic_limit", "16")
    coordinator = SmartEVChargingCoordinator(hass, entry, 30)
    coordinator.smart_enable_switch_entity_id = (
        "switch.avancerad_elbilsladdning_smart_laddning_aktiv"
    )
    coordinator.max_price_entity_id = "number.avancerad_elbilsladdning_max_elpris"
    coordinator.solar_enable_switch_entity_id = (
        "switch.avancerad_elbilsladdning_aktivera_solenergiladdning"
    )
    coordinator._internal_entities_resolved = True
    hass.states.async_set(coordinator.smart_enable_switch_entity_id, STATE_ON)
    hass.states.async_set(coordinator.max_price_entity_id, "1.0")
    hass.states.async_set(coordinator.solar_enable_switch_entity_id, STATE_OFF)
    resume_calls = async_mock_service(hass, "easee", EASEE_SERVICE_RESUME_CHARGING)
    set_current_calls = async_mock_service(
        hass, "easee", EASEE_SERVICE_SET_DYNAMIC_CURRENT
    )

    # 2. ACT
    await coordinator.async_request_refresh()
    await hass.async_block_till_done()

    # 3. ASSERT
    assert len(set_current_calls) == 0
    assert len(resume_calls) == 0

    # 4. TEARDOWN
    await coordinator.async_shutdown()
    await hass.async_block_till_done()
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


# Korrigering: Homeassistant -> HomeAssistant
async def test_charging_stops_when_soc_limit_is_reached(hass: HomeAssistant, caplog):
    """
    Testar att laddning pausas och ett meddelande loggas när SoC-gränsen nås.

    SYFTE:
        Att verifiera att SoC-gränsen har högst prioritet och att den
        korrekt pausar laddningen samt ger en informativ loggutskrift.

    FÖRUTSÄTTNINGAR (Arrange):
        - Debug-loggning är aktiverat i konfigurationen.
        - Laddning pågår ('charging').
        - Bilens SoC är 90%.
        - SoC-gränsen i konfigurationen är satt till 89%.
        - Alla nödvändiga config-värden (som `CONF_CHARGER_ENABLED_SWITCH_ID`) finns med.

    UTFÖRANDE (Act):
        - En uppdatering av koordinatorn triggas.

    FÖRVÄNTAT RESULTAT (Assert):
        - Tjänsten `easee.pause_charging` anropas exakt en gång.
        - En logg på INFO-nivå skapas med ett meddelande om att SoC-gränsen är nådd.
    """
    # 1. ARRANGE
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_CHARGER_DEVICE: "easee_123",
            CONF_STATUS_SENSOR: "sensor.easee_status",
            CONF_EV_SOC_SENSOR: "sensor.ev_soc",
            CONF_TARGET_SOC_LIMIT: 89.0,
            CONF_DEBUG_LOGGING: True,
            CONF_CHARGER_ENABLED_SWITCH_ID: "switch.easee_power",
        },
        entry_id="test_coordinator_entry_3",
    )
    entry.add_to_hass(hass)
    hass.states.async_set("sensor.easee_status", "charging")
    hass.states.async_set("sensor.ev_soc", "90.0")
    hass.states.async_set("switch.easee_power", STATE_ON)
    coordinator = SmartEVChargingCoordinator(hass, entry, 30)
    coordinator._internal_entities_resolved = True
    pause_calls = async_mock_service(hass, "easee", EASEE_SERVICE_PAUSE_CHARGING)

    # 2. ACT
    caplog.set_level(logging.INFO)
    await coordinator.async_request_refresh()
    await hass.async_block_till_done()

    # 3. ASSERT
    assert len(pause_calls) == 1
    assert "SoC (90.0%) har nått målet (89.0%)" in caplog.text

    # 4. TEARDOWN
    await coordinator.async_shutdown()
    await hass.async_block_till_done()
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_full_day_price_time_simulation(hass: HomeAssistant):
    """
    Testar Pris/Tid-logiken genom att simulera ett helt dygn, timme för timme.
    ... (docstring) ...
    """
    # 1. ARRANGE (Initial förberedelse)
    # ---------------------------------
    max_price = random.uniform(0.2, 0.8)
    active_schedule_hours: Set[int] = set(random.sample(range(24), 12))
    hourly_spot_prices = {hour: random.uniform(0.0, 1.0) for hour in range(24)}

    print(f"\n--- Test-setup ---")
    print(f"Slumpat maxpris: {max_price:.2f} kr")
    print(f"Timmar med aktivt schema: {sorted(list(active_schedule_hours))}")

    MOCK_SCHEDULE_ID = "schedule.test_laddningsschema"
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_CHARGER_DEVICE: "easee_123",
            CONF_STATUS_SENSOR: "sensor.easee_status",
            CONF_CHARGER_ENABLED_SWITCH_ID: "switch.easee_power",
            CONF_PRICE_SENSOR: "sensor.nordpool_price",
            CONF_TIME_SCHEDULE_ENTITY: MOCK_SCHEDULE_ID,
            CONF_DEBUG_LOGGING: True,
        },
        entry_id="test_full_day_sim",
    )
    entry.add_to_hass(hass)

    # ---- VI STÄNGER AV LYSSNARNA FÖR ATT FÅ FULL KONTROLL ----
    with patch(
        "custom_components.smart_ev_charging.coordinator.SmartEVChargingCoordinator._setup_listeners"
    ):
        # Skapa koordinatorn direkt. Dess `_setup_listeners` kommer inte att köras.
        coordinator = SmartEVChargingCoordinator(hass, entry, 30)

        # Sätt alla interna entitets-ID:n manuellt.
        coordinator.smart_enable_switch_entity_id = (
            "switch.avancerad_elbilsladdning_smart_laddning_aktiv"
        )
        coordinator.max_price_entity_id = "number.avancerad_elbilsladdning_max_elpris"
        coordinator.solar_enable_switch_entity_id = (
            "switch.avancerad_elbilsladdning_aktivera_solenergiladdning"
        )
        coordinator._internal_entities_resolved = True

        # Sätt tillstånden för de interna entiteterna
        hass.states.async_set(coordinator.smart_enable_switch_entity_id, STATE_ON)
        hass.states.async_set(coordinator.max_price_entity_id, f"{max_price:.2f}")
        hass.states.async_set(coordinator.solar_enable_switch_entity_id, STATE_OFF)

        # Sätt starttillstånd för de externa entiteterna
        hass.states.async_set("sensor.easee_status", "ready_to_charge")
        hass.states.async_set("switch.easee_power", STATE_ON)

        # Mocka tjänsterna vi vill övervaka
        resume_calls = async_mock_service(hass, "easee", EASEE_SERVICE_RESUME_CHARGING)
        pause_calls = async_mock_service(hass, "easee", EASEE_SERVICE_PAUSE_CHARGING)
        async_mock_service(hass, "easee", EASEE_SERVICE_SET_DYNAMIC_CURRENT)

        # 2. ACT & ASSERT (Loopa igenom dygnet)
        # ------------------------------------
        start_of_day = datetime(2025, 5, 30, 0, 0, 0, tzinfo=timezone.utc)
        is_charging = False

        for hour in range(24):
            current_time = start_of_day + timedelta(hours=hour)

            spot_price_this_hour = hourly_spot_prices[hour]
            schedule_active_this_hour = hour in active_schedule_hours

            schedule_state = STATE_ON if schedule_active_this_hour else STATE_OFF
            hass.states.async_set(MOCK_SCHEDULE_ID, schedule_state)

            hass.states.async_set(
                "sensor.nordpool_price", f"{spot_price_this_hour:.2f}"
            )

            current_charger_status = "charging" if is_charging else "ready_to_charge"
            hass.states.async_set("sensor.easee_status", current_charger_status)

            async_fire_time_changed(hass, current_time)
            await hass.async_block_till_done()

            should_be_charging = schedule_active_this_hour and (
                spot_price_this_hour <= max_price
            )

            resume_calls.clear()
            pause_calls.clear()

            # Denna refresh är nu den ENDA som körs, vilket ger oss full kontroll.
            await coordinator.async_request_refresh()
            await hass.async_block_till_done()

            # Verifiera resultatet
            if should_be_charging and not is_charging:
                print(
                    f"TIMME {hour:02d}: Pris {spot_price_this_hour:.2f} <= {max_price:.2f}, Schema PÅ. Förväntar START."
                )
                assert len(resume_calls) == 1, (
                    f"Fel timme {hour}: Förväntade start av laddning."
                )
                assert len(pause_calls) == 0, (
                    f"Fel timme {hour}: Förväntade start, men fick paus."
                )
                is_charging = True
            elif not should_be_charging and is_charging:
                reason = (
                    "Pris för högt"
                    if not (spot_price_this_hour <= max_price)
                    else "Schema inaktivt"
                )
                print(f"TIMME {hour:02d}: {reason}. Förväntar STOPP.")
                assert len(pause_calls) == 1, (
                    f"Fel timme {hour}: Förväntade stopp av laddning."
                )
                assert len(resume_calls) == 0, (
                    f"Fel timme {hour}: Förväntade stopp, men fick start."
                )
                is_charging = False
            else:
                status_text = "fortsatt laddning" if is_charging else "fortsatt pausad"
                print(
                    f"TIMME {hour:02d}: Pris {spot_price_this_hour:.2f}, Schema {'PÅ' if schedule_active_this_hour else 'AV'}. Förväntar {status_text}."
                )
                assert len(resume_calls) == 0, (
                    f"Fel timme {hour}: Förväntade ingen ändring, men fick start."
                )
                assert len(pause_calls) == 0, (
                    f"Fel timme {hour}: Förväntade ingen ändring, men fick paus."
                )

        # 4. TEARDOWN
        # -----------
        # Shutdown behövs inte eftersom lyssnare/timers aldrig startades.
        # Vi behöver inte heller köra unload eftersom setup aldrig kördes.
