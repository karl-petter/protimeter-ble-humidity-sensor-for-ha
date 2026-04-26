# Contributing to Protimeter BLE

---

## Development environment

No Home Assistant installation is required to work on the parser or run tests.

```bash
git clone <repo>
cd protimeter-ble-humidity-sensor-for-ha
pip install pytest
```

The integration itself requires HA to be running. Use `deploy.sh` to push changes
to a local HA instance over SSH:

```bash
./deploy.sh <user> <host>
# e.g. ./deploy.sh homeassistant homeassistant.local
```

Then reload the integration in HA: **Settings → Devices & Services →
Protimeter BLE → ⋮ → Reload**.

---

## Running tests

```bash
pytest tests/
```

Tests use real BLE notification bytes captured from the device and
cross-referenced against the official app. No HA or BLE hardware needed.

`tests/conftest.py` stubs out all `homeassistant` and `bleak` modules so
`parser.py` can be imported in a plain Python environment.

To add a new test case: capture raw R-command notification bytes from the HA
debug log, create a `CalibrationOffset` list from the O-command log entries,
and assert against app-confirmed values.

---

## Architecture

```text
config_flow.py   →  ConfigEntry created (address, name, fetch_interval_days)
     ↓
__init__.py      →  creates ProtimeterCoordinator, schedules first fetch
     ↓
coordinator.py   →  DataUpdateCoordinator
                    1. BLE connect
                    2. C command → record count
                    3. O command → 4 calibration offsets
                    4. R command → new history records
                    5. Import as HA long-term statistics (hourly buckets)
                    6. Persist last_record_id in entry.data
                    7. Return most-recent record as coordinator.data
     ↓
sensor.py        →  5 CoordinatorEntity instances per device
                    (Humidity, Temperature, WME, Battery, Last reading)
button.py        →  Fetch History button — triggers coordinator.async_refresh()
parser.py        →  Pure Python, no HA dependencies. Decodes all BLE responses.
                    Unit-tested independently.
```

### Key design decisions

- **History-based, not live** — The integration reads the device's stored records
  (one per hour) rather than polling for live readings. This preserves battery life;
  the device's BLE radio is only active when HA connects.

- **Statistics, not state history** — Records are stored as HA long-term statistics
  (external, `source=protimeter_ble`) rather than entity state history. This allows
  arbitrary time ranges to be graphed without HA's state history retention limits.

- **Incremental fetch** — After the first full-history import, subsequent fetches
  only request records newer than `last_record_id` (with a 5-record overlap).

- **Non-blocking startup** — The first fetch is launched as a background task so
  HA startup is not delayed. Sensors show "unavailable" until the first fetch
  completes, then retain their last values even if later fetches fail.

---

## Config entry data keys

| Key | Type | Description |
| --- | --- | --- |
| `address` | str | Device MAC address (upper-case) |
| `name` | str | Friendly name |
| `fetch_interval_days` | int | Fetch interval (default: 7) |
| `last_record_id` | int | Highest record ID imported so far |

`last_record_id` is written back to `entry.data` after each successful fetch and
persisted across HA restarts. Removing and re-adding the integration resets it,
causing the next fetch to import the full history.

---

## Debug scripts

Standalone scripts for direct BLE interaction (useful when developing protocol
changes without deploying to HA):

```bash
pip install -r requirements.txt   # bleak

# Scan for nearby Protimeter devices
python3 scripts/01_ble_scanner.py

# Dump full GATT service/characteristic tree
python3 scripts/02_device_connector.py AA:BB:CC:DD:EE:FF

# Subscribe to notifications and log raw bytes for 30 s
python3 scripts/05_notification_logger.py AA:BB:CC:DD:EE:FF 30
```

---

## HA debug log

To capture a debug log from HA:

1. Go to **Settings → System → Logs → Load full logs → Enable debug logging**
2. Select `custom_components.protimeter_ble`
3. Reproduce the issue
4. Download the log file

Debug-level messages do not appear in the HA logs UI — download the full log file.
R-command notification hex bytes in the log can be used as test inputs in
`tests/test_parser.py`.
