# File version: 2025-05-21.8
import logging
from datetime import timedelta
import asyncio # Importerad för asyncio.sleep

from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry

from .const import (
    DOMAIN,
    CONF_CHARGER_DEVICE,
    CONF_STATUS_SENSOR,
    CONF_PRICE_SENSOR,
    CONF_SURCHARGE_HELPER,
    CONF_TIME_SCHEDULE_ENTITY,
    CONF_HOUSE_POWER_SENSOR,
    CONF_SOLAR_PRODUCTION_SENSOR,
    CONF_SOLAR_SCHEDULE_ENTITY,
    CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR,
    CONF_EV_POWER_SENSOR,
    CONF_SCAN_INTERVAL,
    CONF_CHARGER_ENABLED_SWITCH_ID,
    CONF_EV_SOC_SENSOR, 
    CONF_TARGET_SOC_LIMIT,
    DEFAULT_SCAN_INTERVAL_SECONDS,
)
from .coordinator import SmartEVChargingCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["switch", "number", "sensor"]

async def async_options_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    _LOGGER.info("Alternativ uppdaterade för %s (entry_id: %s), laddar om integrationen.", entry.title, entry.entry_id)
    await hass.config_entries.async_reload(entry.entry_id)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Smart EV Charging from a config entry."""
    _LOGGER.debug("--- DEBUG INIT: async_setup_entry STARTAR för %s ---", entry.entry_id)

    # Lägg till en fördröjning här för att låta andra entiteter initialiseras
    _LOGGER.info("Smart EV Charging: Väntar 5 sekunder för att andra entiteter ska initialiseras...")
    await asyncio.sleep(2)
    _LOGGER.info("Smart EV Charging: Fördröjning klar, fortsätter med setup.")

    # Använd entry.options om de finns, annars entry.data. Options tar företräde.
    # Detta säkerställer att vi använder de senast sparade inställningarna.
    current_config = {**entry.data, **entry.options}
    _LOGGER.debug("--- DEBUG INIT: Använder config för koordinator: %s ---", current_config)


    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        # Skicka den kombinerade/aktuella konfigurationen till koordinatorn
        "config": current_config, 
        "coordinator": None,
        "options_listener": entry.add_update_listener(async_options_update_listener)
    }
    _LOGGER.debug("--- DEBUG INIT: hass.data initialiserad för entry_id %s ---", entry.entry_id)

    scan_interval_value = current_config.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_SECONDS)
    try:
        scan_interval_seconds = int(scan_interval_value)
        if scan_interval_seconds < 10: 
            _LOGGER.warning("Scan interval för lågt (%s sekunder), sätter till 10 sekunder.", scan_interval_seconds)
            scan_interval_seconds = 10
    except (ValueError, TypeError):
        _LOGGER.warning("Ogiltigt värde för scan_interval ('%s'), använder default %s sekunder.", scan_interval_value, DEFAULT_SCAN_INTERVAL_SECONDS)
        scan_interval_seconds = DEFAULT_SCAN_INTERVAL_SECONDS
    
    _LOGGER.debug("--- DEBUG INIT: Koordinatorns scan-intervall kommer att vara: %s sekunder ---", scan_interval_seconds)

    try:
        coordinator = SmartEVChargingCoordinator(
            hass,
            entry, # Skicka hela entry-objektet
            current_config, # Skicka den aktuella konfigurationen
            scan_interval_seconds
        )
        _LOGGER.debug("--- DEBUG INIT: SmartEVChargingCoordinator-objekt SKAPAT ---")

        await coordinator.async_config_entry_first_refresh()
        _LOGGER.debug("--- DEBUG INIT: coordinator.async_config_entry_first_refresh() ANROPAD OCH KLAR ---")

        hass.data[DOMAIN][entry.entry_id]["coordinator"] = coordinator
        _LOGGER.debug("--- DEBUG INIT: Koordinator lagrad i hass.data ---")

    except Exception as e:
        _LOGGER.error("--- DEBUG INIT: FEL vid skapande eller första refresh av koordinator: %s ---", e, exc_info=True)
        if entry.entry_id in hass.data[DOMAIN]:
            if listener_remover := hass.data[DOMAIN][entry.entry_id].get("options_listener"):
                listener_remover()
            hass.data[DOMAIN].pop(entry.entry_id)
        return False

    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        _LOGGER.debug("--- DEBUG INIT: async_forward_entry_setups KLAR för plattformar: %s ---", PLATFORMS)
    except Exception as e:
        _LOGGER.error("--- DEBUG INIT: FEL vid async_forward_entry_setups: %s ---", e, exc_info=True)
        await async_unload_entry(hass, entry) 
        return False

    _LOGGER.info("%s med entry_id %s är nu uppsatt och redo.", DOMAIN, entry.entry_id)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Avlastar %s med entry_id %s (Titel: %s)", DOMAIN, entry.entry_id, entry.title)
    
    entry_data = hass.data[DOMAIN].get(entry.entry_id)
    all_unloaded_ok = True

    if entry_data:
        coordinator: SmartEVChargingCoordinator | None = entry_data.get("coordinator")
        if coordinator:
            await coordinator._remove_listeners() 
            _LOGGER.debug("Koordinatorns _remove_listeners anropad för %s", entry.entry_id)

        options_listener_remover = entry_data.get("options_listener")
        if options_listener_remover:
            options_listener_remover()
            _LOGGER.debug("Options listener borttagen för %s", entry.entry_id)

        unload_results = await asyncio.gather(
            *[hass.config_entries.async_forward_entry_unload(entry, platform) for platform in PLATFORMS],
            return_exceptions=True
        )

        for i, result in enumerate(unload_results):
            platform = PLATFORMS[i]
            if isinstance(result, Exception):
                _LOGGER.error("Fel vid avlastning av plattform %s för %s: %s", platform, entry.entry_id, result)
                all_unloaded_ok = False
            elif not result:
                 _LOGGER.warning("Misslyckades med att avlasta plattform %s för %s (returnerade False).", platform, entry.entry_id)
                 all_unloaded_ok = False
            else:
                _LOGGER.debug("Plattform %s avlastad korrekt för %s.", platform, entry.entry_id)

        if all_unloaded_ok:
            hass.data[DOMAIN].pop(entry.entry_id)
            _LOGGER.info("All data för %s (entry_id: %s) borttagen från hass.data.", DOMAIN, entry.entry_id)
        else:
            _LOGGER.warning("En eller flera plattformar kunde inte avlastas korrekt för %s.", entry.entry_id)
            if entry.entry_id in hass.data[DOMAIN]: # Försök ändå ta bort
                 hass.data[DOMAIN].pop(entry.entry_id)
                 _LOGGER.debug("Försökte ta bort data för %s från hass.data trots avlastningsproblem.", entry.entry_id)
    else:
        _LOGGER.debug("Ingen data hittades i hass.data för %s (entry_id: %s) att avlasta.", DOMAIN, entry.entry_id)
    
    return all_unloaded_ok
