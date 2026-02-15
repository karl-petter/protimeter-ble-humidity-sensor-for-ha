#!/bin/bash
# BLE GATT Explorer using gatttool
# This uses native Bluetooth tools for more reliable device exploration

MAC_ADDRESS="${1:-}"

if [ -z "$MAC_ADDRESS" ]; then
    echo "Usage: $0 <MAC_ADDRESS>"
    echo "Example: $0 00:22:a3:00:c7:57"
    exit 1
fi

echo "Connecting to device: $MAC_ADDRESS"
echo "============================================"
echo ""

# First try to connect and get basic device info
echo "Attempting to connect (10 second timeout)..."
timeout 10 gatttool -b "$MAC_ADDRESS" -I <<EOF
connect
primary
characteristics
quit
EOF

if [ $? -eq 124 ]; then
    echo ""
    echo "Connection timed out"
    exit 1
elif [ $? -ne 0 ]; then
    echo ""
    echo "Connection failed"
    exit 1
fi

echo ""
echo "============================================"
echo "Connection successful!"
