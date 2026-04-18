# Protimeter BLE — Home Assistant Integration

A Home Assistant custom integration for the **[Protimeter BLE humidity sensor](https://www.protimeter.com/ble)**.
Exposes humidity, temperature, Wood Moisture Equivalent (WME), and battery level
as HA sensor entities, enabling automations, dashboards, and long-term graphs.

The BLE protocol was fully reverse-engineered from the official Android APK
(`ProtimeterBLE.apk`, Xamarin/.NET). See [PROTOCOL.md](PROTOCOL.md) for the
complete specification.

---

## Features

- **4 sensor entities** per device: Humidity (%RH), Temperature (°C), Wood Moisture Equivalent (%), Battery (%)
- **Auto-discovery** via Home Assistant Bluetooth integration
- **Manual MAC address entry** as fallback
- **Configurable polling interval** (default: 5 minutes)
- **Multi-device support** (add each sensor as a separate config entry)

---

## Requirements

- Home Assistant 2023.x or later (uses the `bluetooth` integration)
- A Bluetooth adapter reachable by your HA host (USB dongle, built-in, or [ESPHome Bluetooth Proxy](https://esphome.io/components/bluetooth_proxy.html))
- Protimeter BLE humidity sensor (tested with MAC prefix `00:22:A3:…`)

---

## Installation

### HACS (recommended)

1. Open HACS → **Integrations** → ⋮ → **Custom repositories**
2. Add this repository URL, category **Integration**
3. Search for **Protimeter BLE** and install
4. Restart Home Assistant

### Manual

1. Copy the `custom_components/protimeter_ble/` folder into your HA configuration directory:

   ```text
   <config>/custom_components/protimeter_ble/
   ```

2. Restart Home Assistant

---

## Setup

### Auto-discovery

If your HA Bluetooth adapter can see the device advertising, a discovery notification
will appear automatically in **Settings → Devices & Services**. Confirm the device
and optionally change the name and polling interval.

### Via Settings UI

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **Protimeter BLE**
3. Enter the device MAC address (e.g. `00:22:A3:00:C7:57`)
4. Set a friendly name and polling interval

---

## Sensors

| Entity | Unit | Device class | Notes |
| --- | --- | --- | --- |
| Humidity | % | `humidity` | Relative humidity |
| Temperature | °C | `temperature` | |
| Battery | % | `battery` | |
| Wood Moisture Equivalent | % | — | Approximate without device calibration data |

WME is calculated from the raw ADC value using the lookup tables extracted
from the app, with temperature compensation applied. Full accuracy requires
calibration offsets stored on the device (readable via the `O` BLE command —
not yet implemented in this integration).

---

## Project Structure

```text
├── custom_components/
│   └── protimeter_ble/          # Home Assistant integration
│       ├── __init__.py          # Entry setup/teardown
│       ├── manifest.json        # Integration metadata + BT UUID matcher
│       ├── const.py             # UUIDs, commands, defaults
│       ├── parser.py            # BLE protocol decoding (pure Python, no HA deps)
│       ├── coordinator.py       # DataUpdateCoordinator (BLE connect → read → parse)
│       ├── config_flow.py       # UI config flow (discovery + manual)
│       ├── sensor.py            # Sensor entities
│       ├── strings.json         # UI strings
│       └── translations/en.json
├── scripts/                     # Standalone analysis/debug scripts
│   ├── 01_ble_scanner.py        # Scan for nearby BLE devices
│   ├── 02_device_connector.py   # Dump full GATT service/characteristic tree
│   ├── 03_gatt_explorer.sh      # gatttool wrapper
│   ├── 04_scan_to_file.py       # Scanner with file output
│   └── 05_notification_logger.py # Subscribe to notifications and log
├── btsnoop-hci-logs/            # Raw HCI captures from Android device
├── outputs/                     # Analysis artefacts and decoded data
├── apk/                         # Original Android APK (for reference)
├── PROTOCOL.md                  # Complete BLE protocol specification
├── PROJECT_NOTES.md             # Development notes
└── todo.txt                     # Phase checklist
```

---

## BLE Protocol Summary

Full specification: [PROTOCOL.md](PROTOCOL.md)

| Item | Value |
| --- | --- |
| Advertised service UUID | `00005500-d102-11e1-9b23-00025b00a5a5` |
| Command service UUID | `00005500-d102-11e1-9b23-00025b00a5a5` |
| Command characteristic | `00005501-d102-11e1-9b23-00025b00a5a5` |
| Get current reading | Write `S` (0x53), wait for 12-byte notification |
| Get history | Write `R` + start/end indices + XOR checksum, one 20-byte notification per record |
| Humidity formula | `(high×256 + low) / 16384 × 100` |
| Temperature formula | `((high×64) + (low/4)) / 16384 × 165 − 40` |

---

## Development

### Debug scripts

Run the standalone scripts against a live device for testing (requires `bleak`):

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Scan for nearby devices
python3 scripts/01_ble_scanner.py

# Dump GATT tree
python3 scripts/02_device_connector.py 00:22:A3:00:C7:57

# Log raw notifications for 30 s
python3 scripts/05_notification_logger.py 00:22:A3:00:C7:57 30
```

### Reverse engineering

The protocol was reverse-engineered by:

1. Capturing HCI logs from an Android phone (`btsnoop_hci.log`)
2. Analysing the logs with `tshark`
3. Decompiling the Android APK with `jadx` and `monodis` (Xamarin/.NET app)
4. Extracting exact byte-parsing formulas from `ProtimeterApp.dll`

Key source classes: `ProtimeterApp.Bluetooth.{ServiceIds,CharacteristicIds,CommandCodes}`,
`ProtimeterApp.Helpers.ByteHelper`.

---

## License

TBD
