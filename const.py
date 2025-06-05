# File version: 2025-06-05 0.2.0
"""Constants for the Smart EV Charging integration."""

DOMAIN = "smart_ev_charging"

# Konfigurationsnycklar från ConfigFlow
CONF_CHARGER_DEVICE = "charger_device_id"
CONF_STATUS_SENSOR = "status_sensor_id"
CONF_PRICE_SENSOR = "price_sensor_id"
CONF_TIME_SCHEDULE_ENTITY = "time_schedule_entity_id"
CONF_HOUSE_POWER_SENSOR = "house_power_sensor_id"
CONF_SOLAR_PRODUCTION_SENSOR = "solar_production_sensor_id"
CONF_SOLAR_SCHEDULE_ENTITY = "solar_schedule_entity_id"
CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR = "charger_max_current_limit_sensor_id"
CONF_CHARGER_DYNAMIC_CURRENT_SENSOR = "charger_dynamic_current_sensor_id"
CONF_SCAN_INTERVAL = "scan_interval_seconds"
CONF_CHARGER_ENABLED_SWITCH_ID = "charger_enabled_switch_id"

CONF_EV_SOC_SENSOR = "ev_soc_sensor_id"
CONF_TARGET_SOC_LIMIT = "target_soc_limit"

CONF_DEBUG_LOGGING = "debug_logging_enabled"

DEFAULT_NAME = "Avancerad Elbilsladdning"
DEFAULT_SCAN_INTERVAL_SECONDS = 30

ENTITY_ID_SUFFIX_SMART_ENABLE_SWITCH = "smart_charging_enabled"
ENTITY_ID_SUFFIX_MAX_PRICE_NUMBER = "max_charging_price"
ENTITY_ID_SUFFIX_ENABLE_SOLAR_CHARGING_SWITCH = "solar_surplus_charging_enabled"
ENTITY_ID_SUFFIX_SOLAR_BUFFER_NUMBER = "solar_charging_buffer"
ENTITY_ID_SUFFIX_MIN_SOLAR_CHARGE_CURRENT_A_NUMBER = "min_solar_charging_current"

ENTITY_ID_SUFFIX_ACTIVE_CONTROL_MODE_SENSOR = "active_control_mode"

# Exempel på statusvärden från Easee
EASEE_STATUS_DISCONNECTED = ["disconnected", "car_disconnected"]
EASEE_STATUS_AWAITING_START = "awaiting_start"
EASEE_STATUS_READY_TO_CHARGE = [
    "ready_to_charge",
    "charger_ready",
    "awaiting_schedule",
    "standby",
]
EASEE_STATUS_CHARGING = "charging"
EASEE_STATUS_PAUSED = "paused"
EASEE_STATUS_COMPLETED = "completed"
EASEE_STATUS_ERROR = "error"
EASEE_STATUS_OFFLINE = "offline"

# Återinförda tjänstekonstanter som används av tester
EASEE_SERVICE_RESUME_CHARGING = "resume_charging"
EASEE_SERVICE_ACTION_COMMAND = "action_command"
EASEE_SERVICE_SET_DYNAMIC_CURRENT = "set_charger_dynamic_limit"
# EASEE_SERVICE_PAUSE_CHARGING = "pause" # Om du vill ha med dessa för framtiden
# EASEE_SERVICE_RESUME_CHARGING = "start" # Om du vill ha med dessa för framtiden

# Kontrollägen
CONTROL_MODE_PRICE_TIME = "PRIS_TID"
CONTROL_MODE_SOLAR_SURPLUS = "SOLENERGI"
CONTROL_MODE_MANUAL = "AV"

# Andra konstanter
MIN_CHARGE_CURRENT_A = 6
MAX_CHARGE_CURRENT_A_HW_DEFAULT = 16
POWER_MARGIN_W = 300
# Återinförd konstant som används av tester
SOLAR_SURPLUS_DELAY_SECONDS = 60

# Fysiska konstanter för beräkningar
PHASES = 3  # Antal faser som normalt används för laddning (kan behöva justeras om 1-fas är vanligt)
VOLTAGE_PHASE_NEUTRAL = 230  # Standard fasspänning i Sverige
