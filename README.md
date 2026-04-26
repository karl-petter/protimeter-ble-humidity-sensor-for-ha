# Protimeter BLE — Home Assistant Integration

A Home Assistant custom integration for the **[Protimeter BLE humidity sensor](https://www.protimeter.com/products/protimeter-bluetooth-le-hygrometer/)**.

Exposes humidity, temperature, Wood Moisture Equivalent (WME), battery level, and
last-reading timestamp as HA sensor entities, with full long-term history imported
as HA statistics for graphing and automations.

---

## Features

- **5 sensor entities** per device: Humidity (%RH), Temperature (°C), WME (%), Battery (%), Last reading (timestamp)
- **Full history import** — reads all records stored on the device and imports them as HA long-term statistics (hourly buckets)
- **Incremental updates** — subsequent fetches only retrieve new records, preserving battery life
- **Calibrated WME** — uses the device's built-in calibration offsets and battery-voltage compensation for accurate readings matching the official app
- **Auto-discovery** via Home Assistant Bluetooth integration
- **Manual MAC address entry** as fallback
- **Configurable fetch interval** (default: 7 days)
- **Multi-device support**

---

## Requirements

- Home Assistant 2024.x or later
- A **connectable** Bluetooth adapter reachable by your HA host:
  - USB Bluetooth dongle on the HA host, or
  - [ESPHome Bluetooth Proxy](https://esphome.io/components/bluetooth_proxy.html) with `active: true` placed near the sensor
  
  > **Note:** Passive-only adapters (e.g. Shelly BT Gateway) cannot establish BLE connections and will not work.

- Protimeter BLE humidity sensor

---

## Installation

### HACS (recommended)

1. Open HACS → **Integrations** → ⋮ → **Custom repositories**
2. Add this repository URL, category **Integration**
3. Search for **Protimeter BLE** and install
4. Restart Home Assistant

### Manual

1. Copy `custom_components/protimeter_ble/` into your HA config directory:

   ```text
   <config>/custom_components/protimeter_ble/
   ```

2. Restart Home Assistant

---

## Setup

### Auto-discovery

If a connectable Bluetooth adapter can see the device advertising, a discovery
notification appears in **Settings → Devices & Services**. Confirm the device
and optionally set a friendly name and fetch interval.

### Manual setup

1. **Settings → Devices & Services → Add Integration**
2. Search for **Protimeter BLE**
3. Enter the device MAC address (e.g. `AA:BB:CC:DD:EE:FF`)
4. Set a friendly name and fetch interval

---

## Sensors & controls

| Entity | Unit | Device class | Notes |
| --- | --- | --- | --- |
| Humidity | % | `humidity` | From most-recent stored record |
| Temperature | °C | `temperature` | From most-recent stored record |
| Wood Moisture Equivalent | % | — | Calibrated using device O-command offsets + battery-voltage compensation |
| Battery | % | `battery` | From most-recent stored record |
| Last reading | — | `timestamp` | When the most-recent record was captured on the device |
| Fetch history | — | button | Trigger an immediate history fetch |

Sensor values reflect the **most-recent record stored on the device**, not a live
reading. The device records hourly; values update each time a fetch completes.
Sensors retain their last known values if a fetch fails.

---

## History graphs

All four measurement sensors are imported as **HA long-term statistics**, viewable
with a `statistics-graph` card:

```yaml
type: statistics-graph
title: Basement South — WME
period: day
stat_type: mean
entities:
  - entity: sensor.protimeter_basement_south_wood_moisture_equivalent
```

---

## ESPHome BLE proxy

The Protimeter sensor uses GATT connections — passive-only Bluetooth adapters
cannot be used. An ESPHome device with the BT proxy component works reliably:

```yaml
bluetooth_proxy:
  active: true
```

Place it within a few metres of the sensor. HA will route connections through it
automatically.

---

## How it works

On each scheduled fetch (default: weekly) or when **Fetch history** is pressed:

1. Connect to the device over BLE
2. `C` command → read total record count
3. `O` command → read 4 calibration offset slots
4. `R` command → read new records (full history on first run; incremental thereafter)
5. Import records into HA long-term statistics (hourly mean/min/max)
6. Disconnect

The device stores one record per hour. A weekly fetch retrieves ~168 records and
completes in under a minute.

If 3 consecutive fetches fail a persistent notification appears in HA with the
error detail and advice. It clears automatically when the next fetch succeeds.

---

## Further reading

- [BLE Protocol Specification](docs/PROTOCOL.md)
- [Contributing / Developer Guide](docs/CONTRIBUTING.md)
- [Reverse Engineering Notes](docs/REVERSE_ENGINEERING.md)

---

## License

MIT
