# File version: 2025-05-28 0.1.2
"""Config flow for Smart EV Charging integration."""
import logging
from typing import Any, Dict

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigEntry, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    DeviceSelectorConfig,
    DeviceSelector,
    EntitySelectorConfig,
    EntitySelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    BooleanSelector,
    BooleanSelectorConfig,
)
from homeassistant.components.sensor import SensorDeviceClass

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
    CONF_DEBUG_LOGGING, # Importerad
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL_SECONDS,
)

_LOGGER = logging.getLogger(__name__)

ALL_SCHEMA_KEYS = [
    CONF_CHARGER_DEVICE, CONF_STATUS_SENSOR, CONF_CHARGER_ENABLED_SWITCH_ID,
    CONF_PRICE_SENSOR, CONF_SURCHARGE_HELPER, CONF_TIME_SCHEDULE_ENTITY,
    CONF_HOUSE_POWER_SENSOR, CONF_SOLAR_PRODUCTION_SENSOR,
    CONF_SOLAR_SCHEDULE_ENTITY, CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR,
    CONF_EV_POWER_SENSOR, CONF_SCAN_INTERVAL,
    CONF_EV_SOC_SENSOR, CONF_TARGET_SOC_LIMIT, CONF_DEBUG_LOGGING # Tillagd
]
# Obligatoriska fält vid initial setup
REQUIRED_SETUP_KEYS = [
    CONF_CHARGER_DEVICE, CONF_STATUS_SENSOR, CONF_CHARGER_ENABLED_SWITCH_ID, CONF_PRICE_SENSOR
]

OPTIONAL_ENTITY_SELECTOR_KEYS = [
    CONF_TIME_SCHEDULE_ENTITY, CONF_SOLAR_SCHEDULE_ENTITY, CONF_SURCHARGE_HELPER,
    CONF_HOUSE_POWER_SENSOR, CONF_SOLAR_PRODUCTION_SENSOR,
    CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR, CONF_EV_POWER_SENSOR,
    CONF_EV_SOC_SENSOR
]

# Gemensam funktion för att bygga schema för både config och options
def _build_common_schema(
    handler: ConfigFlow | OptionsFlow,
    current_values: dict | None = None,
    is_options_flow: bool = False
) -> vol.Schema:
    """Bygger upp ett gemensamt Voluptuous-schema för konfiguration och alternativ."""

    # Hämta befintliga värden (antingen från config_entry.data, config_entry.options eller formulärdata)
    def _get_value(key: str, default_val: Any = None) -> Any:
        if current_values is not None and key in current_values:
            form_val = current_values[key]
            # Hantera tomma strängar för valfria entitetsväljare korrekt
            if key in OPTIONAL_ENTITY_SELECTOR_KEYS and form_val == "":
                return None
            # Behåll strängformat för nummerfält om formuläret postar det (för validering)
            if isinstance(form_val, str) and key in [CONF_SCAN_INTERVAL, CONF_TARGET_SOC_LIMIT]:
                return form_val
            return form_val

        # För OptionsFlow, hämta från options först, sedan data. För ConfigFlow, hämta från data (om entry finns).
        if is_options_flow and isinstance(handler, SmartEVChargingOptionsFlowHandler):
            return handler.config_entry.options.get(key, handler.config_entry.data.get(key, default_val))
        # För initial ConfigFlow (user step), kan det finnas current_values från formuläret.
        # Om inget finns där, använd default_val.
        return default_val

    # Schema definition
    schema_definition = {
        vol.Required(CONF_CHARGER_DEVICE, default=_get_value(CONF_CHARGER_DEVICE)): DeviceSelector(
            DeviceSelectorConfig(integration="easee")
        ),
        vol.Required(CONF_STATUS_SENSOR, default=_get_value(CONF_STATUS_SENSOR)): EntitySelector(
            EntitySelectorConfig(domain="sensor", multiple=False)
        ),
        vol.Required(CONF_CHARGER_ENABLED_SWITCH_ID, default=_get_value(CONF_CHARGER_ENABLED_SWITCH_ID)): EntitySelector(
            EntitySelectorConfig(domain="switch", multiple=False)
        ),
        vol.Required(CONF_PRICE_SENSOR, default=_get_value(CONF_PRICE_SENSOR)): EntitySelector(
            EntitySelectorConfig(domain="sensor", multiple=False)
        ),
        vol.Optional(CONF_SURCHARGE_HELPER, description={"suggested_value": _get_value(CONF_SURCHARGE_HELPER)}): EntitySelector(
            EntitySelectorConfig(domain=["sensor", "input_number"], multiple=False)
        ),
        vol.Optional(CONF_TIME_SCHEDULE_ENTITY, description={"suggested_value": _get_value(CONF_TIME_SCHEDULE_ENTITY)}): EntitySelector(
            EntitySelectorConfig(domain="schedule", multiple=False)
        ),
        vol.Optional(CONF_HOUSE_POWER_SENSOR, description={"suggested_value": _get_value(CONF_HOUSE_POWER_SENSOR)}): EntitySelector(
            EntitySelectorConfig(domain="sensor", device_class=SensorDeviceClass.POWER, multiple=False)
        ),
        vol.Optional(CONF_SOLAR_PRODUCTION_SENSOR, description={"suggested_value": _get_value(CONF_SOLAR_PRODUCTION_SENSOR)}): EntitySelector(
            EntitySelectorConfig(domain="sensor", device_class=SensorDeviceClass.POWER, multiple=False)
        ),
        vol.Optional(CONF_SOLAR_SCHEDULE_ENTITY, description={"suggested_value": _get_value(CONF_SOLAR_SCHEDULE_ENTITY)}): EntitySelector(
            EntitySelectorConfig(domain="schedule", multiple=False)
        ),
        vol.Optional(CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR, description={"suggested_value": _get_value(CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR)}): EntitySelector(
            EntitySelectorConfig(domain="sensor", multiple=False)
        ),
        vol.Optional(CONF_EV_POWER_SENSOR, description={"suggested_value": _get_value(CONF_EV_POWER_SENSOR)}): EntitySelector(
            EntitySelectorConfig(domain="sensor", device_class=SensorDeviceClass.POWER, multiple=False)
        ),
        vol.Optional(CONF_EV_SOC_SENSOR, description={"suggested_value": _get_value(CONF_EV_SOC_SENSOR)}): EntitySelector(
            EntitySelectorConfig(domain="sensor", device_class=SensorDeviceClass.BATTERY, multiple=False)
        ),
        vol.Optional(CONF_TARGET_SOC_LIMIT, description={"suggested_value": _get_value(CONF_TARGET_SOC_LIMIT, None)}): NumberSelector(
            NumberSelectorConfig(min=0, max=100, step=0.5, mode=NumberSelectorMode.BOX, unit_of_measurement="%")
        ),
        vol.Optional(CONF_SCAN_INTERVAL, default=_get_value(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_SECONDS)): NumberSelector(
            NumberSelectorConfig(min=10, max=3600, step=1, mode=NumberSelectorMode.BOX, unit_of_measurement="sekunder")
        ),
        vol.Optional(CONF_DEBUG_LOGGING, default=_get_value(CONF_DEBUG_LOGGING, False)): BooleanSelector(BooleanSelectorConfig()),
    }
    # Om det är initial setup, är vissa fält obligatoriska utan default från existerande entry.
    # Annars (OptionsFlow), är de ifyllda från existerande config/options.
    if not is_options_flow:
        final_schema = {}
        for key, selector in schema_definition.items():
            if key.schema in REQUIRED_SETUP_KEYS: # key är ett vol.Marker objekt
                final_schema[vol.Required(key.schema, default=_get_value(key.schema))] = selector
            else: # För Optional
                final_schema[key] = selector # key är redan ett vol.Optional
        return vol.Schema(final_schema)

    return vol.Schema(schema_definition)


class SmartEVChargingOptionsFlowHandler(OptionsFlow):
    """Hanterar alternativflödet för Smart EV Charging."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initierar alternativflödet."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Hanterar alternativen."""
        errors: Dict[str, str] = {}
        current_schema = _build_common_schema(self, self.config_entry.options, is_options_flow=True)

        if user_input is not None:
            options_to_save = {}

            for key in ALL_SCHEMA_KEYS: # Iterera över alla möjliga nycklar
                value = user_input.get(key)

                if key == CONF_DEBUG_LOGGING:
                    options_to_save[key] = isinstance(value, bool) and value
                elif key in OPTIONAL_ENTITY_SELECTOR_KEYS:
                    options_to_save[key] = None if value == "" or value is None else value
                elif key == CONF_TARGET_SOC_LIMIT:
                    if value is None or value == "":
                        options_to_save[key] = None
                    else:
                        try:
                            soc_val = float(value)
                            if not (0 <= soc_val <= 100):
                                errors[key] = "invalid_target_soc"
                            else:
                                options_to_save[key] = soc_val
                        except (ValueError, TypeError):
                            errors[key] = "invalid_target_soc"
                elif key == CONF_SCAN_INTERVAL:
                    # Använd config_entry.data om värdet är tomt i options, annars default
                    current_scan_interval = self.config_entry.data.get(key, DEFAULT_SCAN_INTERVAL_SECONDS)
                    if value is None or value == "":
                         options_to_save[key] = current_scan_interval
                    else:
                        try:
                            scan_val = int(value)
                            if not (10 <= scan_val <= 3600):
                                errors[key] = "invalid_scan_interval"
                            else:
                                options_to_save[key] = scan_val
                        except (ValueError, TypeError):
                            errors[key] = "invalid_scan_interval"
                elif value is not None: # För obligatoriska fält som inte är None
                    options_to_save[key] = value
                else:
                    # Behåll befintligt värde från data om ett obligatoriskt fält oväntat är None,
                    # eller om ett valfritt fält inte explicit hanteras ovan och är None.
                    options_to_save[key] = self.config_entry.data.get(key)


            if errors:
                # Återpopulera formuläret med de värden användaren matat in som orsakade felet
                current_schema_repop = _build_common_schema(self, user_input, is_options_flow=True)
                return self.async_show_form(
                    step_id="init", data_schema=current_schema_repop, errors=errors,
                    description_placeholders={"help_url": "https://github.com/AlleHj/home-assistant-smart_ev_charging/blob/master/HELP.md"}
                )

            _LOGGER.debug("Sparar alternativ från OptionsFlow: %s", options_to_save)
            # Detta uppdaterar config_entry.options och triggar lyssnaren i __init__.py
            return self.async_create_entry(title="", data=options_to_save)

        # Visa formuläret initialt, populera med existerande options (eller data som fallback)
        return self.async_show_form(
            step_id="init", data_schema=current_schema, errors=errors,
            description_placeholders={"help_url": "https://github.com/AlleHj/home-assistant-smart_ev_charging/blob/master/HELP.md"}
        )


class SmartEVChargingConfigFlow(ConfigFlow, domain=DOMAIN):
    """Hanterar konfigurationsflödet för Smart EV Charging."""
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> SmartEVChargingOptionsFlowHandler:
        """Hämtar alternativflödeshanteraren."""
        return SmartEVChargingOptionsFlowHandler(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Hanterar användarsteget i konfigurationsflödet."""
        errors: Dict[str, str] = {}
        current_schema = _build_common_schema(self, user_input, is_options_flow=False)

        if user_input is not None:
            data_to_save = {}
            # Validera och spara varje nyckel från schemat
            for key_marker in current_schema.schema:
                key = str(key_marker.schema) # Hämta den faktiska nyckelsträngen
                value = user_input.get(key)

                if key == CONF_DEBUG_LOGGING:
                    data_to_save[key] = isinstance(value, bool) and value
                elif key in OPTIONAL_ENTITY_SELECTOR_KEYS:
                    data_to_save[key] = None if value == "" or value is None else value
                elif key == CONF_TARGET_SOC_LIMIT:
                    if value is None or value == "":
                        data_to_save[key] = None # Spara som None om tomt
                    else:
                        try:
                            soc_val = float(value)
                            if not (0 <= soc_val <= 100):
                                errors[key] = "invalid_target_soc"
                            data_to_save[key] = soc_val
                        except (ValueError, TypeError):
                            errors[key] = "invalid_target_soc"
                elif key == CONF_SCAN_INTERVAL:
                    if value is None or value == "": # Om tomt, använd default
                        data_to_save[key] = DEFAULT_SCAN_INTERVAL_SECONDS
                    else:
                        try:
                            scan_val = int(value)
                            if not (10 <= scan_val <= 3600):
                                errors[key] = "invalid_scan_interval"
                            data_to_save[key] = scan_val
                        except (ValueError, TypeError):
                            errors[key] = "invalid_scan_interval"
                elif value is not None: # För obligatoriska fält
                    data_to_save[key] = value
                else: # För valfria fält som inte angivits (och inte är entitetsväljare)
                    data_to_save[key] = None


            if errors:
                 # Återpopulera formuläret med de värden användaren matat in som orsakade felet
                 return self.async_show_form(step_id="user", data_schema=_build_common_schema(self, user_input, is_options_flow=False), errors=errors,
                                            description_placeholders={"help_url": "https://github.com/AlleHj/home-assistant-smart_ev_charging/blob/master/HELP.md"})

            _LOGGER.debug("Initial konfigurationsdata att spara: %s", data_to_save)
            # Sätt ett unikt ID för att förhindra flera instanser (kan tas bort om flera instanser önskas)
            await self.async_set_unique_id(f"{DOMAIN}_smart_charger_main_instance")
            self._abort_if_unique_id_configured()

            return self.async_create_entry(title=DEFAULT_NAME, data=data_to_save)

        # Visa formuläret för första gången
        return self.async_show_form(step_id="user", data_schema=current_schema, errors=errors,
                                   description_placeholders={"help_url": "https://github.com/AlleHj/home-assistant-smart_ev_charging/blob/master/HELP.md"})