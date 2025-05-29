# File version: 2025-05-29 0.1.28
"""Config flow for Smart EV Charging integration."""
import logging
from typing import Any
from collections import OrderedDict

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
import homeassistant.helpers.config_validation as cv

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
    CONF_DEBUG_LOGGING, # Säkerställ att denna är med från nyare versioner
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL_SECONDS,
)

_LOGGER = logging.getLogger(__name__)

# Baserat på konstanterna från den NYARE versionen av const.py
ALL_CONF_KEYS = [
    CONF_CHARGER_DEVICE, CONF_STATUS_SENSOR, CONF_CHARGER_ENABLED_SWITCH_ID,
    CONF_PRICE_SENSOR, CONF_SURCHARGE_HELPER, CONF_TIME_SCHEDULE_ENTITY,
    CONF_HOUSE_POWER_SENSOR, CONF_SOLAR_PRODUCTION_SENSOR,
    CONF_SOLAR_SCHEDULE_ENTITY, CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR,
    CONF_EV_POWER_SENSOR, CONF_SCAN_INTERVAL,
    CONF_EV_SOC_SENSOR, CONF_TARGET_SOC_LIMIT, CONF_DEBUG_LOGGING
]

OPTIONAL_ENTITY_CONF_KEYS = [
    CONF_SURCHARGE_HELPER, CONF_TIME_SCHEDULE_ENTITY,
    CONF_HOUSE_POWER_SENSOR, CONF_SOLAR_PRODUCTION_SENSOR,
    CONF_SOLAR_SCHEDULE_ENTITY, CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR,
    CONF_EV_POWER_SENSOR, CONF_EV_SOC_SENSOR
]
# Fält som kan vara None och vars selektorer behöver kapslas i vol.Maybe
MAYBE_SELECTOR_CONF_KEYS = OPTIONAL_ENTITY_CONF_KEYS + [CONF_TARGET_SOC_LIMIT]

REQUIRED_CONF_SETUP_KEYS = [
    CONF_CHARGER_DEVICE, CONF_STATUS_SENSOR, CONF_CHARGER_ENABLED_SWITCH_ID, CONF_PRICE_SENSOR
]

HELP_URL_GLOBAL = "https://github.com/AlleHj/home-assistant-smart_ev_charging/blob/master/HELP.md"


def _build_common_schema(
    current_settings: dict[str, Any],
    user_input_for_repopulating: dict | None = None,
    is_options_flow: bool = False
) -> vol.Schema:
    """Bygger upp ett gemensamt Voluptuous-schema."""

    def _get_current_or_repop_value(conf_key: str, default_val: Any = None) -> Any:
        # Används för att sätta initiala värden i formulärfälten (suggested_value eller default).
        if user_input_for_repopulating is not None and conf_key in user_input_for_repopulating:
            return user_input_for_repopulating[conf_key]
        return current_settings.get(conf_key, default_val)

    # Definiera alla fält och deras selektorer först
    # Paret är (värde_för_suggested_value_eller_default, selector_instance)
    defined_fields_with_selectors = OrderedDict()
    defined_fields_with_selectors[CONF_CHARGER_DEVICE] = (_get_current_or_repop_value(CONF_CHARGER_DEVICE), DeviceSelector(DeviceSelectorConfig(integration="easee")))
    defined_fields_with_selectors[CONF_STATUS_SENSOR] = (_get_current_or_repop_value(CONF_STATUS_SENSOR), EntitySelector(EntitySelectorConfig(domain="sensor", multiple=False)))
    defined_fields_with_selectors[CONF_CHARGER_ENABLED_SWITCH_ID] = (_get_current_or_repop_value(CONF_CHARGER_ENABLED_SWITCH_ID), EntitySelector(EntitySelectorConfig(domain="switch", multiple=False)))
    defined_fields_with_selectors[CONF_PRICE_SENSOR] = (_get_current_or_repop_value(CONF_PRICE_SENSOR), EntitySelector(EntitySelectorConfig(domain="sensor", multiple=False)))
    defined_fields_with_selectors[CONF_SURCHARGE_HELPER] = (_get_current_or_repop_value(CONF_SURCHARGE_HELPER), EntitySelector(EntitySelectorConfig(domain=["sensor", "input_number"], multiple=False)))
    defined_fields_with_selectors[CONF_TIME_SCHEDULE_ENTITY] = (_get_current_or_repop_value(CONF_TIME_SCHEDULE_ENTITY), EntitySelector(EntitySelectorConfig(domain="schedule", multiple=False)))
    defined_fields_with_selectors[CONF_HOUSE_POWER_SENSOR] = (_get_current_or_repop_value(CONF_HOUSE_POWER_SENSOR), EntitySelector(EntitySelectorConfig(domain="sensor", device_class=SensorDeviceClass.POWER, multiple=False)))
    defined_fields_with_selectors[CONF_SOLAR_PRODUCTION_SENSOR] = (_get_current_or_repop_value(CONF_SOLAR_PRODUCTION_SENSOR), EntitySelector(EntitySelectorConfig(domain="sensor", device_class=SensorDeviceClass.POWER, multiple=False)))
    defined_fields_with_selectors[CONF_SOLAR_SCHEDULE_ENTITY] = (_get_current_or_repop_value(CONF_SOLAR_SCHEDULE_ENTITY), EntitySelector(EntitySelectorConfig(domain="schedule", multiple=False)))
    defined_fields_with_selectors[CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR] = (_get_current_or_repop_value(CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR), EntitySelector(EntitySelectorConfig(domain="sensor", multiple=False)))
    defined_fields_with_selectors[CONF_EV_POWER_SENSOR] = (_get_current_or_repop_value(CONF_EV_POWER_SENSOR), EntitySelector(EntitySelectorConfig(domain="sensor", device_class=SensorDeviceClass.POWER, multiple=False)))
    defined_fields_with_selectors[CONF_EV_SOC_SENSOR] = (_get_current_or_repop_value(CONF_EV_SOC_SENSOR), EntitySelector(EntitySelectorConfig(domain="sensor", device_class=SensorDeviceClass.BATTERY, multiple=False)))
    defined_fields_with_selectors[CONF_TARGET_SOC_LIMIT] = (_get_current_or_repop_value(CONF_TARGET_SOC_LIMIT), NumberSelector(NumberSelectorConfig(min=0, max=100, step=0.5, mode=NumberSelectorMode.BOX, unit_of_measurement="%")))
    defined_fields_with_selectors[CONF_SCAN_INTERVAL] = (_get_current_or_repop_value(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_SECONDS), NumberSelector(NumberSelectorConfig(min=10, max=3600, step=1, mode=NumberSelectorMode.BOX, unit_of_measurement="sekunder")))
    defined_fields_with_selectors[CONF_DEBUG_LOGGING] = (_get_current_or_repop_value(CONF_DEBUG_LOGGING, False), BooleanSelector(BooleanSelectorConfig()))

    final_schema_dict = OrderedDict()
    is_initial_setup_display = not is_options_flow and user_input_for_repopulating is None

    for conf_key, (val_for_ui_default, selector_instance_orig) in defined_fields_with_selectors.items():
        selector_instance_final = selector_instance_orig

        if is_options_flow:
            # För Options Flow, efterlikna gamla koden: använd description/suggested_value för UI-hint.
            # Kapsla med vol.Maybe för fält som kan vara None.
            ui_suggestion = val_for_ui_default if val_for_ui_default is not None else ""
            if conf_key in MAYBE_SELECTOR_CONF_KEYS:
                selector_instance_final = vol.Maybe(selector_instance_orig)
                # Om värdet är None, är suggested_value "" för entity selectors, annars None för NumberSelector
                ui_suggestion = "" if conf_key in OPTIONAL_ENTITY_CONF_KEYS and val_for_ui_default is None else val_for_ui_default

            # Använd inte default= i vol.Optional om möjligt för att efterlikna gamla koden, förlita på suggested_value.
            # Om fältet är av en typ som behöver ett default för att inte krascha om det saknas helt (t.ex. boolean), sätt det.
            if conf_key == CONF_DEBUG_LOGGING:
                 final_schema_dict[vol.Optional(conf_key, default=bool(val_for_ui_default))] = selector_instance_final
            elif conf_key == CONF_SCAN_INTERVAL:
                 final_schema_dict[vol.Optional(conf_key, default=int(val_for_ui_default or DEFAULT_SCAN_INTERVAL_SECONDS))] = selector_instance_final
            else:
                final_schema_dict[vol.Optional(conf_key, description={"suggested_value": ui_suggestion})] = selector_instance_final

        else: # Initial Setup Flow
            if is_initial_setup_display:
                if conf_key in REQUIRED_CONF_SETUP_KEYS:
                    final_schema_dict[vol.Required(conf_key, default=vol.UNDEFINED)] = selector_instance_orig
                elif conf_key in MAYBE_SELECTOR_CONF_KEYS: # Inkluderar OPTIONAL_ENTITY_CONF_KEYS & TARGET_SOC_LIMIT
                    final_schema_dict[vol.Optional(conf_key, default=None)] = vol.Maybe(selector_instance_orig)
                elif conf_key == CONF_SCAN_INTERVAL:
                    final_schema_dict[vol.Optional(conf_key, default=DEFAULT_SCAN_INTERVAL_SECONDS)] = selector_instance_orig
                elif conf_key == CONF_DEBUG_LOGGING:
                    final_schema_dict[vol.Optional(conf_key, default=False)] = selector_instance_orig
                else: # Fallback för andra valfria som inte är Maybe (finns inga just nu)
                    final_schema_dict[vol.Optional(conf_key, default=val_for_ui_default)] = selector_instance_orig
            else: # Repopulerar setup-formulär efter fel - använd val_for_ui_default som innehåller användarens tidigare försök
                current_selector_repop = selector_instance_orig
                if conf_key in MAYBE_SELECTOR_CONF_KEYS:
                     current_selector_repop = vol.Maybe(selector_instance_orig)
                if conf_key in REQUIRED_CONF_SETUP_KEYS:
                    final_schema_dict[vol.Required(conf_key, default=val_for_ui_default)] = current_selector_repop
                else:
                    final_schema_dict[vol.Optional(conf_key, default=val_for_ui_default)] = current_selector_repop

    return vol.Schema(final_schema_dict)


class SmartEVChargingOptionsFlowHandler(OptionsFlow):
    """Hanterar alternativflödet för Smart EV Charging."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initierar alternativflödet."""
        # self.config_entry tillhandahålls av OptionsFlow basklassen.
        pass

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Hanterar alternativen."""
        errors: dict[str, str] = {}
        current_settings = {**self.config_entry.data, **self.config_entry.options}

        if user_input is not None:
            _LOGGER.debug("OptionsFlow: Mottaget user_input (för felsökning av sparproblem): %s", user_input)

            options_to_save = {}
            validation_ok = True

            # Denna sparlogik är densamma som tidigare och bör fungera om user_input är korrekt
            # (dvs. "" eller None för rensade valfria entitetsfält).
            for conf_key in ALL_CONF_KEYS: # Använd ALL_CONF_KEYS från denna fil
                value_from_form = user_input.get(conf_key)

                if conf_key == CONF_DEBUG_LOGGING:
                    options_to_save[conf_key] = isinstance(value_from_form, bool) and value_from_form

                elif conf_key in OPTIONAL_ENTITY_CONF_KEYS:
                    options_to_save[conf_key] = None if value_from_form == "" or value_from_form is None else value_from_form

                elif conf_key == CONF_TARGET_SOC_LIMIT:
                    if value_from_form is None or value_from_form == "" or str(value_from_form).strip() == "":
                        options_to_save[conf_key] = None
                    else:
                        try:
                            soc_val = float(value_from_form)
                            if not (0 <= soc_val <= 100):
                                errors[conf_key] = "invalid_target_soc"; validation_ok = False
                            else:
                                options_to_save[conf_key] = soc_val
                        except (ValueError, TypeError):
                            errors[conf_key] = "invalid_target_soc"; validation_ok = False

                elif conf_key == CONF_SCAN_INTERVAL:
                    if value_from_form is None or value_from_form == "" or str(value_from_form).strip() == "":
                        options_to_save[conf_key] = DEFAULT_SCAN_INTERVAL_SECONDS
                    else:
                        try:
                            scan_val = int(value_from_form)
                            if not (10 <= scan_val <= 3600):
                                errors[conf_key] = "invalid_scan_interval"; validation_ok = False
                            else:
                                options_to_save[conf_key] = scan_val
                        except (ValueError, TypeError):
                            errors[conf_key] = "invalid_scan_interval"; validation_ok = False

                elif value_from_form is not None: # För alla andra (typiskt obligatoriska fält från setup)
                    options_to_save[conf_key] = value_from_form

                # Om value_from_form är None för ett fält som inte är specialhanterat ovan:
                elif conf_key in REQUIRED_CONF_SETUP_KEYS:
                    # Behåll existerande värde från config_entry (data eller options)
                    # Detta är en fallback om ett "obligatoriskt" fält inte skulle skickas med från formuläret.
                    options_to_save[conf_key] = current_settings.get(conf_key)

                else: # Andra valfria fält där value_from_form är None och som inte specialhanterats
                    options_to_save[conf_key] = None


            if not validation_ok:
                return self.async_show_form(
                    step_id="init",
                    data_schema=_build_common_schema(current_settings, user_input, is_options_flow=True),
                    errors=errors,
                    description_placeholders={"help_url": HELP_URL_GLOBAL}
                )

            _LOGGER.debug("OptionsFlow: Sparar options: %s", options_to_save)
            return self.async_create_entry(title="", data=options_to_save)

        return self.async_show_form(
            step_id="init",
            data_schema=_build_common_schema(current_settings, None, is_options_flow=True),
            errors=errors,
            description_placeholders={"help_url": HELP_URL_GLOBAL}
        )


class SmartEVChargingConfigFlow(ConfigFlow, domain=DOMAIN):
    """Hanterar konfigurationsflödet för Smart EV Charging."""
    VERSION = 1

    async def is_matching(self, import_info: dict[str, Any]) -> bool:
        """Avgör om en upptäckt enhet matchar detta flöde.

        Denna integration förlitar sig inte på discovery, så metoden returnerar False.
        Detta är för att tillfredsställa kravet på att abstrakta metoder implementeras.
        """
        return False

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Hanterar det initiala användarsteget för konfigurationen."""
        errors: dict[str, str] = {}

        if user_input is not None:
            _LOGGER.debug("ConfigFlow User Step: Mottaget user_input: %s", user_input)
            data_to_save = {}
            validation_ok = True

            for conf_key in ALL_CONF_KEYS: # Använd ALL_CONF_KEYS från denna fil
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