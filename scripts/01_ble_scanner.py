#!/usr/bin/env python3
"""
BLE Device Scanner
Scans for all available BLE devices and displays their information.
"""

import asyncio
import sys
from bleak import BleakScanner


async def scan_devices():
    """Scan for BLE devices and print their information."""
    print("Scanning for BLE devices... (this may take a moment)")
    print("-" * 80)
    
    devices = await BleakScanner.discover(timeout=10.0)
    
    if not devices:
        print("No BLE devices found.")
        return
    
    print(f"Found {len(devices)} device(s):\n")
    
    for device in devices:
        print(f"Device: {device.name or 'Unknown'}")
        print(f"  MAC Address: {device.address}")
        print(f"  RSSI: {device.rssi} dBm")
        
        if device.metadata:
            print("  Advertisement Data:")
            for key, value in device.metadata.items():
                if key == "uuids":
                    print(f"    UUIDs: {value}")
                elif key == "manufacturer_data":
                    print(f"    Manufacturer Data: {value}")
                elif key == "service_data":
                    print(f"    Service Data: {value}")
                elif key == "tx_power":
                    print(f"    TX Power: {value}")
                else:
                    print(f"    {key}: {value}")
        
        print()


def main():
    """Main entry point."""
    try:
        asyncio.run(scan_devices())
    except KeyboardInterrupt:
        print("\n\nScanning interrupted by user.")
        sys.exit(0)
    except Exception as e:
        print(f"Error during scanning: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
