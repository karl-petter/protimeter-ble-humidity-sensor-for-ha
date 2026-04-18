# Protimeter BLE Sensor — Protocol Specification

Reverse-engineered from `ProtimeterBLE.apk` (Xamarin/.NET app, `ProtimeterApp.dll`).  
All field names and constants are taken directly from the decompiled source.

---

## BLE Discovery

The device advertises with service UUID `00005500-d102-11e1-9b23-00025b00a5a5`
(the `COMMAND_SERVICE_ID`). The local name in the scan response is
`Protimeter_` followed by the last 8 hex characters of the MAC address
(e.g. `Protimeter_a300c757` for MAC `00:22:A3:00:C7:57`).

---

## GATT Services and Characteristics

### Custom Command Service

| Constant | UUID |
|---|---|
| `COMMAND_SERVICE_ID` | `00005500-d102-11e1-9b23-00025b00a5a5` |
| `COMMAND_CHARACTERISTIC_ID` | `00005501-d102-11e1-9b23-00025b00a5a5` |

All commands are **written** to `COMMAND_CHARACTERISTIC_ID`.  
All responses come back on the **same characteristic** via notifications or indications.  
Enable notifications on this characteristic before sending any command.

### Standard Battery Service

| Constant | UUID |
|---|---|
| `BATTERY_SERVICE_ID` | `0000180f-0000-1000-8000-00805f9b34fb` |
| `BATTERY_CHARACTERISTIC_ID` | `00002a19-0000-1000-8000-00805f9b34fb` |

Standard BLE Battery Level characteristic — readable directly, returns a single byte 0–100.

### Standard Device Information Service

| Constant | UUID |
|---|---|
| `DEVICE_INFORMATION_SERVICE_ID` | `0000180a-0000-1000-8000-00805f9b34fb` |
| `SERIAL_NUMBER_CHARACTERISTIC_ID` | `00002a24-0000-1000-8000-00805f9b34fb` |

---

## Command Codes

All commands are sent as ASCII bytes to `COMMAND_CHARACTERISTIC_ID`.

| ASCII | Hex | Constant | Description | Payload |
|---|---|---|---|---|
| `S` | `0x53` | `READ_READING_COMMAND_CODE` | Get current sensor reading | Single byte `S` |
| `R` | `0x52` | `READ_HISTORY_COMMAND_CODE` | Read stored history records | 6 bytes (see below) |
| `C` | `0x43` | `READ_NUMBER_OF_RECORDS_COMMAND_CODE` | Get number of stored records | Single byte `C` |
| `O` | `0x4F` | `READ_CALIBRATION_COMMAND_CODE` | Read calibration offset slot | 3 bytes (see below) |
| `L` | `0x4C` | `WRITE_CALIBRATION_COMMAND_CODE` | Write calibration offset | 3 bytes (see below) |
| `T` | `0x54` | `WRITE_REAL_TIME_CLOCK_COMMAND_CODE` | Set device clock | 8 bytes (see below) |
| `F` | `0x46` | `WRITE_FREQUENCY_COMMAND_CODE` | Set recording frequency | 3 bytes |
| `A` | `0x41` | `WRITE_ADVERTISING_RATE_COMMAND_CODE` | Set BLE advertising rate | 4 bytes |
| `I` | `0x49` | `IDENTIFY_COMMAND_CODE` | Identify / pair device | Single byte `I` |
| `D` | `0x44` | `CLEAR_HISTORY_COMMAND_CODE` | Clear stored records | Single byte `D` |

---

## Command Payloads

### `S` — Current Sensor Reading

Write the single byte `0x53`. The device responds with a **12-byte** notification on
`COMMAND_CHARACTERISTIC_ID`.

### `R` — Read History Records

6-byte payload:

```
Byte 0:   0x52  ('R')
Byte 1-2: start index, big-endian uint16
Byte 3-4: end index,   big-endian uint16
Byte 5:   checksum = byte[1] XOR byte[2] XOR byte[3] XOR byte[4]
```

**Record indices are 1-based.** Record 1 is the oldest, record N (= count) is the newest.
Requesting start=0 causes the device to send no data.

Example — fetch all records when count=0x0143 (323):
```
52 01 43 01 43 00
    ^^^^^  ^^^^^
    start   end   checksum = 0x01^0x43^0x01^0x43 = 0x00 ✓
```

Example — fetch records 0x00FB through 0x0104:
```
52 00 FB 01 04 FE
    ^^^^^ ^^^^^
    start  end   checksum = 0x00^0xFB^0x01^0x04 = 0xFE ✓
```

The device sends one **20-byte** notification per record.

### `C` — Record Count

Write the single byte `0x43`. The device responds with a **7-byte** notification:

```
Offset  Length  Field
  0       4     Device MAC address bytes 3–6 (same as in history records)
  4       2     Record count, big-endian uint16
  6       1     XOR checksum of bytes 4–5
```

Example response `a3 00 c7 57 01 42 70`: MAC=a300c757, count=0x0142=322, checksum=0x01^0x42=0x43... (over MAC+count bytes).

### `O` — Read Calibration Offset

3-byte payload:

```
Byte 0:   0x4F  ('O')
Byte 1-2: calibration slot index, big-endian uint16
```

The device responds with a **25-byte** notification (see Calibration Offset Response below).

### `L` — Write Calibration Offset

3-byte payload:

```
Byte 0:   0x4C  ('L')
Byte 1:   offset value (uint8)
Byte 2:   offset value repeated (uint8)
```

### `T` — Set Real-Time Clock

8-byte payload:

```
Byte 0:   0x54  ('T')
Byte 1:   year - 2000  (e.g., 2026 → 0x1A = 26)
Byte 2:   month  (1–12)
Byte 3:   day    (1–31)
Byte 4:   hour   (0–23)
Byte 5:   minute (0–59)
Byte 6:   second (0–59)
Byte 7:   checksum = byte[1] XOR byte[2] XOR byte[3] XOR byte[4] XOR byte[5] XOR byte[6]
```

---

## Response Formats

### Current Reading Response (12 bytes)

Response to command `S`.

```
Offset  Length  Field
  0       4     Unknown / status bytes (possibly MAC fragment or flags)
  4       2     Relative humidity, big-endian uint16
  6       2     Temperature, big-endian, special encoding
  8       2     Raw WME integer, big-endian uint16
 10       1     Battery level, 0–100
 11       1     Unknown
```

### History Record Response (20 bytes)

Each notification in response to command `R`.

```
Offset  Length  Field
  0       4     Device MAC address bytes 3–6 (e.g., 0xA3 0x00 0xC7 0x57)
  4       2     Record ID / sequence number, big-endian uint16
  6       1     Year (2-digit, e.g., 0x1A = 26 → 2026, century from host clock)
  7       1     Month (1–12)
  8       1     Day   (1–31)
  9       1     Hour  (0–23)
 10       1     Minute (0–59)
 11       1     Second (0–59)
 12       2     Relative humidity, big-endian uint16
 14       2     Temperature, big-endian, special encoding
 16       2     Raw WME integer, big-endian uint16
 18       1     Battery level, 0–100
 19       1     Unknown (possibly record checksum)
```

### Calibration Offset Response (25 bytes)

Response to command `O`. Contains a snapshot of the environment at calibration time.

```
Offset  Length  Field
  0       1     Year (2-digit)
  1       1     Month
  2       1     Day
  3       1     Hour
  4       1     Minute
  5       1     Second
  6       2     Relative humidity, big-endian uint16
  8       2     Temperature, big-endian, special encoding
 10       2     Unknown
 12       1     Battery level, 0–100
 13–24          Additional calibration data
```

---

## Sensor Value Decoding

### Helper: `GetIntegerFromHighLowBytes(high, low)`

```python
def get_int(high, low):
    return int(high * 256 + low)
```

### Relative Humidity (%RH)

Source: `ByteHelper.GetHumidityFromLowHighBytes(high, low)`

```python
def decode_rh(high, low):
    return (high * 256 + low) / 16384.0 * 100.0
```

Verification with capture data (record 0x00FB):
- bytes[12:14] = `0x30 0x60` → `(48*256 + 96) / 16384 * 100` = `12384 / 16384 * 100` = **75.6 %RH** ✓

### Temperature (°C)

Source: `ByteHelper.GetTemperatureFromLowHighBytes(high, low)`

This is a Sensirion-style 14-bit ADC encoding (HDC/SHT family), stored in the top 14 bits of a 16-bit big-endian value:

```python
def decode_temperature(high, low):
    raw = high * 64.0 + low / 4.0        # top 14 bits: (high<<6) | (low>>2)
    return (raw / 16384.0) * 165.0 - 40.0
```

Verification with capture data (record 0x00FB):
- bytes[14:16] = `0x49 0xA0` → `(73*64 + 160/4) / 16384 * 165 - 40` = `4712 / 16384 * 165 - 40` = **7.45 °C** ✓

### Battery Level

Source: `ByteHelper.GetSensorReadingFromBytes` / `GetSensorReadingFromRecordBytes`

```python
def decode_battery(b):
    return int(b)    # direct, 0–100 %
```

---

## WME (Wood Moisture Equivalent) Decoding

WME requires calibration data from the device and goes through a 4-stage pipeline.
For simple monitoring, skip WME and rely on %RH.

### Stage 1: Raw integer → ADC value

Source: `ByteHelper.GetWmeAdcValue(wme)`

```python
def wme_to_adc(raw_int):
    return round(raw_int / 1000.0 * 758.51851851851848)
```

### Stage 2: ADC value → Raw WME via AdcTable lookup

Source: `ByteHelper.GetRawWmeFromAdc(adc)` + `AdcTable`

Linear interpolation using the following lookup table. Find the entry where
`XStart <= adc < XEnd`, then interpolate:

```python
# (XStart, XEnd, YStart, YEnd)
ADC_TABLE = [
    (0,    32,   450,   516),
    (32,   64,   516,   603),
    (64,   96,   603,   686),
    (96,   128,  686,   772),
    (128,  160,  772,   853),
    (160,  192,  853,   936),
    (192,  224,  936,   1022),
    (224,  256,  1022,  1111),
    (256,  288,  1111,  1233),
    (288,  320,  1233,  1357),
    (320,  352,  1357,  1496),
    (352,  384,  1496,  1637),
    (384,  416,  1637,  1793),
    (416,  448,  1793,  1951),
    (448,  480,  1951,  2120),
    (480,  512,  2120,  2290),
    (512,  544,  2290,  2496),
    (544,  576,  2496,  2704),
    (576,  608,  2704,  3035),
    (608,  640,  3035,  3500),
    (640,  672,  3500,  4094),
    (672,  704,  4094,  4875),
    (704,  736,  4875,  5717),
    (736,  768,  5717,  6559),
    (768,  800,  6559,  7526),
    (800,  832,  7526,  8492),
    (832,  864,  8492,  9724),
    (864,  896,  9724,  10956),
    (896,  928,  10956, 11000),
    (928,  960,  11000, 11000),
    (960,  992,  11000, 14000),
    (992,  1024, 14000, 14000),
    (1024, 9999, 14000, 99999),
]

def adc_to_raw_wme(adc):
    for xstart, xend, ystart, yend in ADC_TABLE:
        if xstart <= adc < xend:
            return round((yend - ystart) / (xend - xstart) * (adc - xstart) + ystart)
    return 0
```

### Stage 3: Temperature compensation

Source: `ByteHelper.GetTemperatureCompensatedWmeValue(raw_wme, temp_celsius)`

```python
def temperature_compensate_wme(raw_wme, temp_c):
    NOMINAL_TEMP   = 2200   # 22.00 °C × 100
    LOW_THRESHOLD  = 1300
    HIGH_THRESHOLD = 2500
    LOW_FACTOR     = -3
    HIGH_FACTOR    = -6

    v = float(raw_wme)
    if v > 2500:
        v = (v - HIGH_THRESHOLD) * HIGH_FACTOR + (HIGH_THRESHOLD - LOW_THRESHOLD) * LOW_FACTOR
    else:
        v = (v - LOW_THRESHOLD) * LOW_FACTOR

    temp_delta = temp_c * 100 - NOMINAL_TEMP   # deviation from 22 °C
    v = v * temp_delta / 65536.0
    return round(raw_wme + v)
```

### Stage 4: Calibration offset (device-specific)

Source: `ByteHelper.GetCalibratedWme(temp_compensated_wme, calibration_offsets)`

Calibration offsets are fetched from the device using command `O` and are specific to
each sensor unit. They are applied via piecewise linear interpolation using a lookup table
derived from the `CalibrationOffsetTable` in combination with the device's stored offsets.

The nominal (uncalibrated) fallback is to divide by 100:

```python
def calibrate_wme(temp_comp_wme, calibration_offsets=None):
    if not calibration_offsets:
        return temp_comp_wme / 100.0    # nominal fallback, approximate
    # ... device-specific piecewise interpolation
```

### Stage 5: Battery voltage compensation

Source: `ByteHelper.GetVoltageCompensatedWme(battery_int, calibrated_wme)`

Uses the `BatteryLevelTable` (indexed by voltage/battery %) to apply a piecewise
correction based on the closest matching battery level entry. Thresholds at H2o9 (9%),
H2o13 (13.2%), H2o18 (18.2%), H2o26 (26%), H2o40 (40%) WME breakpoints.

### Stage 6: Clamp

```python
def get_wme_value(raw_int, temp_c, battery, calibration_offsets=None):
    adc    = wme_to_adc(raw_int)
    raw    = adc_to_raw_wme(adc)
    t_comp = temperature_compensate_wme(raw, temp_c)
    cal    = calibrate_wme(t_comp, calibration_offsets)
    # voltage compensation omitted — requires BatteryLevelTable implementation
    if cal < 6:
        return 0.0
    return min(cal, 100.0)
```

---

## Typical Connection Flow

```
1. Scan for devices advertising ADVERTISED_SERVICE_ID
   00005500-d102-11e1-9b23-00025b00a5a5

2. Connect to device

3. Discover services, find COMMAND_SERVICE_ID
   00005500-d102-11e1-9b23-00025b00a5a5

4. Enable notifications on COMMAND_CHARACTERISTIC_ID
   00005501-d102-11e1-9b23-00025b00a5a5

5. (Optional) Sync device clock:
   Write T payload → device responds with confirmation

6. (Optional) Fetch calibration offsets for accurate WME:
   For each slot index i = 0, 1, 2, ...:
     Write O 00 [i] → receive CalibrationOffset response

7. Fetch current reading:
   Write S → receive 12-byte SensorReading response

8. Fetch history:
   Write C → receive 7-byte response; extract count N from bytes [4:6]
   Write R [0x00] [0x01] [hi(N)] [lo(N)] [checksum] → receive N × 20-byte records
   (indices are 1-based: start=1, end=N)

9. Disconnect
```

---

## Notes

- **Year encoding**: The device stores only the 2-digit year (e.g., `0x1A` = 26).
  The app combines this with the current century from the host's system clock to get
  the full 4-digit year (e.g., "20" + "26" = 2026).

- **WME vs %RH**: For typical humidity monitoring use cases (cellar walls, wood moisture),
  %RH decoded from the current reading command `S` is sufficient and requires no
  calibration data. WME is for wood-specific moisture content measurement.

- **Battery in current reading vs history**: In the 12-byte current reading response,
  battery is at byte offset 10. In the 20-byte history record, battery is at offset 18.

- **MAC in history records**: Bytes 0–3 of each history record are the last 4 bytes of
  the device MAC address (e.g., MAC `00:22:A3:00:C7:57` → `0xA3 0x00 0xC7 0x57`).
  This allows multi-device responses to be de-multiplexed.
