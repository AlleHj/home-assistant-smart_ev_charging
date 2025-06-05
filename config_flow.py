# File version: 2025-06-05 0.2.0 // ÄNDRA HÄR
"""Config flow for Smart EV Charging integration."""

import voluptuous as vol
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
    CONF_TIME_SCHEDULE_ENTITY,
    CONF_HOUSE_POWER_SENSOR,
    CONF_SOLAR_PRODUCTION_SENSOR,
    CONF_SOLAR_SCHEDULE_ENTITY,
    CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR,
    CONF_CHARGER_DYNAMIC_CURRENT_SENSOR,
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
    CONF_CHARGER_DEVICE,
    CONF_STATUS_SENSOR,
    CONF_CHARGER_ENABLED_SWITCH_ID,
    CONF_PRICE_SENSOR,
    CONF_TIME_SCHEDULE_ENTITY,
    CONF_HOUSE_POWER_SENSOR,
    CONF_SOLAR_PRODUCTION_SENSOR,
    CONF_SOLAR_SCHEDULE_ENTITY,
    CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR,
    CONF_CHARGER_DYNAMIC_CURRENT_SENSOR,
    CONF_SCAN_INTERVAL,
    CONF_EV_SOC_SENSOR,
    CONF_TARGET_SOC_LIMIT,
    CONF_DEBUG_LOGGING,
]

OPTIONAL_ENTITY_CONF_KEYS = [
    CONF_TIME_SCHEDULE_ENTITY,
    CONF_HOUSE_POWER_SENSOR,
    CONF_SOLAR_PRODUCTION_SENSOR,
    CONF_SOLAR_SCHEDULE_ENTITY,
    CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR,
    CONF_CHARGER_DYNAMIC_CURRENT_SENSOR,
    CONF_EV_SOC_SENSOR,
]
MAYBE_SELECTOR_CONF_KEYS = OPTIONAL_ENTITY_CONF_KEYS + [CONF_TARGET_SOC_LIMIT]

REQUIRED_CONF_SETUP_KEYS = [
    CONF_CHARGER_DEVICE,
    CONF_STATUS_SENSOR,
    CONF_CHARGER_ENABLED_SWITCH_ID,
    CONF_PRICE_SENSOR,
]

HELP_URL_GLOBAL = (
    "https://github.com/AlleHj/home-assistant-smart_ev_charging/blob/master/HELP.md"
)


def coerce_empty_string_to_none(value):
    """Convert an empty string to None, pass other values through."""
    if value == "":
        return None
    return value


def _build_common_schema(
    current_settings: dict[str, Any],
    user_input_for_repopulating: dict | None = None,
    is_options_flow: bool = False,
) -> vol.Schema:
    """Bygger upp ett gemensamt Voluptuous-schema."""

    def _get_current_or_repop_value(conf_key: str, default_val: Any = None) -> Any:
        if (
            user_input_for_repopulating is not None
            and conf_key in user_input_for_repopulating
        ):
            return user_input_for_repopulating[conf_key]
        return current_settings.get(conf_key, default_val)

    defined_fields_with_selectors = OrderedDict()
    defined_fields_with_selectors[CONF_CHARGER_DEVICE] = (
        _get_current_or_repop_value(CONF_CHARGER_DEVICE),
        DeviceSelector(DeviceSelectorConfig(integration="easee")),
    )
    defined_fields_with_selectors[CONF_STATUS_SENSOR] = (
        _get_current_or_repop_value(CONF_STATUS_SENSOR),
        EntitySelector(EntitySelectorConfig(domain="sensor", multiple=False)),
    )
    defined_fields_with_selectors[CONF_CHARGER_ENABLED_SWITCH_ID] = (
        _get_current_or_repop_value(CONF_CHARGER_ENABLED_SWITCH_ID),
        EntitySelector(EntitySelectorConfig(domain="switch", multiple=False)),
    )
    defined_fields_with_selectors[CONF_PRICE_SENSOR] = (
        _get_current_or_repop_value(CONF_PRICE_SENSOR),
        EntitySelector(EntitySelectorConfig(domain="sensor", multiple=False)),
    )
    defined_fields_with_selectors[CONF_TIME_SCHEDULE_ENTITY] = (
        _get_current_or_repop_value(CONF_TIME_SCHEDULE_ENTITY),
        EntitySelector(EntitySelectorConfig(domain="schedule", multiple=False)),
    )
    defined_fields_with_selectors[CONF_HOUSE_POWER_SENSOR] = (
        _get_current_or_repop_value(CONF_HOUSE_POWER_SENSOR),
        EntitySelector(
            EntitySelectorConfig(
                domain="sensor", device_class=SensorDeviceClass.POWER, multiple=False
            )
        ),
    )
    defined_fields_with_selectors[CONF_SOLAR_PRODUCTION_SENSOR] = (
        _get_current_or_repop_value(CONF_SOLAR_PRODUCTION_SENSOR),
        EntitySelector(
            EntitySelectorConfig(
                domain="sensor", device_class=SensorDeviceClass.POWER, multiple=False
            )
        ),
    )
    defined_fields_with_selectors[CONF_SOLAR_SCHEDULE_ENTITY] = (
        _get_current_or_repop_value(CONF_SOLAR_SCHEDULE_ENTITY),
        EntitySelector(EntitySelectorConfig(domain="schedule", multiple=False)),
    )
    defined_fields_with_selectors[CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR] = (
        _get_current_or_repop_value(CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR),
        EntitySelector(EntitySelectorConfig(domain="sensor", multiple=False)),
    )
    defined_fields_with_selectors[CONF_CHARGER_DYNAMIC_CURRENT_SENSOR] = (
        _get_current_or_repop_value(CONF_CHARGER_DYNAMIC_CURRENT_SENSOR),
        EntitySelector(EntitySelectorConfig(domain="sensor", multiple=False)),
    )
    defined_fields_with_selectors[CONF_EV_SOC_SENSOR] = (
        _get_current_or_repop_value(CONF_EV_SOC_SENSOR),
        EntitySelector(
            EntitySelectorConfig(
                domain="sensor", device_class=SensorDeviceClass.BATTERY, multiple=False
            )
        ),
    )
    defined_fields_with_selectors[CONF_TARGET_SOC_LIMIT] = (
        _get_current_or_repop_value(CONF_TARGET_SOC_LIMIT),
        NumberSelector(
            NumberSelectorConfig(
                min=0,
                max=100,
                step=0.5,
                mode=NumberSelectorMode.BOX,
                unit_of_measurement="%",
            )
        ),
    )
    defined_fields_with_selectors[CONF_SCAN_INTERVAL] = (
        _get_current_or_repop_value(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_SECONDS),
        NumberSelector(
            NumberSelectorConfig(
                min=10,
                max=3600,
                step=1,
                mode=NumberSelectorMode.BOX,
                unit_of_measurement="sekunder",
            )
        ),
    )
    defined_fields_with_selectors[CONF_DEBUG_LOGGING] = (
        _get_current_or_repop_value(CONF_DEBUG_LOGGING, False),
        BooleanSelector(BooleanSelectorConfig()),
    )

    final_schema_dict = OrderedDict()
    is_initial_setup_display = (
        not is_options_flow and user_input_for_repopulating is None
    )

    for conf_key, (
        val_for_ui_default,
        selector_instance_orig,
    ) in defined_fields_with_selectors.items():
        selector_instance_final = selector_instance_orig

        if is_options_flow:
            ui_suggestion = val_for_ui_default if val_for_ui_default is not None else ""
            if conf_key in MAYBE_SELECTOR_CONF_KEYS:
                selector_instance_final = vol.Maybe(selector_instance_orig)
                ui_suggestion = (
                    ""
                    if conf_key in OPTIONAL_ENTITY_CONF_KEYS
                    and val_for_ui_default is None
                    else val_for_ui_default
                )

            if conf_key == CONF_DEBUG_LOGGING:
                final_schema_dict[
                    vol.Optional(conf_key, default=bool(val_for_ui_default))
                ] = selector_instance_final
            elif conf_key == CONF_SCAN_INTERVAL:
                final_schema_dict[
                    vol.Optional(
                        conf_key,
                        default=int(
                            val_for_ui_default or DEFAULT_SCAN_INTERVAL_SECONDS
                        ),
                    )
                ] = selector_instance_final
            else:
                final_schema_dict[
                    vol.Optional(
                        conf_key, description={"suggested_value": ui_suggestion}
                    )
                ] = selector_instance_final

        else:
            if is_initial_setup_display:
                if conf_key in REQUIRED_CONF_SETUP_KEYS:
                    final_schema_dict[vol.Required(conf_key, default=vol.UNDEFINED)] = (
                        selector_instance_orig
                    )
                elif conf_key in MAYBE_SELECTOR_CONF_KEYS:
                    final_schema_dict[vol.Optional(conf_key, default=None)] = vol.Maybe(
                        selector_instance_orig
                    )
                elif conf_key == CONF_SCAN_INTERVAL:
                    final_schema_dict[
                        vol.Optional(conf_key, default=DEFAULT_SCAN_INTERVAL_SECONDS)
                    ] = selector_instance_orig
                elif conf_key == CONF_DEBUG_LOGGING:
                    final_schema_dict[vol.Optional(conf_key, default=False)] = (
                        selector_instance_orig
                    )
                else:
                    final_schema_dict[
                        vol.Optional(conf_key, default=val_for_ui_default)
                    ] = selector_instance_orig
            else:
                current_selector_repop = selector_instance_orig
                if conf_key in MAYBE_SELECTOR_CONF_KEYS:
                    current_selector_repop = vol.Maybe(selector_instance_orig)
                if conf_key in REQUIRED_CONF_SETUP_KEYS:
                    final_schema_dict[
                        vol.Required(conf_key, default=val_for_ui_default)
                    ] = current_selector_repop
                else:
                    final_schema_dict[
                        vol.Optional(conf_key, default=val_for_ui_default)
                    ] = current_selector_repop

    return vol.Schema(final_schema_dict)


class SmartEVChargingOptionsFlowHandler(OptionsFlow):
    """Hanterar alternativflödet för Smart EV Charging."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initierar alternativflödet."""
        pass

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Hanterar alternativen."""
        errors: dict[str, str] = {}
        current_settings = {**self.config_entry.data, **self.config_entry.options}

        if user_input is not None:
            _LOGGER.debug("OptionsFlow: Mottaget user_input: %s", user_input)
            options_to_save = {}
            validation_ok = True

            for conf_key in ALL_CONF_KEYS:
                value_from_form = user_input.get(conf_key)

                if conf_key == CONF_DEBUG_LOGGING:
                    options_to_save[conf_key] = (
                        isinstance(value_from_form, bool) and value_from_form
                    )
                elif conf_key in OPTIONAL_ENTITY_CONF_KEYS:
                    options_to_save[conf_key] = (
                        None
                        if value_from_form == "" or value_from_form is None
                        else value_from_form
                    )
                elif conf_key == CONF_TARGET_SOC_LIMIT:
                    if (
                        value_from_form is None
                        or value_from_form == ""
                        or str(value_from_form).strip() == ""
                    ):
                        options_to_save[conf_key] = None
                    else:
                        try:
                            soc_val = float(value_from_form)
                            if not (0 <= soc_val <= 100):
                                errors[conf_key] = "invalid_target_soc"
                                validation_ok = False
                            else:
                                options_to_save[conf_key] = soc_val
                        except (ValueError, TypeError):
                            errors[conf_key] = "invalid_target_soc"
                            validation_ok = False
                elif conf_key == CONF_SCAN_INTERVAL:
                    if (
                        value_from_form is None
                        or value_from_form == ""
                        or str(value_from_form).strip() == ""
                    ):
                        options_to_save[conf_key] = DEFAULT_SCAN_INTERVAL_SECONDS
                    else:
                        try:
                            scan_val = int(value_from_form)
                            if not (10 <= scan_val <= 3600):
                                errors[conf_key] = "invalid_scan_interval"
                                validation_ok = False
                            else:
                                options_to_save[conf_key] = scan_val
                        except (ValueError, TypeError):
                            errors[conf_key] = "invalid_scan_interval"
                            validation_ok = False
                elif value_from_form is not None:
                    options_to_save[conf_key] = value_from_form
                elif conf_key in REQUIRED_CONF_SETUP_KEYS:
                    options_to_save[conf_key] = current_settings.get(conf_key)
                else:
                    options_to_save[conf_key] = None

            if not validation_ok:
                return self.async_show_form(
                    step_id="init",
                    data_schema=_build_common_schema(
                        current_settings, user_input, is_options_flow=True
                    ),
                    errors=errors,
                    description_placeholders={"help_url": HELP_URL_GLOBAL},
                )
            _LOGGER.debug("OptionsFlow: Sparar options: %s", options_to_save)
            return self.async_create_entry(title="", data=options_to_save)

        return self.async_show_form(
            step_id="init",
            data_schema=_build_common_schema(
                current_settings, None, is_options_flow=True
            ),
            errors=errors,
            description_placeholders={"help_url": HELP_URL_GLOBAL},
        )


class SmartEVChargingConfigFlow(ConfigFlow, domain=DOMAIN):
    """Hanterar konfigurationsflödet för Smart EV Charging."""

    VERSION = 1

    async def is_matching(self, import_info: dict[str, Any]) -> bool:
        """Avgör om en upptäckt enhet matchar detta flöde."""
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

            for conf_key in ALL_CONF_KEYS:
                value = user_input.get(conf_key)

                if conf_key == CONF_DEBUG_LOGGING:
                    data_to_save[conf_key] = isinstance(value, bool) and value
                elif conf_key in OPTIONAL_ENTITY_CONF_KEYS:
                    data_to_save[conf_key] = (
                        None if value == "" or value is None else value
                    )
                elif conf_key == CONF_TARGET_SOC_LIMIT:
                    if value is None or value == "" or str(value).strip() == "":
                        data_to_save[conf_key] = None
                    else:
                        try:
                            soc_val = float(value)
                            if not (0 <= soc_val <= 100):
                                errors[conf_key] = "invalid_target_soc"
                                validation_ok = False
                            else:
                                data_to_save[conf_key] = soc_val
                        except (ValueError, TypeError):
                            errors[conf_key] = "invalid_target_soc"
                            validation_ok = False
                elif conf_key == CONF_SCAN_INTERVAL:
                    if value is None or value == "" or str(value).strip() == "":
                        data_to_save[conf_key] = DEFAULT_SCAN_INTERVAL_SECONDS
                    else:
                        try:
                            scan_val = int(value)
                            if not (10 <= scan_val <= 3600):
                                errors[conf_key] = "invalid_scan_interval"
                                validation_ok = False
                            else:
                                data_to_save[conf_key] = scan_val
                        except (ValueError, TypeError):
                            errors[conf_key] = "invalid_scan_interval"
                            validation_ok = False
                elif value is not None:
                    data_to_save[conf_key] = value
                elif conf_key in REQUIRED_CONF_SETUP_KEYS:
                    errors[conf_key] = "required_field"
                    validation_ok = False
                else:
                    data_to_save[conf_key] = None

            if not validation_ok:
                return self.async_show_form(
                    step_id="user",
                    data_schema=_build_common_schema(
                        {}, user_input, is_options_flow=False
                    ),
                    errors=errors,
                    description_placeholders={"help_url": HELP_URL_GLOBAL},
                )

            _LOGGER.debug("Initial konfigurationsdata att spara: %s", data_to_save)
            await self.async_set_unique_id(f"{DOMAIN}_smart_charger_main_instance")
            self._abort_if_unique_id_configured()

            return self.async_create_entry(title=DEFAULT_NAME, data=data_to_save)

        return self.async_show_form(
            step_id="user",
            data_schema=_build_common_schema({}, None, is_options_flow=False),
            errors=errors,
            description_placeholders={"help_url": HELP_URL_GLOBAL},
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> SmartEVChargingOptionsFlowHandler:
        return SmartEVChargingOptionsFlowHandler(config_entry)
