# File version: 2025-06-05 0.2.0
import logging
from datetime import timedelta
import asyncio

from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP

from .const import (
    DOMAIN,
    CONF_SCAN_INTERVAL,
    CONF_DEBUG_LOGGING,
    DEFAULT_SCAN_INTERVAL_SECONDS,
)
from .coordinator import SmartEVChargingCoordinator

_LOGGER = logging.getLogger(__name__)
_COMPONENT_LOGGER = logging.getLogger(f"custom_components.{DOMAIN}")

PLATFORMS = ["switch", "number", "sensor"]  # Definiera vilka plattformar som ska laddas


def _update_logger_level(debug_enabled: bool) -> None:
    """Uppdaterar loggnivån för integrationsspecifika loggers."""
    if debug_enabled:
        _COMPONENT_LOGGER.setLevel(logging.DEBUG)
        _LOGGER.info("Debug-loggning aktiverad för %s.", DOMAIN)
    else:
        _COMPONENT_LOGGER.setLevel(logging.INFO)
        # _LOGGER.info("Debug-loggning avaktiverad för %s. Standardnivå INFO.", DOMAIN) # Kan tas bort för mindre brus
    # Logger för __name__ (denna fil) kan också justeras om nödvändigt, men oftast är det _COMPONENT_LOGGER som är intressant.


async def async_options_update_listener(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Hanterar uppdateringar av alternativ från UI."""
    _LOGGER.info(
        "Alternativ uppdaterade för %s (entry_id: %s), laddar om integrationen.",
        entry.title,
        entry.entry_id,
    )
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Konfigurerar Smart EV Charging från en config entry."""
    _LOGGER.debug(
        "--- DEBUG INIT: async_setup_entry STARTAR för %s ---", entry.entry_id
    )

    # Kombinera data och options, där options har företräde. Används lokalt här.
    current_config_for_init = {**entry.data, **entry.options}
    _LOGGER.debug(
        "--- DEBUG INIT: Använder lokal config för setup: %s ---",
        current_config_for_init,
    )

    # Ställ in loggningsnivå baserat på konfigurationen (innan koordinatorn skapas)
    debug_enabled = current_config_for_init.get(CONF_DEBUG_LOGGING, False)
    _update_logger_level(debug_enabled)

    hass.data.setdefault(DOMAIN, {})
    # Lagra config_entry direkt, koordinatorn kan komma åt entry.data och entry.options
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": None,  # Skapas nedan
        "options_listener": entry.add_update_listener(async_options_update_listener),
    }
    _LOGGER.debug(
        "--- DEBUG INIT: hass.data initialiserad för entry_id %s ---", entry.entry_id
    )

    # Validera och hämta scan_interval
    scan_interval_value = current_config_for_init.get(
        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_SECONDS
    )
    scan_interval_seconds: int
    try:
        scan_interval_seconds = int(scan_interval_value)
        if scan_interval_seconds < 10:
            _COMPONENT_LOGGER.warning(
                "Scan interval för lågt (%s sekunder), sätter till 10 sekunder.",
                scan_interval_seconds,
            )
            scan_interval_seconds = 10
    except (ValueError, TypeError):
        _COMPONENT_LOGGER.warning(
            "Ogiltigt värde för scan_interval ('%s'), använder default %s sekunder.",
            scan_interval_value,
            DEFAULT_SCAN_INTERVAL_SECONDS,
        )
        scan_interval_seconds = DEFAULT_SCAN_INTERVAL_SECONDS

    _COMPONENT_LOGGER.debug(
        "--- DEBUG INIT: Koordinatorns scan-intervall kommer att vara: %s sekunder ---",
        scan_interval_seconds,
    )

    try:
        coordinator = SmartEVChargingCoordinator(
            hass,
            entry,  # Koordinatorn kan själv hämta config från entry.data | entry.options
            scan_interval_seconds,  # Skicka med det validerade intervallet
        )
        _COMPONENT_LOGGER.debug(
            "--- DEBUG INIT: SmartEVChargingCoordinator-objekt SKAPAT ---"
        )

        # Koordinatorn anropar _async_first_refresh internt via DataUpdateCoordinator.
        # Men vi måste vänta på att den första datan hämtas innan vi sätter upp plattformar
        # om de är beroende av data som koordinatorn tillhandahåller initialt.
        await (
            coordinator.async_config_entry_first_refresh()
        )  # Vänta på första uppdateringen

        hass.data[DOMAIN][entry.entry_id]["coordinator"] = coordinator
        _COMPONENT_LOGGER.debug("--- DEBUG INIT: Koordinator lagrad i hass.data ---")

    except Exception as e:
        _COMPONENT_LOGGER.error(
            "--- DEBUG INIT: FEL vid skapande eller första refresh av koordinator: %s ---",
            e,
            exc_info=True,
        )
        # Städa upp om koordinatorn misslyckades
        if entry.entry_id in hass.data[DOMAIN]:
            if listener_remover := hass.data[DOMAIN][entry.entry_id].get(
                "options_listener"
            ):
                listener_remover()
            hass.data[DOMAIN].pop(entry.entry_id)
        return False

    # Sätt upp plattformar (sensor, switch, number)
    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        _COMPONENT_LOGGER.debug(
            "--- DEBUG INIT: async_forward_entry_setups KLAR för plattformar: %s ---",
            PLATFORMS,
        )
    except Exception as e:
        _COMPONENT_LOGGER.error(
            "--- DEBUG INIT: FEL vid async_forward_entry_setups: %s ---",
            e,
            exc_info=True,
        )
        await async_unload_entry(hass, entry)  # Försök städa upp
        return False

    # Säkerställ att koordinatorns listeners tas bort när Home Assistant stängs
    async def _shutdown_handler(event):  # event-parametern är nödvändig för lyssnaren
        _COMPONENT_LOGGER.debug(
            "Home Assistant stängs ner, anropar koordinatorns cleanup för %s.",
            entry.entry_id,
        )
        if coord := hass.data[DOMAIN].get(entry.entry_id, {}).get("coordinator"):
            # Antag att koordinatorn har en cleanup-metod för att ta bort sina egna lyssnare etc.
            await coord.cleanup()

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _shutdown_handler)
    )

    _COMPONENT_LOGGER.info(
        "%s med entry_id %s är nu uppsatt och redo.", DOMAIN, entry.entry_id
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Avlastar en config entry."""
    _COMPONENT_LOGGER.info(
        "Avlastar %s med entry_id %s (Titel: %s)", DOMAIN, entry.entry_id, entry.title
    )

    entry_data = hass.data[DOMAIN].get(entry.entry_id)
    all_unloaded_ok = True

    if entry_data:
        coordinator: SmartEVChargingCoordinator | None = entry_data.get("coordinator")
        if coordinator:
            # Anropa en dedikerad cleanup-metod på koordinatorn
            await coordinator.cleanup()  # Denna metod bör hantera _remove_listeners()
            _COMPONENT_LOGGER.debug(
                "Koordinatorns cleanup-metod anropad för %s", entry.entry_id
            )

        options_listener_remover = entry_data.get("options_listener")
        if options_listener_remover:
            options_listener_remover()
            _COMPONENT_LOGGER.debug("Options listener borttagen för %s", entry.entry_id)

        unload_results = await hass.config_entries.async_unload_platforms(
            entry, PLATFORMS
        )

        # async_unload_platforms returnerar True om alla lyckades, annars False.
        if not unload_results:  # Om någon plattform misslyckades att avlastas
            _COMPONENT_LOGGER.warning(
                "En eller flera plattformar kunde inte avlastas korrekt för %s.",
                entry.entry_id,
            )
            all_unloaded_ok = False
        else:
            _COMPONENT_LOGGER.debug(
                "Alla plattformar (%s) avlastade korrekt för %s.",
                PLATFORMS,
                entry.entry_id,
            )

        # Ta bort data oavsett om allt avlastades OK eller inte, för att undvika rester.
        hass.data[DOMAIN].pop(entry.entry_id, None)
        if all_unloaded_ok:
            _COMPONENT_LOGGER.info(
                "All data för %s (entry_id: %s) borttagen från hass.data.",
                DOMAIN,
                entry.entry_id,
            )
        else:
            _COMPONENT_LOGGER.warning(
                "Data för %s (entry_id: %s) borttagen från hass.data, trots tidigare avlastningsproblem.",
                DOMAIN,
                entry.entry_id,
            )

    else:
        _COMPONENT_LOGGER.debug(
            "Ingen data hittades i hass.data för %s (entry_id: %s) att avlasta.",
            DOMAIN,
            entry.entry_id,
        )

    return all_unloaded_ok
