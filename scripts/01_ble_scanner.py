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
    print("Scanning for BLE devices... (scanning for 10 seconds)")
    print("-" * 100)
    
    try:
        # Use the static discover method
        devices = await BleakScanner.discover(timeout=10.0, return_adv=False)
        
        if not devices:
            print("No BLE devices found.")
            return
        
        print(f"\nFound {len(devices)} device(s):\n")
        
        for device in devices:
            print(f"Device: {device.name or 'Unknown'}")
            print(f"  MAC Address: {device.address}")
            
            # Try to display device details
            if hasattr(device, 'details'):
                details = device.details
                print(f"  Details: {details}")
            
            print()
    
    except Exception as e:
        print(f"Error during scanning: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()


def main():
    """Main entry point."""
    try:
        asyncio.run(scan_devices())
    except KeyboardInterrupt:
        print("\n\nScanning interrupted by user.")
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
