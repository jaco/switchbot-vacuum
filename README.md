# SwitchBot Vacuum for Home Assistant

Custom [HACS](https://hacs.xyz/) integration for SwitchBot robot vacuums (S10 and compatible models) in Home Assistant.

## Why this exists

The official [SwitchBot Cloud integration](https://www.home-assistant.io/integrations/switchbot_cloud/#vacuums) provides basic vacuum controls. This custom integration uses internal cloud APIs, reverse-engineered from the mobile app, to add room-specific cleaning and automatic room name discovery.

## Features

- **Vacuum entity** with full state reporting (cleaning, docked, paused, returning, idle)
- **Error detection (S10)** — an error sensor with specific error types and a problem binary sensor for automations. K10+ error reporting is not implemented; see the model support table below.
- **Room sensor entities** — one per room discovered from the vacuum's map
- **Room-aware cleaning** — clean specific rooms by name or ID. S10 supports mode, suction, water level, passes, and order; K10+ EU supports vacuum/mop mode, suction, passes, and order. K10+ uses a disposable wipe with no water tank or pump.
- **Automatic room discovery** — room names are downloaded from the vacuum's cloud map every 24 hours
- **Multi-device support** — if your account has multiple SwitchBot vacuums, the config flow lets you pick which one to add
- **Force refresh service** — manually re-download room data and device status on demand

## Model support

The feature list includes capabilities that differ by model. This change adds K10+ EU room support to the existing integration and keeps the same login, entities, and `clean_rooms` / `force_refresh` services.

| Capability | S10 | K10+ (EU) |
|------------|-----|-----------|
| Account email/password setup and device selection | Existing flow | Same flow; no manual token capture required |
| Vacuum activity and battery | Existing support | Existing support; docked, cleaning and paused observed live |
| Specific error types and problem detection | Existing support | Not implemented; do not rely on these sensors for K10+ fault automations |
| Room sensors with names from the map | Existing support | Supported; all six rooms verified on one device |
| `clean_rooms` by name or ID | Existing support | Supported; one room physically verified |
| Room command mode and suction overrides | Supported | Implemented: sweep or mop; fan_level 1–4. Quiet write verified live; mop test pending |
| Water output | Supported | Not applicable: disposable wipe, no water tank or pump |
| Empty dustbin button | Not added by this change | Implemented; docked precondition and robot reply checked. Live status showed collecting → docked |
| Cleaning mode select | Not added by this change | Vacuum/mop with mop-plate checks; selecting a mode does not start cleaning |
| Room command passes and order | Supported | Supported by the protocol; one pass physically verified |
| Automatic map refresh every 24 hours | Existing support | Implemented; the full 24-hour interval has not yet been observed |
| Multiple vacuums on one account | Existing flow | Selected-device routing tested with fake devices; only one physical device tested |
| `force_refresh` for status and rooms | Existing service | Same service using the K10+ map protocol |

K10+ Pro room support and regions outside EU are not added by this change.

## Installation

### HACS (recommended)

1. Open HACS in Home Assistant
2. Click the three dots menu → **Custom repositories**
3. Add `https://github.com/jaco/switchbot-vacuum` with category **Integration**
4. Search for "SwitchBot Vacuum" and install
5. Restart Home Assistant

### Manual

Copy `custom_components/switchbot_vacuum/` to your Home Assistant `config/custom_components/` directory and restart.

## Configuration

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **SwitchBot Vacuum**
3. Enter your SwitchBot account email and password
4. If multiple vacuums are found, select the one to add

You can add the integration multiple times for multiple vacuums.

If you change your SwitchBot password, open the integration entry menu and select **Reconfigure** to enter the current password. Authentication failures also offer a reauthentication form. Both flows keep the existing device and entities, and check that the same vacuum is still present in the account.

## Screenshots

| Device & room entities | Clean rooms service | Room sensor detail |
|---|---|---|
| ![Device entities](screenshots/device-entities.png) | ![Clean rooms service](screenshots/clean-rooms-service.png) | ![Room sensor detail](screenshots/room-sensor-detail.png) |

## Entities

### Vacuum

The main entity (`vacuum.switchbot_vacuum`) provides:

| Feature | Description |
|---------|-------------|
| **State** | idle, cleaning, docked, paused, returning |
| **Battery** | Current battery percentage |
| **Fan speed** | quiet, standard, strong, max |
| **Start** | Start full cleaning |
| **Stop / Pause** | Stop or pause current cleaning |
| **Return to base** | Send vacuum to charging station |

#### Extra attributes

The vacuum entity exposes additional attributes you can use in automations and templates. Water and cleaning-summary attributes below describe S10. K10+ exposes the actual `clean_type` (`sweep` or `mop`), `mopping_pad_installed`, rooms and a default pass count, not the last room command's pass count:

| Attribute | Example | Description |
|-----------|---------|-------------|
| `water_level` | `1` | Current water output level (1–3) |
| `clean_type` | `sweep_mop` | Current mode: `sweep`, `mop`, or `sweep_mop` |
| `times` | `1` | Number of cleaning passes |
| `last_clean_area` | `45` | Area cleaned in last session (m²) |
| `last_clean_time` | `30` | Duration of last session (minutes) |
| `rooms` | `{"ROOM_013": "Kitchen", ...}` | All known rooms with IDs and names |

**Reading attributes in templates:**

```yaml
# Get battery level
{{ state_attr('vacuum.switchbot_vacuum', 'battery_level') }}

# Get current clean type
{{ state_attr('vacuum.switchbot_vacuum', 'clean_type') }}

# Get last cleaned area
{{ state_attr('vacuum.switchbot_vacuum', 'last_clean_area') }} m²

# List all room names
{% for id, name in state_attr('vacuum.switchbot_vacuum', 'rooms').items() %}
  {{ name }} ({{ id }})
{% endfor %}
```

### Error & problem detection

| Entity | Type | Description |
|--------|------|-------------|
| `binary_sensor.*.problem` | Problem | ON when any error is active — simplest automation trigger |
| `sensor.*.error` | Sensor | Current error type as a string (e.g. `stuck`, `clean_water_tank_empty`) or `none` |

The following mappings apply to S10. K10+ currently supplies a fixed zero error code, so its error/problem entities do not provide reliable fault detection.

The S10 error sensor state is one of:

| State | Error code | Description |
|-------|-----------|-------------|
| `none` | 0 | No error |
| `stuck` | 2000 | Robot is stuck |
| `wheel_stuck` | 2001 | Wheel stuck or suspended |
| `side_brush_stuck` | 2002 | Side brush tangled |
| `main_brush_stuck` | 2003 | Main brush/roller tangled |
| `bumper_stuck` | 2004 | Bumper stuck — check for debris |
| `dust_bin_missing` | 2005 | Dust bin not installed |
| `filter_clogged` | 2006 | Filter needs cleaning |
| `cliff_sensor_error` | 2007 | Cliff/drop sensor error |
| `low_battery` | 2008 | Battery too low to continue |
| `charging_error` | 2009 | Cannot charge — check dock contacts |
| `internal_error` | 2010 | Internal system error |
| `laser_sensor_error` | 2011 | LDS/laser sensor error |
| `path_blocked` | 2012 | Navigation error — cannot find path |
| `clean_water_tank_empty` | 2728 | Clean water tank empty |
| `dirty_water_tank_full` | 2739 | Dirty water tank full |
| `dirty_water_tank_removed` | 2740 | Dirty water tank removed |
| `fault` | — | Work status is fault but no specific error code |
| `error_XXXX` | XXXX | Unknown code (logged as warning for discovery) |

Both entities expose `error_code` (raw integer) and `error_type`/`error_description` as extra attributes.

### Room sensors

Each room discovered from the vacuum's map gets a sensor entity (e.g. `sensor.kitchen`, `sensor.bedroom`). The sensor value is the room name, and the `room_id` attribute contains the internal ID (S10: e.g. `ROOM_013`; K10+: e.g. `room1`).

```yaml
# Get room ID for use in clean_rooms service
{{ state_attr('sensor.kitchen', 'room_id') }}
```

## Services

### `switchbot_vacuum.clean_rooms`

Clean specific rooms by name or ID. The example and mode/suction/water defaults below apply to S10. For K10+ EU, the same service also accepts `mode` (`sweep` or `mop`) and `fan_level` (1–4), as shown in the K10+ section. Water settings and simultaneous sweep/mop do not apply to this hardware.

```yaml
service: switchbot_vacuum.clean_rooms
target:
  entity_id: vacuum.switchbot_vacuum
data:
  rooms:
    - "Kitchen"
    - "Bedroom"
    - "ROOM_003"
  mode: "mop"
  fan_level: 2
  water_level: 2
  times: 1
  force_order: true
```

| Parameter | Required | Default | Values |
|-----------|----------|---------|--------|
| `rooms` | yes | — | List of room names or IDs (can mix) |
| `mode` | no | S10: `sweep_mop`; K10+: current mode | `sweep`, `mop`; `sweep_mop` is S10 only |
| `fan_level` | no | S10: `1`; K10+: each room's app setting | 1 (quiet), 2 (standard), 3 (strong), 4 (max) |
| `water_level` | no | S10: `1` | S10 only: 1 (low), 2 (medium), 3 (high); omit for K10+ |
| `times` | no | `1` | 1 or 2 passes |
| `force_order` | no | `true` | Clean rooms in the specified order |

### `switchbot_vacuum.force_refresh`

Force an immediate refresh of device status and room data from the model's cloud map (S10: S3; K10+: signed Qihoo/OSS map download).

```yaml
service: switchbot_vacuum.force_refresh
target:
  entity_id: vacuum.switchbot_vacuum
```

## Automation examples

### Mop the kitchen every day at 10:00

```yaml
automation:
  - alias: "Daily kitchen mop"
    trigger:
      - platform: time
        at: "10:00:00"
    action:
      - service: switchbot_vacuum.clean_rooms
        target:
          entity_id: vacuum.switchbot_vacuum
        data:
          rooms:
            - "Kitchen"
          mode: "mop"
          water_level: 2
```

### Notify when water tank is empty

```yaml
automation:
  - alias: "S10 water tank empty"
    trigger:
      - platform: state
        entity_id: sensor.floor_cleaning_robot_s10_error
        to: "clean_water_tank_empty"
    action:
      - service: notify.mobile_app
        data:
          title: "SwitchBot S10"
          message: "Clean water tank is empty — refill to continue cleaning"
```

### Notify on any problem

```yaml
automation:
  - alias: "S10 any problem"
    trigger:
      - platform: state
        entity_id: binary_sensor.floor_cleaning_robot_s10_problem
        to: "on"
    action:
      - service: notify.mobile_app
        data:
          title: "SwitchBot S10 problem"
          message: >
            Error: {{ state_attr('sensor.floor_cleaning_robot_s10_error', 'error_description') }}
            (code {{ state_attr('sensor.floor_cleaning_robot_s10_error', 'error_code') }})
```

### Full clean when everyone leaves

```yaml
automation:
  - alias: "Clean when away"
    trigger:
      - platform: state
        entity_id: group.family
        to: "not_home"
    action:
      - service: vacuum.start
        target:
          entity_id: vacuum.switchbot_vacuum
```

## K10+ rooms (EU region)

Room names and numeric IDs are read from the current map using the signed Qihoo API. Creating cleaning schedules is not required. Use `switchbot_vacuum.force_refresh` to refresh the map and room sensors.

Use the existing `switchbot_vacuum.clean_rooms` service for K10+ room cleaning:

```yaml
action: switchbot_vacuum.clean_rooms
target:
  entity_id: vacuum.switchbot_vacuum
data:
  rooms:
    - "Entry"
  mode: sweep
  fan_level: 1
  times: 1
  force_order: true
```

The action accepts room names, numeric IDs as strings, and legacy IDs such as `room1`. It supports one or two passes. Omit `fan_level` to keep each room's app settings, or supply 1–4 to override only the selected rooms for this request. Omit `mode` to keep the current device mode, or choose `sweep` / `mop`. Unknown rooms, `water_level`, and `sweep_mop` are rejected. A failed K10+ room command never falls back to whole-house cleaning.

### K10+ controls

The device also exposes a **Cleaning mode** select (`vacuum`, `mop`) and an **Empty dustbin** button. Entity IDs are generated by Home Assistant and can be found on the device page.

- Install the mop plate with its cleaning sheet before selecting `mop`; remove it before selecting `vacuum`. K10+ cannot vacuum and mop simultaneously. [SwitchBot's hardware guidance](https://support.switch-bot.com/hc/en-us/articles/14215810297879-Can-SwitchBot-Mini-Robot-Vacuum-K10-K10-Pro-K11-K11-Pro-Simultaneously-Vacuum-and-Mop).
- Changing the select sets the mode without starting cleaning. Pause an active task before changing modes. Room cleaning waits for the new mode to be confirmed before starting.
- Use the standard `vacuum.set_fan_speed` action with `quiet`, `standard`, `strong`, or `max` to set device suction. Room commands have their own `fan_level` override; when omitted, app room settings are retained.
- Press **Empty dustbin** while docked to collect dust into the base. The command is sent once and the robot's reply is checked.
- Mode and mop-plate state are read from Qihoo properties each status update. If that read fails, these extra controls become unavailable while basic vacuum status can continue through SwitchBot.

The new mode, suction and emptying paths were reconstructed from Android 10.6. Seventy focused tests passed in HA 2026.10.1 / Python 3.14.6. Live HA calls changed suction from max to quiet and produced a collecting-dust → docked status sequence. A short quiet Entry call received the robot reply and Pause was sent after 9.35 seconds; the owner confirmed emptying, room cleaning and stopping. The immediate post-start cloud refresh was removed to avoid overwriting the acknowledged start with a cached docked state; regular status polling remains. Mop switching still needs a physical test with the plate installed. The earlier Entry test with existing room settings was physically confirmed.

This implementation uses the existing SwitchBot email/password login, obtains a delegated Qihoo token, uploads the selected-room configuration with temporary OSS credentials, and waits for the robot's reply. It never automatically retries the start request. If confirmation times out, check the robot before retrying.

The protocol was reconstructed from SwitchBot Android 10.6 and physically verified on one K10+ using the EU endpoints: the selected room started and the robot returned `ErrorNO: 0`. Login recovery, room discovery, and a dashboard room-start/pause test were also verified in Home Assistant Container 2026.10.1, with its existing battery compatibility migration applied. Other regions and K10+ Pro room cleaning are not covered by this implementation. This remains an unofficial cloud protocol and may change.

## Technical notes

- The integration polls the device every 30 seconds
- Auth tokens are refreshed automatically every 1.5 hours
- Room names are refreshed from the cloud map every 24 hours (or on demand via `force_refresh`); room refresh runs as a background task so it never blocks setup
- K10+ status and room requests share Home Assistant's managed HTTP session and DNS cache. A start request is never retried automatically.
- For S10, error codes are read from device property 1019 and mapped to descriptive strings; unknown codes are logged as warnings so they can be reported and added
- Error code mappings were reverse-engineered from the SwitchBot APK's Flutter module (`feature_sweeper`, Qihoo 360 SDK)

## License

MIT
