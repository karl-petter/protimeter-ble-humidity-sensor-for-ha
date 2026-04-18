"""Constants for the Protimeter BLE integration."""

DOMAIN = "protimeter_ble"

# ── BLE identifiers ────────────────────────────────────────────────────────────

# UUID the device puts in its advertisement packets (same as COMMAND_SERVICE_UUID)
ADVERTISED_SERVICE_UUID = "00005500-d102-11e1-9b23-00025b00a5a5"

# GATT service containing all Protimeter-specific characteristics
COMMAND_SERVICE_UUID = "00005500-d102-11e1-9b23-00025b00a5a5"

# Characteristic used for both writing commands and receiving notifications.
# UUID confirmed from APK (CharacteristicIds) and live GATT dump (handle 29, props write+notify).
COMMAND_CHAR_UUID = "00005501-d102-11e1-9b23-00025b00a5a5"
NOTIFY_CHAR_UUID  = COMMAND_CHAR_UUID   # same characteristic — kept as alias

# Standard BLE Battery Level characteristic (read directly, no command needed)
BATTERY_SERVICE_UUID = "0000180f-0000-1000-8000-00805f9b34fb"
BATTERY_CHAR_UUID    = "00002a19-0000-1000-8000-00805f9b34fb"

# Standard Device Information
DEVICE_INFO_SERVICE_UUID  = "0000180a-0000-1000-8000-00805f9b34fb"
SERIAL_NUMBER_CHAR_UUID   = "00002a24-0000-1000-8000-00805f9b34fb"

# ── Command bytes (ASCII) ──────────────────────────────────────────────────────

CMD_READ_CURRENT  = b"S"   # → 12-byte SensorReading notification (not used in integration)
CMD_READ_COUNT    = b"C"   # → 2-byte uint16 big-endian: total number of stored records
CMD_READ_HISTORY  = b"R"   # + 5 bytes (start/end indices + XOR checksum) → 20 bytes per record
CMD_READ_CALIB    = b"O"   # + 2 bytes (slot index)
CMD_WRITE_CALIB   = b"L"   # + 2 bytes (offset value × 2)
CMD_WRITE_CLOCK   = b"T"   # + 7 bytes (yy mm dd hh mm ss + XOR checksum)
CMD_WRITE_FREQ    = b"F"   # + 2 bytes
CMD_WRITE_ADV     = b"A"   # + 3 bytes
CMD_IDENTIFY      = b"I"
CMD_CLEAR_HISTORY = b"D"

# ── Config entry keys ──────────────────────────────────────────────────────────

CONF_ADDRESS             = "address"
CONF_FETCH_INTERVAL_DAYS = "fetch_interval_days"
CONF_LAST_RECORD_ID      = "last_record_id"   # persisted in entry.data after each fetch

# ── Defaults ───────────────────────────────────────────────────────────────────

DEFAULT_FETCH_INTERVAL_DAYS = 7   # weekly
DEFAULT_NAME                = "Protimeter"

# Number of records to re-read on each incremental fetch to verify no gaps
HISTORY_OVERLAP = 5

# ── Timeouts ───────────────────────────────────────────────────────────────────

BLE_CONNECT_TIMEOUT_S  = 20
BLE_RESPONSE_TIMEOUT_S = 15    # timeout for a single command response (C command)

# ── Expected response sizes ────────────────────────────────────────────────────

CURRENT_READING_LEN = 12
HISTORY_RECORD_LEN  = 20
