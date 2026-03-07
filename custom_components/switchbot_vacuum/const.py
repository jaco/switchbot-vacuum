"""Constants for the SwitchBot Vacuum integration."""
from typing import Final

DOMAIN: Final = "switchbot_vacuum"

# Config
CONF_USERNAME: Final = "username"
CONF_PASSWORD: Final = "password"
CONF_DEVICE_MAC: Final = "device_mac"
CONF_PRODUCT_KEY: Final = "product_key"

# API
API_AUTH_HOST: Final = "https://account.api.switchbot.net"
CLIENT_ID: Final = "5nnwmhmsa9xxskm14hd85lm9bm"
APP_VERSION: Final = "8.6.1"
API_TIMEOUT: Final = 30
DEVICE_TYPE_S10: Final = "WoSweeperOrigin"
DEVICE_TYPE_K10: Final = "WoSweeperMini"
DEVICE_TYPE_K10PRO: Final = "WoSweeperMiniPro"
SUPPORTED_DEVICE_TYPES: Final = {DEVICE_TYPE_S10, DEVICE_TYPE_K10, DEVICE_TYPE_K10PRO}

DEVICE_TYPE_TO_MODEL: Final = {
    DEVICE_TYPE_S10: "Floor Cleaning Robot S10",
    DEVICE_TYPE_K10: "Mini Robot Vacuum K10+",
    DEVICE_TYPE_K10PRO: "Mini Robot Vacuum K10+ Pro",
}

# K10+ WorkingStatus values (verified from APK VacuumUtil.smali)
# isCleaning  → [1, 2, 3]
# isPaused    → [4]
# isGoCharging→ [5]
# isCharging  → [6]  (also isDocking)
# isDocking   → [6, 7, 11]
# isCollecting→ [11]
K10_WORK_STATUS_CLEANING: Final = 1
K10_WORK_STATUS_CLEANING_2: Final = 2
K10_WORK_STATUS_CLEANING_3: Final = 3
K10_WORK_STATUS_PAUSED: Final = 4
K10_WORK_STATUS_GO_CHARGE: Final = 5
K10_WORK_STATUS_CHARGING: Final = 6
K10_WORK_STATUS_DOCKED: Final = 7
K10_WORK_STATUS_COLLECTING_DUST: Final = 11
K10_WORK_STATUS_STANDBY: Final = 0  # fallback

# Commands
CMD_CLEAN: Final = 1001
CMD_GO_CHARGE: Final = 1022
CMD_CONTROL: Final = 1009
CMD_CHANGE_MODE: Final = 1043

# Work Status
WORK_STATUS_STANDBY: Final = 1
WORK_STATUS_CHARGING: Final = 2
WORK_STATUS_CHARGE_DONE: Final = 3
WORK_STATUS_PAUSED: Final = 4
WORK_STATUS_GO_CHARGE: Final = 5
WORK_STATUS_RETURNING: Final = 7
WORK_STATUS_CLEANING: Final = 8
WORK_STATUS_CLEANING_ROOMS: Final = 9
WORK_STATUS_PAUSED_2: Final = 11
WORK_STATUS_GO_CHARGE_2: Final = 15
WORK_STATUS_DOCKING: Final = 19

# Properties
PROP_ONLINE: Final = 1003
PROP_BATTERY: Final = 1004
PROP_WORK_STATUS: Final = 1010
PROP_ERROR_CODE: Final = 1019
PROP_S3_BUCKET: Final = 1028
PROP_AWS_REGION: Final = 1031
PROP_TASK_INFO: Final = 1032
PROP_ROOM_PLANS: Final = 1038
PROP_MAP_INFO: Final = 1055
PROP_CLEAN_MODE: Final = 1053
PROP_CLEAN_SUMMARY: Final = 1052
PROP_AWS_CREDS: Final = 1130
PROP_FIRMWARE: Final = 1002

K10PRO_PROP_ONLINE: Final = 66
K10PRO_PROP_BATTERY: Final = 820
K10PRO_PROP_SUCTION_POW_LEVEL: Final = 4601
K10PRO_PROP_WORK_STATUS: Final = 4602
K10PRO_PROP_DUST_COLECT_FREQUENCY: Final = 4609
K10PRO_PROP_CHILD_LOCK: Final = 4610
K10PRO_PROP_DUST_COLECT_TIME: Final = 4614
K10PRO_PROP_AUTO_RESTART: Final = 4615

# Fan speed mapping (S10)
FAN_SPEEDS: Final = {
    "quiet": 1,
    "standard": 2,
    "strong": 3,
    "max": 4,
}
FAN_SPEED_LIST: Final = list(FAN_SPEEDS.keys())

# Fan speed mapping (K10+) — SuctionPowLevel 0-3 (confirmed via app: quiet/standard/strong/max)
K10_FAN_SPEEDS: Final = {
    "quiet": 0,
    "standard": 1,
    "strong": 2,
    "max": 3,
}
K10_FAN_SPEED_LIST: Final = list(K10_FAN_SPEEDS.keys())
K10_FAN_LEVEL_TO_SPEED: Final = {v: k for k, v in K10_FAN_SPEEDS.items()}

# Clean types
CLEAN_TYPE_SWEEP: Final = "sweep"
CLEAN_TYPE_MOP: Final = "mop"
CLEAN_TYPE_SWEEP_MOP: Final = "sweep_mop"

# Work status indicating fault (S10)
WORK_STATUS_FAULT: Final = 13

# Error codes (property 1019) — from APK feature_sweeper (sweeperErrorEnd_XXXX)
# Codes with known descriptions from APK string analysis; unknown codes logged for discovery.
ERROR_CODES: Final[dict[int, str]] = {
    0: "none",
    # sweeperErrorEnd_2000 – 2012: Qihoo 360 SDK error codes
    2000: "stuck",                      # Robot is stuck
    2001: "wheel_stuck",                # Wheel stuck or suspended
    2002: "side_brush_stuck",           # Side brush tangled/stuck
    2003: "main_brush_stuck",           # Main brush/roller tangled/stuck
    2004: "bumper_stuck",               # Bumper stuck — check for debris
    2005: "dust_bin_missing",           # Dust bin not installed
    2006: "filter_clogged",             # Filter needs cleaning
    2007: "cliff_sensor_error",         # Cliff/drop sensor error
    2008: "low_battery",               # Battery too low to continue
    2009: "charging_error",             # Cannot charge — check dock contacts
    2010: "internal_error",             # Internal system error
    2011: "laser_sensor_error",         # LDS/laser sensor error
    2012: "path_blocked",              # Cannot find path / navigation error
    # S10-specific base station errors
    2728: "clean_water_tank_empty",     # Clean water tank empty
    2739: "dirty_water_tank_full",      # Dirty water tank full
    2740: "dirty_water_tank_removed",   # Dirty water tank removed
}

# Separate operational failure reasons (from APK operateFail* strings)
# These appear as transient conditions checked before/during commands.
OPERATIONAL_ERRORS: Final[dict[str, str]] = {
    "operateFailLowBattery": "Low battery",
    "operateFailClearWaterEmpty": "Clean water tank empty",
    "operateFailDirtWaterFull": "Dirty water tank full",
    "operateFailNoClearWater": "No clean water tank",
    "operateFailNoDirtWater": "No dirty water tank",
    "operateFailOutBaseStation": "Robot not at base station",
    "operateFailOutStation": "Robot not at station",
    "operateFailRepeatControl": "Duplicate command",
}

# S3
S3_REGION: Final = "eu-central-1"

# Timings
UPDATE_INTERVAL_SECONDS: Final = 30
TOKEN_REFRESH_SECONDS: Final = 5400  # 1.5 hours
ROOM_REFRESH_SECONDS: Final = 86400  # 24 hours
