"""Constants for the SwitchBot Vacuum integration."""
from typing import Final

DOMAIN: Final = "switchbot_vacuum"

# Config
CONF_USERNAME: Final = "username"
CONF_PASSWORD: Final = "password"
CONF_DEVICE_MAC: Final = "device_mac"

# API
API_AUTH_HOST: Final = "https://account.api.switchbot.net"
API_HOST_EU: Final = "https://wonderlabs.eu.api.switchbot.net"
CLIENT_ID: Final = "5nnwmhmsa9xxskm14hd85lm9bm"
APP_VERSION: Final = "8.6.1"
API_TIMEOUT: Final = 30
DEVICE_TYPE_S10: Final = "WoSweeperOrigin"

# Commands
CMD_CLEAN: Final = 1001
CMD_GO_CHARGE: Final = 1008
CMD_CONTROL: Final = 1009
CMD_CHANGE_MODE: Final = 1043

# Work Status
WORK_STATUS_STANDBY: Final = 1
WORK_STATUS_CHARGING: Final = 2
WORK_STATUS_CHARGE_DONE: Final = 3
WORK_STATUS_PAUSED: Final = 4
WORK_STATUS_GO_CHARGE: Final = 5
WORK_STATUS_CLEANING: Final = 8

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

# Fan speed mapping
FAN_SPEEDS: Final = {
    "quiet": 1,
    "standard": 2,
    "strong": 3,
    "max": 4,
}
FAN_SPEED_LIST: Final = list(FAN_SPEEDS.keys())

# Clean types
CLEAN_TYPE_SWEEP: Final = "sweep"
CLEAN_TYPE_MOP: Final = "mop"
CLEAN_TYPE_SWEEP_MOP: Final = "sweep_mop"

# S3
S3_REGION: Final = "eu-central-1"

# Timings
UPDATE_INTERVAL_SECONDS: Final = 30
TOKEN_REFRESH_SECONDS: Final = 5400  # 1.5 hours
ROOM_REFRESH_SECONDS: Final = 86400  # 24 hours
