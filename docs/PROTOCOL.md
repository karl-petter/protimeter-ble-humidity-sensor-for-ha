# Protimeter BLE Sensor — Protocol Specification

Reverse-engineered from `ProtimeterBLE.apk` (Xamarin/.NET, `ProtimeterApp.dll`).
All field names and constants are taken from the decompiled source.
See [REVERSE_ENGINEERING.md](REVERSE_ENGINEERING.md) for methodology.

---

## BLE Discovery

The device advertises with service UUID `00005500-d102-11e1-9b23-00025b00a5a5`
(`COMMAND_SERVICE_ID`). The local name in the scan response is `Protimeter_`
followed by the last 8 hex characters of the MAC address
(e.g. `Protimeter_a300c757` for MAC `00:22:A3:00:C7:57`).

---

## GATT Services and Characteristics

### Custom Command Service

| Constant | UUID |
| --- | --- |
| `COMMAND_SERVICE_ID` | `00005500-d102-11e1-9b23-00025b00a5a5` |
| `COMMAND_CHARACTERISTIC_ID` | `00005501-d102-11e1-9b23-00025b00a5a5` |

All commands are **written** to `COMMAND_CHARACTERISTIC_ID`.
All responses arrive on the **same characteristic** via notifications.
Enable notifications before sending any command.

### Standard Battery Service

| Constant | UUID |
| --- | --- |
| `BATTERY_SERVICE_ID` | `0000180f-0000-1000-8000-00805f9b34fb` |
| `BATTERY_CHARACTERISTIC_ID` | `00002a19-0000-1000-8000-00805f9b34fb` |

Readable directly; returns a single byte 0–100.

### Standard Device Information Service

| Constant | UUID |
| --- | --- |
| `DEVICE_INFORMATION_SERVICE_ID` | `0000180a-0000-1000-8000-00805f9b34fb` |
| `SERIAL_NUMBER_CHARACTERISTIC_ID` | `00002a24-0000-1000-8000-00805f9b34fb` |

---

## Command Codes

All commands are sent as ASCII bytes to `COMMAND_CHARACTERISTIC_ID`.

| ASCII | Hex | Constant | Description |
| --- | --- | --- | --- |
| `S` | `0x53` | `READ_READING_COMMAND_CODE` | Get current sensor reading |
| `R` | `0x52` | `READ_HISTORY_COMMAND_CODE` | Read stored history records |
| `C` | `0x43` | `READ_NUMBER_OF_RECORDS_COMMAND_CODE` | Get number of stored records |
| `O` | `0x4F` | `READ_CALIBRATION_COMMAND_CODE` | Read all calibration slots |
| `L` | `0x4C` | `WRITE_CALIBRATION_COMMAND_CODE` | Write calibration offset |
| `T` | `0x54` | `WRITE_REAL_TIME_CLOCK_COMMAND_CODE` | Set device clock |
| `F` | `0x46` | `WRITE_FREQUENCY_COMMAND_CODE` | Set recording frequency |
| `A` | `0x41` | `WRITE_ADVERTISING_RATE_COMMAND_CODE` | Set BLE advertising rate |
| `I` | `0x49` | `IDENTIFY_COMMAND_CODE` | Identify / pair device |
| `D` | `0x44` | `CLEAR_HISTORY_COMMAND_CODE` | Clear stored records |

---

## Command Payloads and Responses

### `C` — Record Count

Write the single byte `0x43`. The device responds with a **7-byte** notification:

```
Offset  Length  Field
  0       4     Device MAC address bytes 3–6
  4       2     Record count, big-endian uint16
  6       1     XOR checksum of bytes 4–5
```

Example: `a3 00 c7 57 01 42 43` → MAC=a300c757, count=0x0142=322.

---

### `O` — Read Calibration Offsets

Write the single byte `0x4F`. The device responds with **4 × 19-byte** notifications
(one per calibration slot). The integration waits for all 4.

```
Offset  Length  Field
  0       4     Device MAC address bytes 3–6
  4       1     Calibration slot index (1–4)
  5       8     Timestamp at calibration (not used)
 13       2     Temperature at calibration, same encoding as history records
 15       2     Raw WME integer at calibration, big-endian uint16
 17       2     Reference WME (not used)
```

The `raw_int` and `temperature` values from each slot are used to build the
calibration curve in `GetCalibratedWme` (see WME pipeline, stage 4).

---

### `R` — Read History Records

6-byte payload:

```
Byte 0:   0x52  ('R')
Byte 1-2: start index, big-endian uint16 (1-based)
Byte 3-4: end index,   big-endian uint16 (1-based)
Byte 5:   checksum = byte[1] XOR byte[2] XOR byte[3] XOR byte[4]
```

**Record indices are 1-based.** Record 1 is the oldest, record N (= count) is newest.
Requesting start=0 causes the device to send no data.

The device sends one **20-byte** notification per record (see History Record Response).

Example — fetch all 323 records (count = 0x0143):

```
52 01 43 01 43 00
   -----  -----
   start   end   checksum = 0x01^0x43^0x01^0x43 = 0x00 ✓
```

---

### `S` — Current Sensor Reading

Write the single byte `0x53`. The device responds with a **12-byte** notification
(see Current Reading Response). The integration uses history records (`R` command)
instead of live readings; this command is documented for completeness.

---

### `T` — Set Real-Time Clock

8-byte payload:

```
Byte 0:   0x54  ('T')
Byte 1:   year - 2000  (e.g. 2026 → 0x1A)
Byte 2:   month  (1–12)
Byte 3:   day    (1–31)
Byte 4:   hour   (0–23)
Byte 5:   minute (0–59)
Byte 6:   second (0–59)
Byte 7:   XOR of bytes 1–6
```

---

## Response Formats

### Current Reading Response (12 bytes)

Response to command `S`.

```
Offset  Length  Field
  0       4     Unknown / status bytes
  4       2     Relative humidity, big-endian uint16
  6       2     Temperature, big-endian, 14-bit encoding
  8       2     Raw WME integer, big-endian uint16
 10       1     Battery level, 0–100
 11       1     Unknown
```

### History Record Response (20 bytes)

Each notification in response to command `R`.

```
Offset  Length  Field
  0       4     Device MAC address bytes 3–6
  4       2     Record ID, big-endian uint16 (1-based)
  6       1     Year, 2-digit (e.g. 0x1A = 26 → 2026)
  7       1     Month (1–12)
  8       1     Day   (1–31)
  9       1     Hour  (0–23)
 10       1     Minute (0–59)
 11       1     Second (0–59)
 12       2     Relative humidity, big-endian uint16
 14       2     Temperature, big-endian, 14-bit encoding
 16       2     Raw WME integer, big-endian uint16
 18       1     Battery level, 0–100
 19       1     Unknown (possibly checksum)
```

---

## Sensor Value Decoding

### Relative Humidity (%RH)

Source: `ByteHelper.GetHumidityFromLowHighBytes`

```python
def decode_rh(high, low):
    return (high * 256 + low) / 16384.0 * 100.0
```

### Temperature (°C)

Source: `ByteHelper.GetTemperatureFromLowHighBytes`

Sensirion-style 14-bit encoding stored in the top 14 bits of a big-endian uint16:

```python
def decode_temperature(high, low):
    raw = high * 64.0 + low / 4.0
    return (raw / 16384.0) * 165.0 - 40.0
```

### Battery Level

Direct byte, 0–100 %.

---

## WME (Wood Moisture Equivalent) Decoding

Full 5-stage pipeline. Source: `ByteHelper.GetWmeValue` and helpers.

### Stage 1 — Raw integer → ADC value

Source: `ByteHelper.GetWmeAdcValue`

```python
def wme_to_adc(raw_int):
    return round(raw_int / 1000.0 * 758.51851851851848)
```

### Stage 2 — ADC value → Raw WME via AdcTable

Source: `ByteHelper.GetRawWmeFromAdc` + `AdcTable`

Piecewise linear interpolation. Find the row where `XStart <= adc < XEnd`:

```python
ADC_TABLE = [  # (XStart, XEnd, YStart, YEnd)
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
    for xs, xe, ys, ye in ADC_TABLE:
        if xs <= adc < xe:
            return round((ye - ys) / (xe - xs) * (adc - xs) + ys)
    return 0
```

### Stage 3 — Temperature compensation

Source: `ByteHelper.GetTemperatureCompensatedWmeValue`

Nominal operating temperature is 22 °C. The correction is proportional to the
deviation from that nominal.

```python
def temperature_compensate_wme(raw_wme, temp_c):
    NOMINAL_TEMP   = 2200   # 22.00 °C × 100
    LOW_THRESHOLD  = 1300
    HIGH_THRESHOLD = 2500
    LOW_FACTOR     = -3
    HIGH_FACTOR    = -6

    v = float(raw_wme)
    if v > HIGH_THRESHOLD:
        v = (v - HIGH_THRESHOLD) * HIGH_FACTOR + (HIGH_THRESHOLD - LOW_THRESHOLD) * LOW_FACTOR
    else:
        v = (v - LOW_THRESHOLD) * LOW_FACTOR

    temp_delta = temp_c * 100 - NOMINAL_TEMP
    return round(raw_wme + v * temp_delta / 65536.0)
```

### Stage 4 — Calibration (device-specific)

Source: `ByteHelper.GetCalibratedWme`

Uses the 4 O-command calibration slots to build a piecewise linear curve mapping
the device's t_comp values to `NominalCalibrationConstants = [1320, 1820, 2690, 4000]`.
The result is divided by 100 to give a percentage.

For each slot (sorted by slot index):
1. Run `raw_int` and `temperature` from the O-response through stages 1–3 to get X
2. Pair X with `NominalCalibrationConstants[slot_index]` as Y
3. Interpolate to find the calibrated value for the current t_comp
4. Divide by 100

Falls back to `t_comp / 100.0` if fewer than 2 calibration points are available.

### Stage 5 — Battery voltage compensation

Source: `ByteHelper.GetVoltageCompensatedWme`

Low battery causes the device to under-report WME. A 26-entry lookup table
(`BatteryLevelTable`) maps battery level to the device's measured WME at each of
five reference moisture points (9 %, 13.2 %, 18.2 %, 26.9 %, 40 %). The correction
is a piecewise linear interpolation between the two surrounding reference points.

At battery = 86 % the table is the identity (no correction). Below 86 % the
device underestimates → correction boosts; above 86 % it overestimates → correction
reduces.

### Stage 6 — Clamp

```python
if volt_comp < 6.0:
    return 0.0
return min(volt_comp, 100.0)
```

---

## Typical Connection Flow

```
1. Scan for devices advertising 00005500-d102-11e1-9b23-00025b00a5a5

2. Connect and enable notifications on COMMAND_CHARACTERISTIC_ID

3. Write C → read total record count N from 7-byte response

4. Write O → collect 4 × 19-byte calibration responses

5. Write R [start_hi] [start_lo] [end_hi] [end_lo] [checksum]
   → collect N × 20-byte history record responses
   (indices 1-based; first run: start=1, end=N;
    incremental: start=last_id-4, end=N)

6. Disconnect
```

---

## Notes

- **Year encoding**: Device stores 2-digit year (e.g. `0x1A` = 26). The integration
  combines this with the current century from the host clock to get the full year.

- **MAC in records**: Bytes 0–3 of history records and O-responses are the last
  4 bytes of the device MAC address, useful for de-multiplexing multi-device
  notification streams.

- **Battery byte offset**: In the 12-byte S response, battery is at offset 10.
  In the 20-byte R record, battery is at offset 18.
