# Protimeter BLE — Project Notes

## Device Information

| Field | Value |
| --- | --- |
| Model | Protimeter BLE Humidity Sensor |
| MAC address (south wall) | `00:22:A3:00:C7:57` (KällarväggSyd) |
| MAC address (north wall) | `00:22:A3:00:C3:0E` (KällarväggNord) |
| BLE advertised service | `5b00a5a5-0002-9b23-e111-02d100550000` |
| App | ProtimeterBLE.apk (Xamarin/.NET) |

## Protocol Reverse Engineering

### Method

1. **HCI log capture** — Enabled Android developer mode → Bluetooth HCI snoop log.
   Performed actions in the official app (connect, read, export history).
   Pulled `btsnoop_hci.log` via ADB.

2. **tshark analysis** — Filtered GATT write/notify packets, identified three
   command codes: `0x4F`, `0x53`, `0x52…`. Decoded timestamp and some value bytes
   manually by cross-referencing with values shown on screen.

3. **APK decompilation** — Downloaded the official APK, decompiled with `jadx`.
   The app is Xamarin (.NET), so Java output is boilerplate; the real logic is in
   `ProtimeterApp.dll`. Disassembled with `monodis` (Mono SDK) to CIL bytecode.
   Extracted all protocol constants and parsing formulas from the IL.

### Key source classes (in `ProtimeterApp.dll`)

- `ProtimeterApp.Bluetooth.ServiceIds` — GATT service UUIDs
- `ProtimeterApp.Bluetooth.CharacteristicIds` — characteristic UUIDs
- `ProtimeterApp.Bluetooth.CommandCodes` — ASCII command bytes
- `ProtimeterApp.Helpers.ByteHelper` — all parsing formulas and lookup tables
- `ProtimeterApp.Services.BluetoothService` — BLE connection flow

### Confirmed command codes

| Command | Byte | Description |
| --- | --- | --- |
| `S` | 0x53 | Get current sensor reading (12-byte response) |
| `R` | 0x52 | Read history records (6-byte payload, 20 bytes per record) |
| `C` | 0x43 | Get number of stored records |
| `O` | 0x4F | Read calibration offset (slot index) |
| `L` | 0x4C | Write calibration offset |
| `T` | 0x54 | Set device real-time clock |
| `F` | 0x46 | Set recording frequency |
| `A` | 0x41 | Set BLE advertising rate |
| `I` | 0x49 | Identify / pair |
| `D` | 0x44 | Clear stored history |

Note: `0x4F` (the `O` command, which we initially thought was a "current reading"
command based on the HCI logs) is actually the **calibration offset read** command.
It returns a 25-byte response that includes ambient conditions at calibration time.
The actual current-reading command is `S` (0x53).

### Sensor decoding (verified against captured data)

**Humidity:**

```python
humidity_pct = (high * 256 + low) / 16384.0 * 100.0
```

Example: `0x30 0x60` → 75.6 %RH ✓

**Temperature:**

```python
raw = high * 64.0 + low / 4.0        # top 14 bits of 16-bit big-endian word
temp_c = (raw / 16384.0) * 165.0 - 40.0
```

Example: `0x49 0xA0` → 7.45 °C ✓ (app showed 7.5 °C)

**Battery:** direct byte, 0–100 %

**WME:** multi-stage pipeline — raw int → ADC scale → piecewise table lookup →
temperature compensation → calibration offset (device-specific) → battery voltage
compensation. Full spec in `PROTOCOL.md`. Integration implements the first three
stages; calibration and voltage compensation require device-specific data.

### Historical data

Exported ~520 records (June 2025 – February 2026) from both sensors.
See `btsnoop-hci-logs/export-all-values.csv` and `last_10_readings.csv`.

Sensor readings at time of last capture (2026-02-24):

- KällarväggSyd: 27.3 %RH, 18.2 °C
- KällarväggNord: 91.0 %RH, 8.0 °C

## Home Assistant Integration

Location: `custom_components/protimeter_ble/`

### Architecture

```text
config_flow.py  →  creates ConfigEntry
    ↓
__init__.py  →  creates ProtimeterCoordinator, forwards to sensor platform
    ↓
coordinator.py  →  DataUpdateCoordinator
                   connect BLE → write S → wait for 12-byte notification
                   → parse with parser.py → return ProtimeterReading
    ↓
sensor.py  →  4 CoordinatorEntity instances per device
              (Humidity, Temperature, Battery, WME)
```

### Config entry data keys

- `address` — MAC address (upper-case)
- `name` — friendly name
- `update_interval` — polling interval in minutes (default 5)

### Known issues / TODO

- **WME calibration**: `O` command response parsing is not yet implemented.
  WME values are approximate (no device-specific calibration offsets applied).
  Accuracy within ~2 % for typical indoor conditions without calibration.

- **Write response type**: The integration uses `response=False`
  (Write Without Response). If a device requires Write With Response, change
  `response=False` to `response=True` in `coordinator.py`.

- **Notification UUID fallback**: The old `05_notification_logger.py` script
  used characteristic `00001014-d102-11e1-9b23-00025b00a5a5` which was discovered
  via GATT dump. The integration uses `00005501` (from the APK). If notifications
  are not received, try swapping to `00001014` in `const.py`.

- **History import**: Not yet implemented in the HA integration — only live
  polling via `S` command is supported. History can still be exported manually
  using the debug scripts.

## Tools Used

| Tool | Purpose |
| --- | --- |
| Android HCI snoop log | Raw BLE packet capture |
| `adb` | Pull btsnoop log from phone |
| `tshark` | Parse and filter HCI log files |
| `jadx` 1.5.5 | Decompile APK to Java (Xamarin boilerplate only) |
| `monodis` (Mono SDK) | Disassemble .NET DLL to CIL bytecode |
| `bleak` 2.1.1 | Python BLE client for debug scripts |

## File Inventory

```text
apk/
└── ProtimeterBLE.apk           Official Android app (source of protocol truth)

btsnoop-hci-logs/
├── btsnoop_hci-*.log           Raw HCI captures
├── export-all-values.csv       ~520 historical readings from both sensors
├── last_10_readings.csv        Latest 10 readings per sensor
└── current_value*.txt          Single-reading captures

outputs/
├── 4f-kommandot.txt            Analysis of 0x4F (O) command responses
├── 5200fb0104fe-kommandot.txt  Analysis of R command bulk export packets
├── phone_writes.txt            Timestamped write commands observed
└── from_screen                 Values cross-referenced from app screenshots

custom_components/protimeter_ble/
                                Home Assistant integration (complete)

scripts/
├── 01_ble_scanner.py           BLE device scanner
├── 02_device_connector.py      GATT service/characteristic explorer
├── 03_gatt_explorer.sh         gatttool wrapper
├── 04_scan_to_file.py          Scanner with file output
└── 05_notification_logger.py   Subscribe to notifications and log to file

PROTOCOL.md                     Complete BLE protocol specification
PROJECT_NOTES.md                This file
README.md                       Project overview and installation instructions
todo.txt                        Phase checklist
```
