Protimeter BLE Reverse Engineering - Project Notes
==================================================

Device Information
------------------
MAC Address: 00:22:a3:00:c7:57
Device Type: Protimeter Humidity Sensor
Quantity: 2 devices


Current Status
==============

✓ Project Setup Complete:
  - Git repository initialized with GitHub remote
  - Python virtual environment created
  - BLE libraries installed (bleak 2.1.1, pyyaml)
  - BLE scanner script created (01_ble_scanner.py)
  - Device connector script created (02_device_connector.py)

⚠ Bluetooth Adapter Issue:
  - Experiencing timeouts when connecting to devices via bleak
  - Scanner hangs during discovery in some cases
  - Possible causes:
    * Multiple concurrent BLE operations
    * Bluetooth adapter needing restart/reconfiguration
    * dbus-fast compatibility issues
    * System resource constraints


Available Tools
===============

1. BLE Device Scanner
   Location: scripts/01_ble_scanner.py
   Usage: python3 scripts/01_ble_scanner.py
   Purpose: List all available BLE devices with friendly names and MAC addresses
   Status: Working (after restart)

2. Device GATT Explorer  
   Location: scripts/02_device_connector.py
   Usage: python3 scripts/02_device_connector.py <MAC_ADDRESS>
   Example: python3 scripts/02_device_connector.py 00:22:a3:00:c7:57
   Purpose: Connect to device and enumerate all services, characteristics, and values
   Status: Ready but having connectivity issues


Next Steps for Troubleshooting
==============================

1. Check Bluetooth Adapter Status:
   - bluetoothctl status
   - hciconfig -a
   - systemctl status bluetooth

2. Clear Bluetooth Cache and Restart:
   - sudo systemctl stop bluetooth
   - sudo rm -rf /var/lib/bluetooth/*
   - sudo systemctl start bluetooth
   - Wait 10 seconds before attempting connections

3. Test with Native Commands First:
   - bluetoothctl scan on / scan off
   - bluetoothctl connect <mac>
   - gatttool commands

4. If issues persist:
   - Upgrade bleak: pip install --upgrade bleak
   - Try downgrading: pip install bleak==0.20.0
   - Check Raspberry Pi power supply (BT requires adequate power)
   - Reduce other BLE operations that might interfere


Once Connection Works
====================

The device explorer will:
1. Connect to the device
2. List all GATT services with UUIDs
3. Enumerate characteristics under each service
4. Read values from characteristics with read permission
5. Display raw hex, bytes, and ASCII representation of values

Example output will help identify:
- Which characteristic contains humidity data
- Data format (integer, float, custom encoding)
- Refresh rate/notification patterns
- Battery status characteristic (if present)


Files Structure
===============

scripts/
├── 01_ble_scanner.py          - BLE device discovery
├── 02_device_connector.py     - GATT exploration
└── 03_packet_analyzer.py      - (TODO) Real-time packet capture

protimeter/
└── (TODO) Python library for device communication

custom_component/
└── (TODO) Home Assistant integration

requirements.txt               - Python dependencies
README.md                     - Project overview
todo.txt                      - Phase checklists
PROJECT_NOTES.md              - This file


Useful References
=================

- Bluetooth GATT UUIDs: https://www.bluetooth.com/specifications/gatt-services-summary/
- Bleak Documentation: https://bleak.readthedocs.io/
- BLE Data Format Guide: https://en.wikipedia.org/wiki/List_of_Bluetooth_profiles_and_services
- Raspberry Pi Bluetooth: https://www.raspberrypi.com/documentation/accessories/bluetooth.html
