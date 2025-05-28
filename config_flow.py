# File version: 2025-05-28 0.1.7
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
    CONF_DEBUG_LOGGING,
    DEFAULT_NAME, # Används som fallback titel om translation saknas
    DEFAULT_SCAN_INTERVAL_SECONDS,
)

_LOGGER = logging.getLogger(__name__)

# Alla CONF_ konstanter som används i schemat
ALL_CONF_KEYS = [
    CONF_CHARGER_DEVICE, CONF_STATUS_SENSOR, CONF_CHARGER_ENABLED_SWITCH_ID,
    CONF_PRICE_SENSOR, CONF_SURCHARGE_HELPER, CONF_TIME_SCHEDULE_ENTITY,
    CONF_HOUSE_POWER_SENSOR, CONF_SOLAR_PRODUCTION_SENSOR,
    CONF_SOLAR_SCHEDULE_ENTITY, CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR,
    CONF_EV_POWER_SENSOR, CONF_SCAN_INTERVAL,
    CONF_EV_SOC_SENSOR, CONF_TARGET_SOC_LIMIT, CONF_DEBUG_LOGGING
]

# CONF_ konstanter för valfria entitetsväljare (används för att hantera tomma strängar)
OPTIONAL_ENTITY_CONF_KEYS = [
    CONF_TIME_SCHEDULE_ENTITY, CONF_SOLAR_SCHEDULE_ENTITY, CONF_SURCHARGE_HELPER,
    CONF_HOUSE_POWER_SENSOR, CONF_SOLAR_PRODUCTION_SENSOR,
    CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR, CONF_EV_POWER_SENSOR,
    CONF_EV_SOC_SENSOR
]
# Obligatoriska fält (med deras CONF_ konstanter) vid initial setup
REQUIRED_CONF_SETUP_KEYS = [
    CONF_CHARGER_DEVICE, CONF_STATUS_SENSOR, CONF_CHARGER_ENABLED_SWITCH_ID, CONF_PRICE_SENSOR
]


def _build_common_schema(
    current_settings: dict[str, Any], # Antingen entry.data eller entry.options, eller {} för ny setup
    user_input_for_repopulating: dict | None = None,
    is_options_flow: bool = False
) -> vol.Schema:
    """Bygger upp ett gemensamt Voluptuous-schema med CONF_ konstanter som nycklar."""

    def _get_current_value(conf_key: str, default_val: Any = None) -> Any:
        if user_input_for_repopulating is not None and conf_key in user_input_for_repopulating:
            form_val = user_input_for_repopulating[conf_key]
            if conf_key in OPTIONAL_ENTITY_CONF_KEYS and form_val == "":
                return None
            if isinstance(form_val, str) and conf_key in [CONF_SCAN_INTERVAL, CONF_TARGET_SOC_LIMIT]:
                return form_val # Behåll som sträng om det kommer från formuläret med fel
            return form_val
        return current_settings.get(conf_key, default_val)

    schema_fields = {
        vol.Required(CONF_CHARGER_DEVICE, default=_get_current_value(CONF_CHARGER_DEVICE)): DeviceSelector(
            DeviceSelectorConfig(integration="easee")
        ),
        vol.Required(CONF_STATUS_SENSOR, default=_get_current_value(CONF_STATUS_SENSOR)): EntitySelector(
            EntitySelectorConfig(domain="sensor", multiple=False)
        ),
        vol.Required(CONF_CHARGER_ENABLED_SWITCH_ID, default=_get_current_value(CONF_CHARGER_ENABLED_SWITCH_ID)): EntitySelector(
            EntitySelectorConfig(domain="switch", multiple=False)
        ),
        vol.Required(CONF_PRICE_SENSOR, default=_get_current_value(CONF_PRICE_SENSOR)): EntitySelector(
            EntitySelectorConfig(domain="sensor", multiple=False)
        ),
        vol.Optional(CONF_SURCHARGE_HELPER, default=_get_current_value(CONF_SURCHARGE_HELPER)): EntitySelector(
            EntitySelectorConfig(domain=["sensor", "input_number"], multiple=False)
        ),
        vol.Optional(CONF_TIME_SCHEDULE_ENTITY, default=_get_current_value(CONF_TIME_SCHEDULE_ENTITY)): EntitySelector(
            EntitySelectorConfig(domain="schedule", multiple=False)
        ),
        vol.Optional(CONF_HOUSE_POWER_SENSOR, default=_get_current_value(CONF_HOUSE_POWER_SENSOR)): EntitySelector(
            EntitySelectorConfig(domain="sensor", device_class=SensorDeviceClass.POWER, multiple=False)
        ),
        vol.Optional(CONF_SOLAR_PRODUCTION_SENSOR, default=_get_current_value(CONF_SOLAR_PRODUCTION_SENSOR)): EntitySelector(
            EntitySelectorConfig(domain="sensor", device_class=SensorDeviceClass.POWER, multiple=False)
        ),
        vol.Optional(CONF_SOLAR_SCHEDULE_ENTITY, default=_get_current_value(CONF_SOLAR_SCHEDULE_ENTITY)): EntitySelector(
            EntitySelectorConfig(domain="schedule", multiple=False)
        ),
        vol.Optional(CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR, default=_get_current_value(CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR)): EntitySelector(
            EntitySelectorConfig(domain="sensor", multiple=False)
        ),
        vol.Optional(CONF_EV_POWER_SENSOR, default=_get_current_value(CONF_EV_POWER_SENSOR)): EntitySelector(
            EntitySelectorConfig(domain="sensor", device_class=SensorDeviceClass.POWER, multiple=False)
        ),
        vol.Optional(CONF_EV_SOC_SENSOR, default=_get_current_value(CONF_EV_SOC_SENSOR)): EntitySelector(
            EntitySelectorConfig(domain="sensor", device_class=SensorDeviceClass.BATTERY, multiple=False)
        ),
        vol.Optional(CONF_TARGET_SOC_LIMIT, default=_get_current_value(CONF_TARGET_SOC_LIMIT)): NumberSelector(
            NumberSelectorConfig(min=0, max=100, step=0.5, mode=NumberSelectorMode.BOX, unit_of_measurement="%")
        ),
        vol.Optional(CONF_SCAN_INTERVAL, default=_get_current_value(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_SECONDS)): NumberSelector(
            NumberSelectorConfig(min=10, max=3600, step=1, mode=NumberSelectorMode.BOX, unit_of_measurement="sekunder")
        ),
        vol.Optional(CONF_DEBUG_LOGGING, default=_get_current_value(CONF_DEBUG_LOGGING, False)): BooleanSelector(BooleanSelectorConfig()),
    }

    # För initial setup, se till att obligatoriska fält är verkligen Required utan fallback till default
    # om inte is_options_flow. Annars är alla Optional men förifyllda.
    if not is_options_flow:
        final_schema = {}
        for conf_key, selector_with_default in schema_fields.items():
            key_marker = conf_key # conf_key är redan ett vol.Marker objekt (Required/Optional)
            actual_conf_key_str = str(key_marker.schema) # Få ut CONF_SOMETHING strängen

            if actual_conf_key_str in REQUIRED_CONF_SETUP_KEYS:
                final_schema[vol.Required(actual_conf_key_str, default=selector_with_default.default)] = selector_with_default.container[actual_conf_key_str]
            else: # Valfria fält
                final_schema[key_marker] = selector_with_default.container[actual_conf_key_str]
        return vol.Schema(final_schema)

    return vol.Schema(schema_fields)


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
            options_to_save = {}
            validation_ok = True

            for conf_key in ALL_CONF_KEYS: # Iterera över CONF_ konstanter
                value = user_input.get(conf_key)

                if conf_key == CONF_DEBUG_LOGGING:
                    options_to_save[conf_key] = isinstance(value, bool) and value
                elif conf_key in OPTIONAL_ENTITY_CONF_KEYS:
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
                    current_scan_interval_from_data = self.config_entry.data.get(conf_key, DEFAULT_SCAN_INTERVAL_SECONDS)
                    if value is None or value == "" or str(value).strip() == "":
                         options_to_save[conf_key] = current_scan_interval_from_data
                    else:
                        try:
                            scan_val = int(value)
                            if not (10 <= scan_val <= 3600):
                                errors[conf_key] = "invalid_scan_interval"; validation_ok = False
                            else:
                                options_to_save[conf_key] = scan_val
                        except (ValueError, TypeError):
                            errors[conf_key] = "invalid_scan_interval"; validation_ok = False
                elif value is not None : # För obligatoriska fält som användaren kan ha ändrat
                    options_to_save[conf_key] = value
                elif conf_key in REQUIRED_CONF_SETUP_KEYS: # Om ett obligatoriskt fält (från setup) är None
                    options_to_save[conf_key] = current_settings.get(conf_key) # Behåll det gamla värdet
                # Valfria fält som är None (och inte hanterats ovan) kommer att sparas som None om de finns i user_input.
                # Om de inte finns i user_input alls, tas de inte med i options_to_save här,
                # vilket innebär att de tas bort från options om de fanns där tidigare (standard voluptuous beteende).

            if not validation_ok:
                return self.async_show_form(
                    step_id="init",
                    data_schema=_build_common_schema(current_settings, user_input, is_options_flow=True),
                    errors=errors,
                    description_placeholders={"help_url": self.hass.data[DOMAIN].get("HELP_URL", "")}
                )

            _LOGGER.debug("Sparar alternativ från OptionsFlow: %s", options_to_save)
            return self.async_create_entry(title="", data=options_to_save) # title="" är standard för options

        return self.async_show_form(
            step_id="init",
            data_schema=_build_common_schema(current_settings, None, is_options_flow=True),
            errors=errors,
            description_placeholders={"help_url": self.hass.data[DOMAIN].get("HELP_URL", "")}
        )


class SmartEVChargingConfigFlow(ConfigFlow, domain=DOMAIN):
    """Hanterar konfigurationsflödet för Smart EV Charging."""
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Hanterar användarsteget i konfigurationsflödet."""
        errors: Dict[str, str] = {}
        # Spara URL till hjälpfilen för enkel åtkomst i description_placeholders
        self.hass.data.setdefault(DOMAIN, {})
        self.hass.data[DOMAIN]["HELP_URL"] = "https://github.com/AlleHj/home-assistant-smart_ev_charging/blob/master/HELP.md"


        if user_input is not None:
            data_to_save = {}
            validation_ok = True

            for conf_key in ALL_CONF_KEYS: # Iterera över CONF_ konstanter
                value = user_input.get(conf_key) # user_input kommer ha CONF_ som nycklar

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
                elif value is not None: # För obligatoriska fält
                    data_to_save[conf_key] = value
                elif conf_key in REQUIRED_CONF_SETUP_KEYS:
                     # Detta bör fångas av vol.Required om fältet är tomt/None
                     errors[conf_key] = "required_field"; validation_ok = False
                else: # Valfria fält som är None
                    data_to_save[conf_key] = None


            if not validation_ok:
                 return self.async_show_form(
                     step_id="user",
                     data_schema=_build_common_schema({}, user_input, is_options_flow=False),
                     errors=errors,
                     description_placeholders={"help_url": self.hass.data[DOMAIN]["HELP_URL"]}
                 )

            _LOGGER.debug("Initial konfigurationsdata att spara: %s", data_to_save)
            await self.async_set_unique_id(f"{DOMAIN}_smart_charger_main_instance")
            self._abort_if_unique_id_configured()

            return self.async_create_entry(title=DEFAULT_NAME, data=data_to_save)

        return self.async_show_form(
            step_id="user",
            data_schema=_build_common_schema({}, None, is_options_flow=False), # Tom dict för current_settings vid ny setup
            errors=errors,
            description_placeholders={"help_url": self.hass.data[DOMAIN]["HELP_URL"]}
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> SmartEVChargingOptionsFlowHandler:
        """Hämtar alternativflödeshanteraren."""
        return SmartEVChargingOptionsFlowHandler(config_entry)