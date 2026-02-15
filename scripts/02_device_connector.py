#!/usr/bin/env python3
"""
BLE Device Connector - Simpler approach with file output
"""

import asyncio
import sys
from bleak import BleakClient


async def connect_and_explore(mac_address):
    """Connect to device and explore GATT."""
    output_file = f"/tmp/{mac_address.replace(':', '_')}_gatt.txt"
    
    with open(output_file, "w") as f:
        f.write(f"Connecting to {mac_address}...\n")
        f.write("=" * 100 + "\n\n")
        f.flush()
        
        try:
            f.write("Creating client...\n")
            f.flush()
            
            client = BleakClient(mac_address)
            
            f.write("Calling connect()...\n")
            f.flush()
            
            try:
                # Try to connect with timeout
                f.write("Waiting for connection (20 second timeout)...\n")
                f.flush()
                
                await asyncio.wait_for(client.connect(), timeout=20)
                
                f.write(f"✓ Connected!\n\n")
                f.flush()
            except asyncio.TimeoutError:
                f.write("✗ Connection timeout (20 seconds exceeded)\n")
                f.flush()
                return
            except Exception as e:
                f.write(f"✗ Connection error: {e}\n")
                f.flush()
                return
            
            # Get services
            try:
                f.write("Getting services...\n")
                f.flush()
                
                # Perform service discovery (handle different bleak versions)
                if hasattr(client, "get_services"):
                    try:
                        services = await client.get_services()
                    except TypeError:
                        # Some bleak versions expose get_services as a regular method
                        services = client.get_services()
                else:
                    # Fallback: client.services may be populated after connect
                    services = client.services

                service_list = list(services)
                f.write(f"\nFound {len(service_list)} services:\n\n")
                f.flush()
                
                for service in service_list:
                    f.write(f"Service: {service.uuid}\n")
                    f.write(f"  Handle: {service.handle}\n")
                    f.write(f"  Characteristics: {len(service.characteristics)}\n\n")
                    f.flush()
                    
                    for char in service.characteristics:
                        f.write(f"    Characteristic: {char.uuid}\n")
                        f.write(f"      Handle: {char.handle}\n")
                        f.write(f"      Properties: {char.properties}\n")
                        f.flush()
                        
                        # Try to read
                        if "read" in char.properties:
                            try:
                                value = await client.read_gatt_char(char.uuid)
                                f.write(f"      Value (hex): {value.hex()}\n")
                                f.write(f"      Value (len): {len(value)} bytes\n")
                                if len(value) <= 32:
                                    try:
                                        ascii_val = value.decode('utf-8', errors='ignore').replace('\x00', '')
                                        if ascii_val:
                                            f.write(f"      Value (ASCII): {ascii_val}\n")
                                    except:
                                        pass
                                f.flush()
                            except Exception as e:
                                f.write(f"      Value: [Error - {e}]\n")
                                f.flush()
                        
                        # List descriptors
                        if char.descriptors:
                            f.write(f"      Descriptors:\n")
                            for desc in char.descriptors:
                                f.write(f"        - {desc.uuid}\n")
                            f.flush()
                        
                        f.write("\n")
                        f.flush()
            
            except Exception as e:
                f.write(f"✗ Error exploring GATT: {e}\n")
                import traceback
                f.write(traceback.format_exc())
                f.flush()
        
        except Exception as e:
            f.write(f"✗ Fatal error: {e}\n")
            import traceback
            f.write(traceback.format_exc())
            f.flush()
        
        finally:
            try:
                if client.is_connected:
                    await client.disconnect()
                    f.write("\n✓ Disconnected\n")
                    f.flush()
            except:
                pass
    
    # Print the output file
    print(f"Results written to {output_file}\n")
    with open(output_file, "r") as f:
        content = f.read()
        print(content)


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 02_device_connector.py <MAC_ADDRESS>")
        print("Example: python3 02_device_connector.py 00:22:a3:00:c7:57")
        sys.exit(1)
    
    mac_address = sys.argv[1]
    asyncio.run(connect_and_explore(mac_address))


if __name__ == "__main__":
    main()
