# File version: 2025-05-29 0.1.31
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

CONF_DEBUG_LOGGING = "debug_logging_enabled"

DEFAULT_NAME = "Avancerad Elbilsladdning"
DEFAULT_SCAN_INTERVAL_SECONDS = 30

ENTITY_ID_SUFFIX_SMART_ENABLE_SWITCH = "smart_charging_enabled"
ENTITY_ID_SUFFIX_MAX_PRICE_NUMBER = "max_charging_price"
ENTITY_ID_SUFFIX_ENABLE_SOLAR_CHARGING_SWITCH = "solar_surplus_charging_enabled"
ENTITY_ID_SUFFIX_SOLAR_BUFFER_NUMBER = "solar_charging_buffer"
ENTITY_ID_SUFFIX_MIN_SOLAR_CHARGE_CURRENT_A_NUMBER = "min_solar_charging_current"

# Borttagna konstanter för sessionssensorer:
# ENTITY_ID_SUFFIX_SESSION_ENERGY_SENSOR = "session_energi"
# ENTITY_ID_SUFFIX_SESSION_COST_SENSOR = "session_kostnad"

ENTITY_ID_SUFFIX_ACTIVE_CONTROL_MODE_SENSOR = "active_control_mode"

# Easee specifika tjänster och statusvärden
EASEE_SERVICE_SET_DYNAMIC_CURRENT = "set_dynamic_charger_circuit_current"
EASEE_SERVICE_SET_CIRCUIT_MAX_CURRENT = "set_max_charger_circuit_current" # Används för att sätta max HW limit
EASEE_SERVICE_ENABLE_CHARGER = "activate_charger"
EASEE_SERVICE_DISABLE_CHARGER = "deactivate_charger"
EASEE_SERVICE_PAUSE_CHARGING = "pause_charging"
EASEE_SERVICE_RESUME_CHARGING = "resume_charging"

# Exempel på statusvärden från Easee (kan variera/utökas)
EASEE_STATUS_DISCONNECTED = ["disconnected", "car_disconnected"] # Kan behöva anpassas till exakta värden från din sensor
EASEE_STATUS_AWAITING_START = "awaiting_start" # Inkluderar bilen ansluten, väntar på startsignal
EASEE_STATUS_READY_TO_CHARGE = ["ready_to_charge", "charger_ready", "awaiting_schedule", "standby"] # Laddklar, men inte aktivt laddande
EASEE_STATUS_CHARGING = "charging"
EASEE_STATUS_PAUSED = "paused" # Pausad av användare eller system
EASEE_STATUS_COMPLETED = "completed" # Laddning klar (t.ex. nått 100% SoC)
EASEE_STATUS_ERROR = "error"
EASEE_STATUS_OFFLINE = "offline" # Helt offline, inte samma som disconnected

# Kontrollägen
CONTROL_MODE_PRICE_TIME = "PRIS_TID"
CONTROL_MODE_SOLAR_SURPLUS = "SOLENERGI"
CONTROL_MODE_MANUAL = "AV" # Smart styrning avstängd

# Andra konstanter
MIN_CHARGE_CURRENT_A = 6 # Minsta ström laddaren kan hantera
MAX_CHARGE_CURRENT_A_HW_DEFAULT = 16 # Fallback om HW sensor saknas
POWER_MARGIN_W = 300 # Marginal för husets effekt innan nedjustering
SOLAR_SURPLUS_DELAY_SECONDS = 300 # 5 minuter fördröjning för solenergiläge
PRICE_CHECK_INTERVAL_MINUTES = 15 # Hur ofta vi kollar om priset är ok (om inte laddning pågår)