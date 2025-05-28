# File version: 2025-05-28 0.1.9
"""Config flow for Smart EV Charging integration."""
import logging
from typing import Any, Dict, OrderedDict

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
    CONF_DEBUG_LOGGING,
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL_SECONDS,
)

_LOGGER = logging.getLogger(__name__)

ALL_CONF_KEYS = [
    CONF_CHARGER_DEVICE, CONF_STATUS_SENSOR, CONF_CHARGER_ENABLED_SWITCH_ID,
    CONF_PRICE_SENSOR, CONF_SURCHARGE_HELPER, CONF_TIME_SCHEDULE_ENTITY,
    CONF_HOUSE_POWER_SENSOR, CONF_SOLAR_PRODUCTION_SENSOR,
    CONF_SOLAR_SCHEDULE_ENTITY, CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR,
    CONF_EV_POWER_SENSOR, CONF_SCAN_INTERVAL,
    CONF_EV_SOC_SENSOR, CONF_TARGET_SOC_LIMIT, CONF_DEBUG_LOGGING
]

OPTIONAL_ENTITY_CONF_KEYS = [
    CONF_TIME_SCHEDULE_ENTITY, CONF_SOLAR_SCHEDULE_ENTITY, CONF_SURCHARGE_HELPER,
    CONF_HOUSE_POWER_SENSOR, CONF_SOLAR_PRODUCTION_SENSOR,
    CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR, CONF_EV_POWER_SENSOR,
    CONF_EV_SOC_SENSOR
]
REQUIRED_CONF_SETUP_KEYS = [
    CONF_CHARGER_DEVICE, CONF_STATUS_SENSOR, CONF_CHARGER_ENABLED_SWITCH_ID, CONF_PRICE_SENSOR
]

HELP_URL_GLOBAL = "https://github.com/AlleHj/home-assistant-smart_ev_charging/blob/master/HELP.md"


def _build_common_schema(
    current_settings: dict[str, Any],
    user_input_for_repopulating: dict | None = None,
    is_options_flow: bool = False
) -> vol.Schema:
    """Bygger upp ett gemensamt Voluptuous-schema med CONF_ konstanter som nycklar."""

    def _get_current_value(conf_key: str, default_val: Any = None) -> Any:
        if user_input_for_repopulating is not None and conf_key in user_input_for_repopulating:
            form_val = user_input_for_repopulating[conf_key]
            return form_val

        existing_val = current_settings.get(conf_key, default_val)
        if conf_key in OPTIONAL_ENTITY_CONF_KEYS and existing_val is None:
            return ""
        return existing_val

    defined_fields = OrderedDict()
    defined_fields[vol.Required(CONF_CHARGER_DEVICE, default=_get_current_value(CONF_CHARGER_DEVICE, ""))] = DeviceSelector(DeviceSelectorConfig(integration="easee"))
    defined_fields[vol.Required(CONF_STATUS_SENSOR, default=_get_current_value(CONF_STATUS_SENSOR, ""))] = EntitySelector(EntitySelectorConfig(domain="sensor", multiple=False))
    defined_fields[vol.Required(CONF_CHARGER_ENABLED_SWITCH_ID, default=_get_current_value(CONF_CHARGER_ENABLED_SWITCH_ID, ""))] = EntitySelector(EntitySelectorConfig(domain="switch", multiple=False))
    defined_fields[vol.Required(CONF_PRICE_SENSOR, default=_get_current_value(CONF_PRICE_SENSOR, ""))] = EntitySelector(EntitySelectorConfig(domain="sensor", multiple=False))

    defined_fields[vol.Optional(CONF_SURCHARGE_HELPER, default=_get_current_value(CONF_SURCHARGE_HELPER, ""))] = EntitySelector(EntitySelectorConfig(domain=["sensor", "input_number"], multiple=False))
    defined_fields[vol.Optional(CONF_TIME_SCHEDULE_ENTITY, default=_get_current_value(CONF_TIME_SCHEDULE_ENTITY, ""))] = EntitySelector(EntitySelectorConfig(domain="schedule", multiple=False))
    defined_fields[vol.Optional(CONF_HOUSE_POWER_SENSOR, default=_get_current_value(CONF_HOUSE_POWER_SENSOR, ""))] = EntitySelector(EntitySelectorConfig(domain="sensor", device_class=SensorDeviceClass.POWER, multiple=False))
    defined_fields[vol.Optional(CONF_SOLAR_PRODUCTION_SENSOR, default=_get_current_value(CONF_SOLAR_PRODUCTION_SENSOR, ""))] = EntitySelector(EntitySelectorConfig(domain="sensor", device_class=SensorDeviceClass.POWER, multiple=False))
    defined_fields[vol.Optional(CONF_SOLAR_SCHEDULE_ENTITY, default=_get_current_value(CONF_SOLAR_SCHEDULE_ENTITY, ""))] = EntitySelector(EntitySelectorConfig(domain="schedule", multiple=False))
    defined_fields[vol.Optional(CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR, default=_get_current_value(CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR, ""))] = EntitySelector(EntitySelectorConfig(domain="sensor", multiple=False))
    defined_fields[vol.Optional(CONF_EV_POWER_SENSOR, default=_get_current_value(CONF_EV_POWER_SENSOR, ""))] = EntitySelector(EntitySelectorConfig(domain="sensor", device_class=SensorDeviceClass.POWER, multiple=False))
    defined_fields[vol.Optional(CONF_EV_SOC_SENSOR, default=_get_current_value(CONF_EV_SOC_SENSOR, ""))] = EntitySelector(EntitySelectorConfig(domain="sensor", device_class=SensorDeviceClass.BATTERY, multiple=False))

    defined_fields[vol.Optional(CONF_TARGET_SOC_LIMIT, default=_get_current_value(CONF_TARGET_SOC_LIMIT))] = NumberSelector(NumberSelectorConfig(min=0, max=100, step=0.5, mode=NumberSelectorMode.BOX, unit_of_measurement="%"))
    defined_fields[vol.Optional(CONF_SCAN_INTERVAL, default=_get_current_value(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_SECONDS))] = NumberSelector(NumberSelectorConfig(min=10, max=3600, step=1, mode=NumberSelectorMode.BOX, unit_of_measurement="sekunder"))
    defined_fields[vol.Optional(CONF_DEBUG_LOGGING, default=_get_current_value(CONF_DEBUG_LOGGING, False))] = BooleanSelector(BooleanSelectorConfig())

    final_schema = OrderedDict()
    for key_marker, selector_value in defined_fields.items():
        conf_key_str = str(key_marker.schema)
        current_default_from_marker = key_marker.default

        if is_options_flow:
            final_schema[vol.Optional(conf_key_str, default=current_default_from_marker)] = selector_value
        else:
            val_for_default_in_setup = current_default_from_marker
            # För nya, valfria entitetsfält, sätt default till "" för att visa tomt i UI
            if user_input_for_repopulating is None and conf_key_str in OPTIONAL_ENTITY_CONF_KEYS:
                val_for_default_in_setup = ""
            # För nya, valfria nummerfält utan specifik konstant default, sätt till UNDEFINED om du inte vill förifylla
            elif user_input_for_repopulating is None and conf_key_str == CONF_TARGET_SOC_LIMIT:
                 val_for_default_in_setup = vol.UNDEFINED
            elif user_input_for_repopulating is None and conf_key_str == CONF_SCAN_INTERVAL:
                val_for_default_in_setup = DEFAULT_SCAN_INTERVAL_SECONDS
            elif user_input_for_repopulating is None and conf_key_str == CONF_DEBUG_LOGGING:
                val_for_default_in_setup = False

            if conf_key_str in REQUIRED_CONF_SETUP_KEYS:
                current_default_for_required = _get_current_value(conf_key_str, "") # Använd "" som fallback för _get_current_value
                if user_input_for_repopulating is None: # Om det är ett helt nytt formulär, tvinga val
                    current_default_for_required = vol.UNDEFINED
                final_schema[vol.Required(conf_key_str, default=current_default_for_required )] = selector_value
            else:
                final_schema[vol.Optional(conf_key_str, default=val_for_default_in_setup)] = selector_value
    return vol.Schema(final_schema)


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
        current_settings = {**self.config_entry.data, **self.config_entry.options}

        if user_input is not None:
            options_to_save = {} # Detta kommer att bli de nya kompletta options
            validation_ok = True

            for conf_key in ALL_CONF_KEYS:
                value = user_input.get(conf_key)

                if conf_key == CONF_DEBUG_LOGGING:
                    options_to_save[conf_key] = isinstance(value, bool) and value
                elif conf_key in OPTIONAL_ENTITY_CONF_KEYS:
                    # Konvertera tom sträng (från EntitySelector) till None vid sparning
                    options_to_save[conf_key] = None if value == "" or value is None else value
                elif conf_key == CONF_TARGET_SOC_LIMIT:
                    if value is None or value == "" or str(value).strip() == "":
                        options_to_save[conf_key] = None
                    else:
                        try:
                            soc_val = float(value)
                            if not (0 <= soc_val <= 100):
                                errors[conf_key] = "invalid_target_soc"; validation_ok = False
                            else:
                                options_to_save[conf_key] = soc_val
                        except (ValueError, TypeError):
                            errors[conf_key] = "invalid_target_soc"; validation_ok = False
                elif conf_key == CONF_SCAN_INTERVAL:
                    # Om fältet är tomt i options, ska vi inte falla tillbaka till data,
                    # utan snarare tillåta att det är "osatt" i options, eller använda en default om det är det som är avsikten.
                    # Här sätter vi det till vad som än finns i user_input eller default om user_input är tomt.
                    if value is None or value == "" or str(value).strip() == "":
                        # Om användaren rensar, använd den ursprungliga default-konstanten,
                        # inte värdet från self.config_entry.data
                        options_to_save[conf_key] = DEFAULT_SCAN_INTERVAL_SECONDS
                    else:
                        try:
                            scan_val = int(value)
                            if not (10 <= scan_val <= 3600):
                                errors[conf_key] = "invalid_scan_interval"; validation_ok = False
                            else:
                                options_to_save[conf_key] = scan_val
                        except (ValueError, TypeError):
                            errors[conf_key] = "invalid_scan_interval"; validation_ok = False
                elif value is not None : # För fält som har ett värde från formuläret
                    options_to_save[conf_key] = value
                elif conf_key in REQUIRED_CONF_SETUP_KEYS: # Obligatoriska fält bör alltid ha ett värde
                    options_to_save[conf_key] = current_settings.get(conf_key) # Behåll gammalt om input är None
                else: # Andra valfria fält som är None i input
                    options_to_save[conf_key] = None


            if not validation_ok:
                return self.async_show_form(
                    step_id="init",
                    data_schema=_build_common_schema(current_settings, user_input, is_options_flow=True),
                    errors=errors,
                    description_placeholders={"help_url": HELP_URL_GLOBAL}
                )

            _LOGGER.debug("OptionsFlow: Sparar options: %s", options_to_save)
            # Vi sparar hela options_to_save. Home Assistant hanterar att bara lagra det som
            # faktiskt utgör "options" som ett lager ovanpå "data".
            # Om en nyckel i options_to_save har samma värde som i config_entry.data,
            # kan HA undvika att skriva den till storage, men det är en intern optimering.
            # Att skicka hela setet säkerställer att `None` för rensade fält verkligen skickas.
            return self.async_create_entry(title="", data=options_to_save)

        return self.async_show_form(
            step_id="init",
            data_schema=_build_common_schema(current_settings, None, is_options_flow=True),
            errors=errors,
            description_placeholders={"help_url": HELP_URL_GLOBAL}
        )


class SmartEVChargingConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: Dict[str, str] = {}

        if user_input is not None:
            data_to_save = {}
            validation_ok = True

            for conf_key in ALL_CONF_KEYS:
                value = user_input.get(conf_key)

                if conf_key == CONF_DEBUG_LOGGING:
                    data_to_save[conf_key] = isinstance(value, bool) and value
                elif conf_key in OPTIONAL_ENTITY_CONF_KEYS:
                    data_to_save[conf_key] = None if value == "" or value is None else value
                elif conf_key == CONF_TARGET_SOC_LIMIT:
                    if value is None or value == "" or str(value).strip() == "":
                        data_to_save[conf_key] = None
                    else:
                        try:
                            soc_val = float(value)
                            if not (0 <= soc_val <= 100):
                                errors[conf_key] = "invalid_target_soc"; validation_ok = False
                            else: data_to_save[conf_key] = soc_val
                        except (ValueError, TypeError):
                            errors[conf_key] = "invalid_target_soc"; validation_ok = False
                elif conf_key == CONF_SCAN_INTERVAL:
                    if value is None or value == "" or str(value).strip() == "":
                        data_to_save[conf_key] = DEFAULT_SCAN_INTERVAL_SECONDS
                    else:
                        try:
                            scan_val = int(value)
                            if not (10 <= scan_val <= 3600):
                                errors[conf_key] = "invalid_scan_interval"; validation_ok = False
                            else: data_to_save[conf_key] = scan_val
                        except (ValueError, TypeError):
                            errors[conf_key] = "invalid_scan_interval"; validation_ok = False
                elif value is not None:
                    data_to_save[conf_key] = value
                elif conf_key in REQUIRED_CONF_SETUP_KEYS:
                     errors[conf_key] = "required_field"; validation_ok = False
                else:
                    data_to_save[conf_key] = None

            if not validation_ok:
                 return self.async_show_form(
                     step_id="user",
                     data_schema=_build_common_schema({}, user_input, is_options_flow=False),
                     errors=errors,
                     description_placeholders={"help_url": HELP_URL_GLOBAL}
                 )

            _LOGGER.debug("Initial konfigurationsdata att spara: %s", data_to_save)
            await self.async_set_unique_id(f"{DOMAIN}_smart_charger_main_instance")
            self._abort_if_unique_id_configured()

            return self.async_create_entry(title=DEFAULT_NAME, data=data_to_save)

        return self.async_show_form(
            step_id="user",
            data_schema=_build_common_schema({}, None, is_options_flow=False),
            errors=errors,
            description_placeholders={"help_url": HELP_URL_GLOBAL}
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> SmartEVChargingOptionsFlowHandler:
        return SmartEVChargingOptionsFlowHandler(config_entry)