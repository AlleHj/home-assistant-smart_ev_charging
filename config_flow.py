# File version: 2025-05-21.6
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
    CONF_EV_SOC_SENSOR, CONF_TARGET_SOC_LIMIT
]
OPTIONAL_ENTITY_SELECTOR_KEYS = [ 
    CONF_TIME_SCHEDULE_ENTITY, CONF_SOLAR_SCHEDULE_ENTITY, CONF_SURCHARGE_HELPER,
    CONF_HOUSE_POWER_SENSOR, CONF_SOLAR_PRODUCTION_SENSOR,
    CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR, CONF_EV_POWER_SENSOR,
    CONF_EV_SOC_SENSOR
]

class SmartEVChargingOptionsFlowHandler(OptionsFlow):
    """Handle an options flow for Smart EV Charging."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            options_to_save = {}
            
            for key in ALL_SCHEMA_KEYS:
                value = user_input.get(key) # Hämta värdet från formuläret

                if key in OPTIONAL_ENTITY_SELECTOR_KEYS:
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
                    if value is None or value == "":
                        # Om tomt i options, använd det som finns i config_entry.data (initialt värde)
                        # eller default om det inte ens finns där.
                        options_to_save[key] = self.config_entry.data.get(key, DEFAULT_SCAN_INTERVAL_SECONDS)
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
                    # Om ett obligatoriskt fält har blivit None (bör inte hända via UI om Required)
                    # eller ett valfritt fält som inte hanteras ovan.
                    # Försök behålla befintligt värde från data om inget annat angetts.
                    options_to_save[key] = self.config_entry.data.get(key)


            if errors:
                return self.async_show_form(
                    step_id="init", data_schema=self._build_options_schema(user_input), errors=errors
                )

            _LOGGER.debug("Sparar alternativ från OptionsFlow: %s", options_to_save)
            # Detta uppdaterar config_entry.options
            return self.async_create_entry(title="", data=options_to_save)

        return self.async_show_form(
            step_id="init", data_schema=self._build_options_schema(), errors=errors
        )

    def _build_options_schema(self, current_values_for_repopulating_form: dict | None = None) -> vol.Schema:
        
        def _get_form_value(key: str, is_optional_entity_selector: bool = False, default_val: Any = None) -> Any:
            if current_values_for_repopulating_form is not None and key in current_values_for_repopulating_form:
                val_from_form = current_values_for_repopulating_form[key]
                if is_optional_entity_selector and val_from_form == "": return None
                if isinstance(val_from_form, str) and key in [CONF_SCAN_INTERVAL, CONF_TARGET_SOC_LIMIT]: return val_from_form 
                return val_from_form
            
            # Använd options om det finns, annars data, annars default_val
            return self.config_entry.options.get(key, self.config_entry.data.get(key, default_val))

        return vol.Schema({
            vol.Required(CONF_CHARGER_DEVICE, default=_get_form_value(CONF_CHARGER_DEVICE)): DeviceSelector(DeviceSelectorConfig(integration="easee")),
            vol.Required(CONF_STATUS_SENSOR, default=_get_form_value(CONF_STATUS_SENSOR)): EntitySelector(EntitySelectorConfig(domain="sensor")),
            vol.Required(CONF_CHARGER_ENABLED_SWITCH_ID, default=_get_form_value(CONF_CHARGER_ENABLED_SWITCH_ID)): EntitySelector(EntitySelectorConfig(domain="switch")),
            vol.Required(CONF_PRICE_SENSOR, default=_get_form_value(CONF_PRICE_SENSOR)): EntitySelector(EntitySelectorConfig(domain="sensor")),
            vol.Optional(CONF_SURCHARGE_HELPER, description={"suggested_value": _get_form_value(CONF_SURCHARGE_HELPER, True)}): EntitySelector(EntitySelectorConfig(domain=["sensor", "input_number"])),
            vol.Optional(CONF_TIME_SCHEDULE_ENTITY, description={"suggested_value": _get_form_value(CONF_TIME_SCHEDULE_ENTITY, True)}): EntitySelector(EntitySelectorConfig(domain="schedule")),
            vol.Optional(CONF_HOUSE_POWER_SENSOR, description={"suggested_value": _get_form_value(CONF_HOUSE_POWER_SENSOR, True)}): EntitySelector(EntitySelectorConfig(domain="sensor", device_class=SensorDeviceClass.POWER)),
            vol.Optional(CONF_SOLAR_PRODUCTION_SENSOR, description={"suggested_value": _get_form_value(CONF_SOLAR_PRODUCTION_SENSOR, True)}): EntitySelector(EntitySelectorConfig(domain="sensor", device_class=SensorDeviceClass.POWER)),
            vol.Optional(CONF_SOLAR_SCHEDULE_ENTITY, description={"suggested_value": _get_form_value(CONF_SOLAR_SCHEDULE_ENTITY, True)}): EntitySelector(EntitySelectorConfig(domain="schedule")),
            vol.Optional(CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR, description={"suggested_value": _get_form_value(CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR, True)}): EntitySelector(EntitySelectorConfig(domain="sensor")),
            vol.Optional(CONF_EV_POWER_SENSOR, description={"suggested_value": _get_form_value(CONF_EV_POWER_SENSOR, True)}): EntitySelector(EntitySelectorConfig(domain="sensor", device_class=SensorDeviceClass.POWER)),
            vol.Optional(CONF_EV_SOC_SENSOR, description={"suggested_value": _get_form_value(CONF_EV_SOC_SENSOR, True)}): EntitySelector(EntitySelectorConfig(domain="sensor", device_class=SensorDeviceClass.BATTERY)),
            vol.Optional(CONF_TARGET_SOC_LIMIT, description={"suggested_value": _get_form_value(CONF_TARGET_SOC_LIMIT, False, None)}): NumberSelector(NumberSelectorConfig(min=0, max=100, step=0.5, mode=NumberSelectorMode.BOX, unit_of_measurement="%")),
            vol.Optional(CONF_SCAN_INTERVAL, default=_get_form_value(CONF_SCAN_INTERVAL, False, DEFAULT_SCAN_INTERVAL_SECONDS)): NumberSelector(NumberSelectorConfig(min=10, max=3600, step=1, mode=NumberSelectorMode.BOX, unit_of_measurement="sekunder")),
        })


class SmartEVChargingConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> SmartEVChargingOptionsFlowHandler:
        return SmartEVChargingOptionsFlowHandler(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: Dict[str, str] = {}
        if user_input is not None:
            data_to_save = {}
            schema = self._build_user_schema(user_input) 
            
            for key_marker in schema.schema:
                key = str(key_marker.schema) # Hämta den faktiska nyckelsträngen
                value = user_input.get(key)

                if key in OPTIONAL_ENTITY_SELECTOR_KEYS:
                    data_to_save[key] = None if value == "" or value is None else value
                elif key == CONF_TARGET_SOC_LIMIT:
                    if value is None or value == "": data_to_save[key] = None
                    else:
                        try: data_to_save[key] = float(value)
                        except ValueError: errors[key] = "invalid_target_soc"
                elif key == CONF_SCAN_INTERVAL:
                    if value is None or value == "": data_to_save[key] = DEFAULT_SCAN_INTERVAL_SECONDS
                    else:
                        try:
                            val_int = int(value)
                            if not (10 <= val_int <= 3600): errors[key] = "invalid_scan_interval"
                            else: data_to_save[key] = val_int
                        except ValueError: errors[key] = "invalid_scan_interval"
                elif value is not None: 
                    data_to_save[key] = value
                else: # För Required fält som inte har angetts (bör fångas av vol) eller valfria som är None
                    data_to_save[key] = None 

            if errors:
                 return self.async_show_form(step_id="user", data_schema=self._build_user_schema(user_input), errors=errors)

            _LOGGER.debug("Initial setup data to save: %s", data_to_save)
            await self.async_set_unique_id(f"{DOMAIN}_smart_charger")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=DEFAULT_NAME, data=data_to_save)

        return self.async_show_form(step_id="user", data_schema=self._build_user_schema(), errors=errors)

    def _build_user_schema(self, current_values: dict | None = None):
        def _get_initial_value(key_const: Any, default: Any = None):
            key_str = str(key_const.schema) if hasattr(key_const, 'schema') else str(key_const)
            if current_values: return current_values.get(key_str, default)
            return default

        return vol.Schema({
            vol.Required(CONF_CHARGER_DEVICE, default=_get_initial_value(CONF_CHARGER_DEVICE)): DeviceSelector(DeviceSelectorConfig(integration="easee")),
            vol.Required(CONF_STATUS_SENSOR, default=_get_initial_value(CONF_STATUS_SENSOR)): EntitySelector(EntitySelectorConfig(domain="sensor", multiple=False)),
            vol.Required(CONF_CHARGER_ENABLED_SWITCH_ID, default=_get_initial_value(CONF_CHARGER_ENABLED_SWITCH_ID)): EntitySelector(EntitySelectorConfig(domain="switch", multiple=False)),
            vol.Required(CONF_PRICE_SENSOR, default=_get_initial_value(CONF_PRICE_SENSOR)): EntitySelector(EntitySelectorConfig(domain="sensor", multiple=False)),
            vol.Optional(CONF_SURCHARGE_HELPER, default=_get_initial_value(CONF_SURCHARGE_HELPER)): EntitySelector(EntitySelectorConfig(domain=["sensor", "input_number"], multiple=False)),
            vol.Optional(CONF_TIME_SCHEDULE_ENTITY, default=_get_initial_value(CONF_TIME_SCHEDULE_ENTITY)): EntitySelector(EntitySelectorConfig(domain="schedule", multiple=False)),
            vol.Optional(CONF_HOUSE_POWER_SENSOR, default=_get_initial_value(CONF_HOUSE_POWER_SENSOR)): EntitySelector(EntitySelectorConfig(domain="sensor", device_class=SensorDeviceClass.POWER, multiple=False)),
            vol.Optional(CONF_SOLAR_PRODUCTION_SENSOR, default=_get_initial_value(CONF_SOLAR_PRODUCTION_SENSOR)): EntitySelector(EntitySelectorConfig(domain="sensor", device_class=SensorDeviceClass.POWER, multiple=False)),
            vol.Optional(CONF_SOLAR_SCHEDULE_ENTITY, default=_get_initial_value(CONF_SOLAR_SCHEDULE_ENTITY)): EntitySelector(EntitySelectorConfig(domain="schedule", multiple=False)),
            vol.Optional(CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR, default=_get_initial_value(CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR)): EntitySelector(EntitySelectorConfig(domain="sensor", multiple=False)),
            vol.Optional(CONF_EV_POWER_SENSOR, default=_get_initial_value(CONF_EV_POWER_SENSOR)): EntitySelector(EntitySelectorConfig(domain="sensor", device_class=SensorDeviceClass.POWER, multiple=False)),
            vol.Optional(CONF_EV_SOC_SENSOR, default=_get_initial_value(CONF_EV_SOC_SENSOR)): EntitySelector(EntitySelectorConfig(domain="sensor", device_class=SensorDeviceClass.BATTERY, multiple=False)),
            vol.Optional(CONF_TARGET_SOC_LIMIT, default=_get_initial_value(CONF_TARGET_SOC_LIMIT)): NumberSelector(NumberSelectorConfig(min=0, max=100, step=0.5, mode=NumberSelectorMode.BOX, unit_of_measurement="%")),
            vol.Optional(CONF_SCAN_INTERVAL, default=_get_initial_value(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_SECONDS)): NumberSelector(NumberSelectorConfig(min=10, max=3600, step=1, mode=NumberSelectorMode.BOX, unit_of_measurement="sekunder")),
        })
