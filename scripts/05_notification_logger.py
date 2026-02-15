#!/usr/bin/env python3
"""
Protimeter Notification Logger
Subscribes to the notification characteristic and logs timestamped payloads to a file.

Usage:
  python3 scripts/05_notification_logger.py <MAC_ADDRESS> [duration_seconds]

Example:
  python3 scripts/05_notification_logger.py 00:22:a3:00:c7:57 30
"""

import asyncio
import sys
from datetime import datetime, timezone
from bleak import BleakClient

# Notification characteristic UUID (from GATT dump)
NOTIFY_UUID = "00001014-d102-11e1-9b23-00025b00a5a5"

async def run(mac, duration=30, out_file='/tmp/protimeter_notifications.log'):
    async with BleakClient(mac) as client:
        # open file
        with open(out_file, 'a') as f:
            def callback(sender: int, data: bytearray):
                ts = datetime.now(timezone.utc).astimezone().isoformat()
                hexdata = data.hex()
                try:
                    ascii = data.decode('utf-8', errors='ignore')
                except Exception:
                    ascii = ''
                line = f"{ts} | {sender} | {hexdata} | {ascii}\n"
                f.write(line)
                f.flush()
                print(line, end='')

            print(f"Connecting to {mac}...")
            try:
                await client.connect()
            except Exception as e:
                # If backend reports already connected, try to disconnect and reconnect
                from bleak import BleakError
                if isinstance(e, BleakError) and "already connected" in str(e):
                    try:
                        print("Client already connected — attempting disconnect then reconnect...")
                        await client.disconnect()
                        await asyncio.sleep(1)
                        await client.connect()
                    except Exception as e2:
                        print(f"Reconnect failed: {e2}")
                        return
                else:
                    print(f"Connection error: {e}")
                    return
            if not client.is_connected:
                print("Failed to connect")
                return
            print("Connected — subscribing to notifications...")

            try:
                await client.start_notify(NOTIFY_UUID, callback)
            except Exception as e:
                print(f"Failed to start notify on {NOTIFY_UUID}: {e}")
                await client.disconnect()
                return

            print(f"Logging notifications to {out_file} for {duration} seconds...")
            try:
                await asyncio.sleep(duration)
            except asyncio.CancelledError:
                pass

            await client.stop_notify(NOTIFY_UUID)
            await client.disconnect()
            print("Done.")


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/05_notification_logger.py <MAC_ADDRESS> [duration_seconds]")
        sys.exit(1)
    mac = sys.argv[1]
    duration = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    asyncio.run(run(mac, duration))


if __name__ == '__main__':
    main()
