#!/usr/bin/env python3
"""
BLE Scanner with file output for debugging
"""

import asyncio
import sys
from bleak import BleakScanner

async def scan_devices():
    """Scan for BLE devices and write to file."""
    output_file = "/tmp/ble_scan_result.txt"
    
    with open(output_file, "w") as f:
        f.write("Starting BLE scan...\n")
        f.flush()
        
        try:
            print("Scanning for devices...", file=sys.stderr)
            scanner = BleakScanner()
            devices = await scanner.discover(timeout=15.0)
            
            f.write(f"Found {len(devices)} devices\n\n")
            f.flush()
            
            target_mac = "00:22:A3:00:C7:57"
            found_target = False
            
            for device in devices:
                device_line = f"{device.name or 'Unknown':30} | {device.address}\n"
                f.write(device_line)
                f.flush()
                
                if device.address.upper() == target_mac:
                    found_target = True
                    f.write(f"  ^^^ TARGET DEVICE FOUND ^^^\n")
                    f.flush()
            
            f.write(f"\nTarget device ({target_mac}) found: {found_target}\n")
            f.flush()
            
        except Exception as e:
            f.write(f"Error: {e}\n")
            f.write(f"Exception type: {type(e).__name__}\n")
            import traceback
            f.write(traceback.format_exc())
            f.flush()
    
    # Print result file location
    print(f"Results written to {output_file}")
    with open(output_file, "r") as f:
        print(f.read())


if __name__ == "__main__":
    asyncio.run(scan_devices())
