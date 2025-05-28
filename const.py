# File version: 2025-05-21.6
"""Constants for the Smart EV Charging integration."""

DOMAIN = "smart_ev_charging"

# Konfigurationsnycklar från ConfigFlow
CONF_CHARGER_DEVICE = "charger_device_id"
CONF_STATUS_SENSOR = "status_sensor_id"
CONF_PRICE_SENSOR = "price_sensor_id"
CONF_SURCHARGE_HELPER = "surcharge_helper_id" 
CONF_TIME_SCHEDULE_ENTITY = "time_schedule_entity_id" 
CONF_HOUSE_POWER_SENSOR = "house_power_sensor_id" 
CONF_SOLAR_PRODUCTION_SENSOR = "solar_production_sensor_id" 
CONF_SOLAR_SCHEDULE_ENTITY = "solar_schedule_entity_id" 
CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR = "charger_max_current_limit_sensor_id" 
CONF_EV_POWER_SENSOR = "ev_power_sensor_id" 
CONF_SCAN_INTERVAL = "scan_interval_seconds"
CONF_CHARGER_ENABLED_SWITCH_ID = "charger_enabled_switch_id"

CONF_EV_SOC_SENSOR = "ev_soc_sensor_id"
CONF_TARGET_SOC_LIMIT = "target_soc_limit"

DEFAULT_NAME = "Avancerad Elbilsladdning"
DEFAULT_SCAN_INTERVAL_SECONDS = 30 # Ändrat default till 30 för snabbare initial testning

ENTITY_ID_SUFFIX_SMART_ENABLE_SWITCH = "smart_charging_enabled"
ENTITY_ID_SUFFIX_MAX_PRICE_NUMBER = "max_charging_price"
ENTITY_ID_SUFFIX_ENABLE_SOLAR_CHARGING_SWITCH = "solar_charging_enabled"
ENTITY_ID_SUFFIX_SOLAR_BUFFER_NUMBER = "solar_charging_buffer"
ENTITY_ID_SUFFIX_MIN_SOLAR_CHARGE_CURRENT_A_NUMBER = "min_solar_charge_current_a"
ENTITY_ID_SUFFIX_SESSION_ENERGY_SENSOR = "session_energy"
ENTITY_ID_SUFFIX_SESSION_COST_SENSOR = "session_cost"
ENTITY_ID_SUFFIX_ACTIVE_CONTROL_MODE_SENSOR = "active_control_mode"
