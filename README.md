# Protimeter BLE Humidity Sensor - Home Assistant Integration

This project aims to reverse engineer the Protimeter humidity sensor BLE protocol and create a Home Assistant custom integration for it.

## Project Status

Currently in **Phase 1: BLE Discovery & Analysis**

## Prerequisites

- Raspberry Pi (or any Linux system with Bluetooth support)
- Python 3.8+
- pip

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/karl-petter/protimeter-ble-humidity-sensor-for-ha.git
cd protimeter-ble-humidity-sensor-for-ha
```

### 2. Create and activate virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

## Usage

### Scan for BLE Devices

To discover all available BLE devices:

```bash
python3 scripts/01_ble_scanner.py
```

This will display all discoverable BLE devices with their:
- Friendly name
- MAC address
- Signal strength (RSSI)
- UUIDs and other advertisement data

### Connect to Device

(To be implemented - Phase 2)

## Project Structure

```
├── scripts/
│   ├── 01_ble_scanner.py          # Scan for available BLE devices
│   ├── 02_device_connector.py     # (WIP) Connect and explore device
│   └── 03_packet_analyzer.py      # (WIP) Analyze BLE packets
├── protimeter/
│   └── (WIP) Python library for device communication
├── custom_component/
│   └── (WIP) Home Assistant integration
├── requirements.txt               # Python dependencies
├── todo.txt                      # Project tasks and status
└── README.md                     # This file
```

## Resources

- [Bleak - Python BLE Library](https://github.com/hynek/bleak)
- [Bluetooth GATT Overview](https://www.bluetooth.com/specifications/gatt-overview/)
- [Home Assistant Custom Components](https://developers.home-assistant.io/docs/creating_integration_manifest/)

## License

TBD

## Notes

- This is a reverse engineering project
- Information about the Protimeter device protocol will be documented as discovered
