# File version: 2025-05-28 0.1.2
import logging
from datetime import timedelta
import asyncio

from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP

from .const import (
    DOMAIN,
    CONF_SCAN_INTERVAL,
    CONF_DEBUG_LOGGING, # Importerad
    DEFAULT_SCAN_INTERVAL_SECONDS,
)
from .coordinator import SmartEVChargingCoordinator

_LOGGER = logging.getLogger(__name__) # Används för allmän loggning i denna fil
_COMPONENT_LOGGER = logging.getLogger(f"custom_components.{DOMAIN}") # Specifik logger för integrationen

PLATFORMS = ["switch", "number", "sensor"]

def _update_logger_level(debug_enabled: bool) -> None:
    """Uppdaterar loggnivån för integrationsspecifika loggers."""
    if debug_enabled:
        _COMPONENT_LOGGER.setLevel(logging.DEBUG)
        _LOGGER.info("Debug-loggning aktiverad för %s.", DOMAIN)
    else:
        _COMPONENT_LOGGER.setLevel(logging.INFO)
        _LOGGER.info("Debug-loggning avaktiverad för %s. Standardnivå INFO.", DOMAIN)

async def async_options_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Hanterar uppdateringar av alternativ."""
    _LOGGER.info("Alternativ uppdaterade för %s (entry_id: %s), laddar om integrationen.", entry.title, entry.entry_id)
    # Omladdning kommer att anropa async_setup_entry igen, som läser nya alternativ inklusive debug.
    await hass.config_entries.async_reload(entry.entry_id)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Konfigurerar Smart EV Charging från en config entry."""
    _LOGGER.debug("--- DEBUG INIT: async_setup_entry STARTAR för %s ---", entry.entry_id)

    # Kombinera data och options, där options har företräde.
    current_config = {**entry.data, **entry.options}
    _LOGGER.debug("--- DEBUG INIT: Använder config för koordinator: %s ---", current_config)

    # Ställ in loggningsnivå baserat på konfigurationen
    debug_enabled = current_config.get(CONF_DEBUG_LOGGING, False)
    _update_logger_level(debug_enabled) # Anropa funktionen här

    # Initial fördröjning (om nödvändigt för andra entiteter)
    # Tas bort då den nu hanteras i koordinatorns _async_first_refresh
    # _LOGGER.info("Smart EV Charging: Väntar X sekunder (om konfigurerat)...")
    # await asyncio.sleep(2) # Justera eller ta bort vid behov
    # _LOGGER.info("Smart EV Charging: Fördröjning klar, fortsätter med setup.")


    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "config": current_config,
        "coordinator": None,
        "options_listener": entry.add_update_listener(async_options_update_listener)
    }
    _LOGGER.debug("--- DEBUG INIT: hass.data initialiserad för entry_id %s ---", entry.entry_id)

    scan_interval_value = current_config.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_SECONDS)
    try:
        scan_interval_seconds = int(scan_interval_value)
        if scan_interval_seconds < 10:
            _COMPONENT_LOGGER.warning("Scan interval för lågt (%s sekunder), sätter till 10 sekunder.", scan_interval_seconds)
            scan_interval_seconds = 10
    except (ValueError, TypeError):
        _COMPONENT_LOGGER.warning("Ogiltigt värde för scan_interval ('%s'), använder default %s sekunder.", scan_interval_value, DEFAULT_SCAN_INTERVAL_SECONDS)
        scan_interval_seconds = DEFAULT_SCAN_INTERVAL_SECONDS

    _COMPONENT_LOGGER.debug("--- DEBUG INIT: Koordinatorns scan-intervall kommer att vara: %s sekunder ---", scan_interval_seconds)

    try:
        coordinator = SmartEVChargingCoordinator(
            hass,
            entry,
            current_config, # Skicka den kombinerade konfigurationen
            scan_interval_seconds
        )
        _COMPONENT_LOGGER.debug("--- DEBUG INIT: SmartEVChargingCoordinator-objekt SKAPAT ---")

        # _async_first_refresh anropas av DataUpdateCoordinator's konstruktor eller när den sätts upp.
        # Vi behöver säkerställa att den körs innan plattformar sätts upp om de är beroende av initial data.
        # await coordinator.async_config_entry_first_refresh() # Detta anropas internt av HA nu.

        hass.data[DOMAIN][entry.entry_id]["coordinator"] = coordinator
        _COMPONENT_LOGGER.debug("--- DEBUG INIT: Koordinator lagrad i hass.data ---")

    except Exception as e:
        _COMPONENT_LOGGER.error("--- DEBUG INIT: FEL vid skapande av koordinator: %s ---", e, exc_info=True)
        if entry.entry_id in hass.data[DOMAIN]:
            if listener_remover := hass.data[DOMAIN][entry.entry_id].get("options_listener"):
                listener_remover()
            hass.data[DOMAIN].pop(entry.entry_id)
        return False

    try:
        # Plattformsuppsättning bör ske efter att koordinatorn är fullt initialiserad
        # och har gjort sin första refresh (vilket sker automatiskt).
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        _COMPONENT_LOGGER.debug("--- DEBUG INIT: async_forward_entry_setups KLAR för plattformar: %s ---", PLATFORMS)
    except Exception as e:
        _COMPONENT_LOGGER.error("--- DEBUG INIT: FEL vid async_forward_entry_setups: %s ---", e, exc_info=True)
        # Försök att städa upp om plattformsuppsättning misslyckas
        await async_unload_entry(hass, entry)
        return False

    # Säkerställ att koordinatorns listeners tas bort när Home Assistant stängs
    async def _shutdown_handler(event):
        _COMPONENT_LOGGER.debug("Home Assistant stängs ner, tar bort koordinatorns listeners för %s.", entry.entry_id)
        if coord := hass.data[DOMAIN].get(entry.entry_id, {}).get("coordinator"):
            await coord._remove_listeners()

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _shutdown_handler)
    )


    _COMPONENT_LOGGER.info("%s med entry_id %s är nu uppsatt och redo.", DOMAIN, entry.entry_id)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Avlastar en config entry."""
    _COMPONENT_LOGGER.info("Avlastar %s med entry_id %s (Titel: %s)", DOMAIN, entry.entry_id, entry.title)

    entry_data = hass.data[DOMAIN].get(entry.entry_id)
    all_unloaded_ok = True

    if entry_data:
        coordinator: SmartEVChargingCoordinator | None = entry_data.get("coordinator")
        if coordinator:
            await coordinator._remove_listeners()
            _COMPONENT_LOGGER.debug("Koordinatorns _remove_listeners anropad för %s", entry.entry_id)
            # Koordinatorn själv behöver inte "stängas av" mer än så här,
            # DataUpdateCoordinator hanterar sin egen avstängning av periodiska uppdateringar.

        options_listener_remover = entry_data.get("options_listener")
        if options_listener_remover:
            options_listener_remover() # Detta är entry.add_update_listener(...)
            _COMPONENT_LOGGER.debug("Options listener borttagen för %s", entry.entry_id)

        # Avlasta plattformarna
        unload_results = await asyncio.gather(
            *[hass.config_entries.async_forward_entry_unload(entry, platform) for platform in PLATFORMS],
            return_exceptions=True # Fånga eventuella undantag under avlastning
        )

        for i, result in enumerate(unload_results):
            platform = PLATFORMS[i]
            if isinstance(result, Exception):
                _COMPONENT_LOGGER.error("Fel vid avlastning av plattform %s för %s: %s", platform, entry.entry_id, result, exc_info=result)
                all_unloaded_ok = False
            elif not result: # Om async_forward_entry_unload returnerar False
                 _COMPONENT_LOGGER.warning("Misslyckades med att avlasta plattform %s för %s (returnerade False).", platform, entry.entry_id)
                 all_unloaded_ok = False
            else:
                _COMPONENT_LOGGER.debug("Plattform %s avlastad korrekt för %s.", platform, entry.entry_id)

        if all_unloaded_ok:
            hass.data[DOMAIN].pop(entry.entry_id, None) # Ta bort entry från hass.data
            _COMPONENT_LOGGER.info("All data för %s (entry_id: %s) borttagen från hass.data.", DOMAIN, entry.entry_id)
        else:
            _COMPONENT_LOGGER.warning("En eller flera plattformar kunde inte avlastas korrekt för %s. Försöker ändå ta bort data från hass.data.", entry.entry_id)
            hass.data[DOMAIN].pop(entry.entry_id, None) # Försök ändå ta bort

    else:
        _COMPONENT_LOGGER.debug("Ingen data hittades i hass.data för %s (entry_id: %s) att avlasta.", DOMAIN, entry.entry_id)

    # Återställ loggnivån till INFO om detta är den sista instansen som avlastas (valfritt, kan vara störande)
    # if not hass.data[DOMAIN]:
    #     _COMPONENT_LOGGER.setLevel(logging.INFO)
    #     _LOGGER.info("Sista instansen av %s avlastad, återställer loggnivå till INFO.", DOMAIN)

    return all_unloaded_ok