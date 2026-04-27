#!/bin/bash
set -e

# Usage: ./deploy.sh <user> <host>
# Example: ./deploy.sh hassio homeassistant.local
if [ -z "$1" ] || [ -z "$2" ]; then
  echo "Usage: $0 <user> <host>"
  exit 1
fi

USER="$1"
HOST_ARG="$2"
HOST="$USER@$HOST_ARG"
REMOTE_DIR="/config/custom_components/protimeter_ble"

echo "==> Creating remote directories..."
ssh -o BatchMode=yes "$HOST" "sudo mkdir -p $REMOTE_DIR/translations && sudo chmod 777 $REMOTE_DIR/translations $REMOTE_DIR"

echo "==> Syncing files..."
rsync -av --exclude='__pycache__' --exclude='.DS_Store' \
  custom_components/protimeter_ble/ \
  "$HOST:$REMOTE_DIR/"

echo "==> Done! Reload the integration in HA: Settings → Devices & Services → Protimeter BLE → (3 dots) → Reload."
