#!/usr/bin/env python3
"""
BLE Device Connector and GATT Explorer
Connects to a specific BLE device and explores its GATT structure.
"""

import asyncio
import sys
from bleak import BleakClient


async def explore_device(mac_address):
    """Connect to device and explore GATT structure."""
    print(f"Connecting to device {mac_address}...")
    print(f"Timeout: 15 seconds")
    print("-" * 100)
    
    client = BleakClient(mac_address)
    
    try:
        # Try to connect with timeout
        try:
            await asyncio.wait_for(client.connect(), timeout=15)
        except asyncio.TimeoutError:
            print("Connection timed out after 15 seconds")
            return
        except Exception as e:
            print(f"Connection error: {e}")
            return
            
        print(f"✓ Connected to {client.address}")
        print()
        
        # Get all services
        services = await client.get_services()
        print(f"Found {len(services)} service(s):\n")
        
        for service in services:
            print(f"Service: {service.uuid}")
            print(f"  Description: {service.description if hasattr(service, 'description') else 'N/A'}")
            
            # Get all characteristics for this service
            characteristics = service.characteristics
            print(f"  Characteristics ({len(characteristics)}):")
            
            for char in characteristics:
                print(f"    - {char.uuid}")
                print(f"        Properties: {char.properties}")
                
                # Try to read the characteristic if it has read permission
                if "read" in char.properties:
                    try:
                        value = await client.read_gatt_char(char.uuid)
                        print(f"        Value (hex): {value.hex()}")
                        print(f"        Value (bytes): {value}")
                        # Try to decode as string if possible
                        try:
                            print(f"        Value (ASCII): {value.decode('utf-8', errors='ignore')}")
                        except:
                            pass
                    except Exception as e:
                        print(f"        Value: [Error reading - {e}]")
                
                # List descriptors
                if char.descriptors:
                    print(f"        Descriptors:")
                    for descriptor in char.descriptors:
                        print(f"          - {descriptor.uuid}")
                
                print()
            
            print()
    
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
    
    finally:
        # Disconnect
        if client.is_connected:
            await client.disconnect()


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python3 02_device_connector.py <MAC_ADDRESS>")
        print("Example: python3 02_device_connector.py 00:22:a3:00:c7:57")
        sys.exit(1)
    
    mac_address = sys.argv[1]
    
    if not _is_valid_mac(mac_address):
        print(f"Invalid MAC address: {mac_address}", file=sys.stderr)
        sys.exit(1)
    
    try:
        asyncio.run(explore_device(mac_address))
    except KeyboardInterrupt:
        print("\n\nConnection interrupted by user.")
        sys.exit(0)


def _is_valid_mac(mac):
    """Check if MAC address is valid."""
    parts = mac.split(':')
    if len(parts) != 6:
        return False
    for part in parts:
        if len(part) != 2:
            return False
        try:
            int(part, 16)
        except ValueError:
            return False
    return True


if __name__ == "__main__":
    main()
