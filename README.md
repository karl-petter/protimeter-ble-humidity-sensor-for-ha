# Protimeter BLE — Home Assistant Integration

A Home Assistant custom integration for the **[Protimeter BLE humidity sensor](https://www.protimeter.com/products/protimeter-bluetooth-le-hygrometer/)**.

Exposes humidity, temperature, Wood Moisture Equivalent (WME), battery level, and
last-reading timestamp as HA sensor entities, with full long-term history imported
as HA statistics for graphing and automations.

The BLE protocol was fully reverse-engineered from the official Android APK
(`ProtimeterBLE.apk`, Xamarin/.NET). See [PROTOCOL.md](PROTOCOL.md) for the
complete specification.

---

## Features

- **5 sensor entities** per device: Humidity (%RH), Temperature (°C), WME (%), Battery (%), Last reading (timestamp)
- **Full history import** — reads all records stored on the device and imports them as HA long-term statistics (hourly buckets)
- **Incremental updates** — subsequent fetches only retrieve new records, preserving battery life
- **Calibrated WME** — uses the device's built-in calibration offsets (O command) and battery-voltage compensation for accurate readings that match the official app
- **Auto-discovery** via Home Assistant Bluetooth integration
- **Manual MAC address entry** as fallback
- **Configurable fetch interval** (default: 7 days; the device records on its own schedule)
- **Multi-device support**

---

## Requirements

- Home Assistant 2024.x or later (uses the `bluetooth` and `recorder` integrations)
- A **connectable** Bluetooth adapter reachable by your HA host. Options:
  - USB Bluetooth dongle on the HA host
  - [ESPHome Bluetooth Proxy](https://esphome.io/components/bluetooth_proxy.html) with `active: true` placed near the sensor — **required for BLE connections** (passive-only proxies such as Shelly BT Gateway cannot establish connections)
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

If a connectable Bluetooth adapter can see the device advertising, a discovery
notification appears automatically in **Settings → Devices & Services**.
Confirm the device, set a friendly name, and optionally change the fetch interval.

### Manual setup

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **Protimeter BLE**
3. Enter the device MAC address (e.g. `00:22:A3:00:C7:57`)
4. Set a friendly name and fetch interval

---

## Sensors & controls

| Entity | Unit | Device class | Notes |
| --- | --- | --- | --- |
| Humidity | % | `humidity` | Relative humidity from most-recent record |
| Temperature | °C | `temperature` | From most-recent record |
| Wood Moisture Equivalent | % | — | Calibrated using device O-command offsets + battery-voltage compensation |
| Battery | % | `battery` | From most-recent record |
| Last reading | — | `timestamp` | When the most-recent record was captured on the device |
| Fetch history | — | button | Trigger an immediate history fetch on demand |

Sensor values reflect the **most-recent record stored on the device**, not a
live reading. The device records hourly; values update each time a fetch completes.
Sensors retain their last known values if a fetch fails — they only show
"unavailable" before the very first successful fetch.

### History graphs

All four measurement sensors are also imported as **HA long-term statistics**,
accessible in the Energy/History dashboard or via a `statistics-graph` card:

```yaml
type: statistics-graph
title: Sydvägg WME
period: day
stat_type: mean
entities:
  - entity: sensor.protimeter_sydvagg_wood_moisture_equivalent
```

---

## ESPHome BLE proxy setup

The Protimeter sensor uses standard BLE GATT connections — it cannot be read by
passive-only adapters. An ESPHome device flashed with the BT proxy component and
placed within ~3 m of the sensor works reliably:

```yaml
# esphome config snippet
bluetooth_proxy:
  active: true
```

Place the proxy within a few metres of the sensor. The HA Bluetooth integration
will automatically route connections through it.

---

## How it works

1. On each scheduled fetch (default: weekly) or when the **Fetch history** button is pressed:
   1. Connect to the device over BLE
   2. Send `C` command → read total record count
   3. Send `O` command → read device calibration offsets (4 slots)
   4. Send `R` command → read new records (full history on first run; incremental with a small overlap on subsequent runs)
   5. Import records into HA long-term statistics (hourly mean/min/max)
   6. Disconnect
2. The most-recent record is shown on the sensor entities.
3. If 3 consecutive fetches fail, a persistent notification appears in HA with the error detail.

The device stores one record per hour internally. A weekly HA fetch therefore
retrieves ~168 records per run and completes in under a minute.

---

## BLE Protocol Summary

Full specification: [PROTOCOL.md](PROTOCOL.md)

| Item | Value |
| --- | --- |
| Advertised service UUID | `00005500-d102-11e1-9b23-00025b00a5a5` |
| Command characteristic | `00005501-d102-11e1-9b23-00025b00a5a5` |
| Count command | Write `C` (0x43) → 7-byte response |
| Calibration command | Write `O` (0x4F) → 4 × 19-byte responses |
| History command | Write `R` + start/end indices + XOR checksum → one 20-byte response per record |
| Humidity formula | `(high×256 + low) / 16384 × 100` |
| Temperature formula | `((high×64) + (low/4)) / 16384 × 165 − 40` |
| WME pipeline | raw → ADC → AdcTable → temp-comp → calibrate (O data) → voltage-comp (battery) |

---

## Project structure

```text
├── custom_components/
│   └── protimeter_ble/
│       ├── __init__.py          # Entry setup/teardown
│       ├── manifest.json        # Integration metadata + BT UUID matcher
│       ├── const.py             # UUIDs, commands, defaults
│       ├── parser.py            # BLE protocol decoding (pure Python, no HA deps)
│       ├── coordinator.py       # DataUpdateCoordinator — BLE connect → read → import
│       ├── config_flow.py       # UI config + options flow
│       ├── sensor.py            # Sensor entities
│       ├── button.py            # Fetch history button
│       └── translations/en.json
├── tests/
│   ├── conftest.py              # HA stub for plain pytest
│   └── test_parser.py          # 33 parser tests using real device bytes
├── scripts/                     # Standalone BLE debug scripts
├── PROTOCOL.md                  # Complete BLE protocol specification
└── todo.txt                     # Development checklist
```

---

## Development

### Running tests

```bash
pip install pytest
pytest tests/
```

Tests use real BLE notification bytes captured from the device and
cross-referenced against the official app. No Home Assistant installation needed.

### Debug scripts

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

python3 scripts/01_ble_scanner.py                          # scan for nearby devices
python3 scripts/02_device_connector.py 00:22:A3:00:C7:57  # dump GATT tree
python3 scripts/05_notification_logger.py 00:22:A3:00:C7:57 30  # log notifications
```

### Reverse engineering

The protocol was reverse-engineered by:

1. Capturing HCI logs from an Android phone (`btsnoop_hci.log`)
2. Analysing logs with `tshark`
3. Decompiling the Android APK with `jadx` and `monodis` (Xamarin/.NET)
4. Extracting byte-parsing formulas from `ProtimeterApp.dll`

Key source: `ProtimeterApp.Helpers.ByteHelper` — `GetHumidityFromLowHighBytes`,
`GetTemperatureFromLowHighBytes`, `GetWmeValue`, `GetCalibratedWme`,
`GetVoltageCompensatedWme`.

---

## License

MIT
