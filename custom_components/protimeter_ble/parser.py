"""
Protimeter BLE protocol parser.

All formulas are reverse-engineered from ProtimeterApp.dll
(Xamarin/.NET assembly inside ProtimeterBLE.apk).
See PROTOCOL.md for the full specification.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .const import CURRENT_READING_LEN, HISTORY_RECORD_LEN


# ── Lookup tables (from ByteHelper static constructor) ─────────────────────────

# AdcTable: maps (adc_value) → raw_wme via piecewise linear interpolation
# Source: ByteHelper static constructor, confirmed from ProtimeterApp.il .cctor
# Columns: (XStart, XEnd, YStart, YEnd)
_ADC_TABLE: list[tuple[float, float, float, float]] = [
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

# NominalCalibrationConstants: reference WME values for calibration slots 1–4.
# Source: ByteHelper.NominalCalibrationConstants, RVA 0x00197c30 in ProtimeterApp.dll.
# GetCalibratedWme maps each O-command slot's t_comp (X) → this reference value (Y).
_NOMINAL_CAL = [1320, 1820, 2690, 4000]

# BatteryLevelTable: maps battery % → H2o values (device-measured WME when true
# moisture is at calibration reference points 9, 13.2, 18.2, 26.9, 40 %).
# Source: ByteHelper static constructor (BatteryLevelTable field initialiser).
# At battery=86 the H2o values equal the reference values (identity / no correction).
# Below 86: device underestimates (H2o < reference) → correction boosts WME.
# Above 86: device overestimates (H2o > reference) → correction reduces WME.
# Sorted descending by battery — same order as in the IL .cctor.
# Tuple layout: (battery, h2o9, h2o13, h2o18, h2o26, h2o40)
_BATTERY_TABLE: list[tuple[int, float, float, float, float, float]] = [
    (110, 12.0,  15.0,  22.0,  32.0,  47.0),
    (100, 10.99, 13.75, 19.19, 30.08, 45.07),
    ( 96, 10.83, 13.6,  18.93, 29.17, 43.52),
    ( 93, 10.68, 13.46, 18.66, 28.26, 41.98),
    ( 89, 10.6,  13.33, 18.43, 27.59, 40.99),
    ( 86, 10.53, 13.2,  18.2,  26.91, 40.0),
    ( 82, 10.36, 13.09, 17.97, 26.58, 39.1),
    ( 79, 10.2,  12.97, 17.74, 26.26, 38.2),
    ( 75, 10.16, 12.79, 17.46, 25.87, 36.99),
    ( 71, 10.13, 12.6,  17.19, 25.49, 35.78),
    ( 68, 10.04, 12.49, 16.98, 25.18, 34.84),
    ( 64,  9.95, 12.38, 16.78, 24.87, 33.91),
    ( 61,  9.86, 12.24, 16.57, 24.55, 32.92),
    ( 57,  9.76, 12.1,  16.35, 24.24, 31.93),
    ( 54,  9.61, 11.96, 16.13, 23.9,  31.0),
    ( 50,  9.45, 11.82, 15.9,  23.57, 30.08),
    ( 46,  9.36, 11.68, 15.67, 23.26, 29.1),
    ( 43,  9.27, 11.54, 15.43, 22.95, 28.12),
    ( 39,  9.13, 11.43, 15.24, 22.65, 27.43),
    ( 36,  8.99, 11.31, 15.05, 22.35, 26.74),
    ( 32,  8.95, 11.15, 14.79, 21.98, 26.28),
    ( 29,  8.91, 10.99, 14.54, 21.62, 25.82),
    ( 25,  8.83, 10.89, 14.34, 21.31, 25.48),
    ( 21,  8.75, 10.78, 14.13, 21.01, 25.13),
    ( 18,  8.69, 10.61, 13.94, 20.66, 24.77),
    ( 14,  8.63, 10.44, 13.74, 20.31, 24.4),
]


# ── Primitive helpers ──────────────────────────────────────────────────────────

def _u16(high: int, low: int) -> int:
    """Big-endian uint16 from two bytes."""
    return int(high * 256 + low)


def _decode_humidity(high: int, low: int) -> float:
    """
    Relative humidity in %RH.
    Source: ByteHelper.GetHumidityFromLowHighBytes
    Encoding: 14-bit value in the top 14 bits of a 16-bit big-endian word.
    """
    return _u16(high, low) / 16384.0 * 100.0


def _decode_temperature(high: int, low: int) -> float:
    """
    Temperature in °C.
    Source: ByteHelper.GetTemperatureFromLowHighBytes
    Encoding: Sensirion-style 14-bit ADC.  Bits [15:2] of the 16-bit word.
    Formula:  ((high*64) + (low/4)) / 16384 * 165 - 40
    """
    raw = high * 64.0 + low / 4.0
    return (raw / 16384.0) * 165.0 - 40.0


# ── WME pipeline ───────────────────────────────────────────────────────────────

def _wme_to_adc(raw_int: float) -> float:
    """Scale raw WME integer to internal ADC units. Source: ByteHelper.GetWmeAdcValue"""
    return round(raw_int / 1000.0 * 758.51851851851848)


def _adc_to_raw_wme(adc: float) -> float:
    """Piecewise linear interpolation through AdcTable. Source: ByteHelper.GetRawWmeFromAdc"""
    for xstart, xend, ystart, yend in _ADC_TABLE:
        if xstart <= adc < xend:
            slope = (yend - ystart) / (xend - xstart)
            return round(slope * (adc - xstart) + ystart)
    return 0.0


def _temperature_compensate_wme(raw_wme: float, temp_c: float) -> float:
    """
    Temperature compensation.
    Source: ByteHelper.GetTemperatureCompensatedWmeValue
    Nominal operating temperature: 22 °C (2200 in 100ths of °C).
    """
    NOMINAL_TEMP   = 2200
    LOW_THRESHOLD  = 1300
    HIGH_THRESHOLD = 2500
    LOW_FACTOR     = -3
    HIGH_FACTOR    = -6

    v = float(raw_wme)
    if v > HIGH_THRESHOLD:
        v = ((v - HIGH_THRESHOLD) * HIGH_FACTOR
             + (HIGH_THRESHOLD - LOW_THRESHOLD) * LOW_FACTOR)
    else:
        v = (v - LOW_THRESHOLD) * LOW_FACTOR

    temp_delta = temp_c * 100.0 - NOMINAL_TEMP
    v = v * temp_delta / 65536.0
    return round(raw_wme + v)


def _calibrate_wme(t_comp: float, cal_offsets: list[CalibrationOffset]) -> float:
    """
    Map temperature-compensated WME to calibrated WME using device-specific
    O-command calibration data.

    Source: ByteHelper.GetCalibratedWme

    Each O-command slot provides a device measurement (raw_int + temperature).
    We run that through the same ADC→raw_wme→t_comp pipeline to get the X
    coordinate, and pair it with NominalCalibrationConstants[slot_index] as Y.
    Then linearly interpolate to find the calibrated value for the current t_comp.

    Falls back to t_comp / 100.0 if fewer than 2 calibration points are available
    (mirrors the app's exception-handler fallback).
    """
    # Build (X, Y) entries sorted by slot order (as the app iterates them)
    entries: list[tuple[float, float]] = []
    for idx, offset in enumerate(sorted(cal_offsets, key=lambda o: o.slot)):
        if idx >= len(_NOMINAL_CAL):
            break
        adc     = _wme_to_adc(offset.raw_int)
        raw_wme = _adc_to_raw_wme(adc)
        x       = float(_temperature_compensate_wme(raw_wme, offset.temperature))
        y       = float(_NOMINAL_CAL[idx])
        entries.append((x, y))

    if len(entries) < 2:
        return t_comp / 100.0  # fallback: same as app's exception-handler (t_comp / 100)

    # Find the two surrounding entries (extrapolates at both ends)
    if t_comp < entries[0][0]:
        lower, upper = entries[0], entries[1]
    elif t_comp >= entries[-1][0]:
        lower, upper = entries[-2], entries[-1]
    else:
        lower, upper = entries[0], entries[1]
        for i in range(len(entries) - 1):
            if entries[i][0] <= t_comp < entries[i + 1][0]:
                lower, upper = entries[i], entries[i + 1]
                break

    slope = (upper[1] - lower[1]) / (upper[0] - lower[0])
    # Divide by 100 here — mirrors GetCalibratedWme's internal ldc.r8 100.0 / div
    return (slope * (t_comp - lower[0]) + lower[1]) / 100.0


def _voltage_compensate_wme(battery: int, calibrated: float) -> float:
    """
    Battery-voltage compensation.
    Source: ByteHelper.GetVoltageCompensatedWme

    Finds the floor entry in BatteryLevelTable (highest Battery ≤ actual battery),
    then linearly interpolates between the two surrounding H2o calibration points to
    map the device reading to the true-moisture reference scale.

    Reference moisture points: 9.0, 13.2, 18.2, 26.9, 40.0 %
    """
    # Floor lookup: iterate descending table, take first entry with Battery ≤ battery
    entry = _BATTERY_TABLE[-1]  # fallback = lowest entry (battery=14)
    for e in _BATTERY_TABLE:
        if e[0] <= battery:
            entry = e
            break

    _, h2o9, h2o13, h2o18, h2o26, h2o40 = entry

    # Select surrounding H2o bracket and interpolate
    if calibrated <= h2o13:
        lo_dev, lo_ref, hi_dev, hi_ref = h2o9,  9.0,  h2o13, 13.2
    elif calibrated <= h2o18:
        lo_dev, lo_ref, hi_dev, hi_ref = h2o13, 13.2, h2o18, 18.2
    elif calibrated <= h2o26:
        lo_dev, lo_ref, hi_dev, hi_ref = h2o18, 18.2, h2o26, 26.9
    else:
        lo_dev, lo_ref, hi_dev, hi_ref = h2o26, 26.9, h2o40, 40.0

    return ((hi_ref - lo_ref) / (hi_dev - lo_dev)) * (calibrated - lo_dev) + lo_ref


def _decode_wme(
    raw_int: int,
    temp_c: float,
    battery: int,
    cal_offsets: list[CalibrationOffset] | None = None,
) -> float:
    """
    Wood Moisture Equivalent (%).

    Pipeline: raw_int → ADC → raw_wme (AdcTable) →
              t_comp (GetTemperatureCompensatedWmeValue) →
              calibrated % (GetCalibratedWme, includes ÷100) →
              voltage-compensated % (GetVoltageCompensatedWme) →
              clamp to [0, 100].

    Source: ByteHelper.GetWmeValue
    """
    if raw_int == 0:
        return 0.0
    adc    = _wme_to_adc(raw_int)
    raw    = _adc_to_raw_wme(adc)
    t_comp = _temperature_compensate_wme(raw, temp_c)

    if cal_offsets:
        cal = _calibrate_wme(t_comp, cal_offsets)   # already ÷100
    else:
        cal = t_comp / 100.0

    volt_comp = _voltage_compensate_wme(battery, cal)

    if volt_comp < 6.0:
        return 0.0
    return min(volt_comp, 100.0)


# ── Public data types ──────────────────────────────────────────────────────────

@dataclass
class CalibrationOffset:
    """
    One calibration slot from the O command response.
    Source: ByteHelper.GetCalibrationOffsetFromBytes
    """
    slot:        int    # calibration point index (1–4)
    raw_int:     int    # device's WME measurement at calibration (big-endian uint16)
    temperature: float  # temperature at calibration (°C)


@dataclass
class ProtimeterReading:
    """Decoded sensor reading from a 12-byte 'S' command response."""
    humidity:    float   # %RH
    temperature: float   # °C
    wme:         float   # Wood Moisture Equivalent %
    battery:     int     # 0–100 %


@dataclass
class ProtimeterRecord:
    """Decoded 20-byte history record from an 'R' command response."""
    record_id:   int
    year:        int
    month:       int
    day:         int
    hour:        int
    minute:      int
    second:      int
    humidity:    float
    temperature: float
    wme:         float
    battery:     int


# ── Public parsers ─────────────────────────────────────────────────────────────

def parse_calibration_offset(data: bytes | bytearray) -> CalibrationOffset | None:
    """
    Parse one 19-byte O-command notification.

    Byte layout (from ByteHelper.GetCalibrationOffsetFromBytes):
      [0:4]   MAC tail
      [4]     calibration slot (1–4)
      [5:13]  timestamp (not used)
      [13:15] temperature (same encoding as history records)
      [15:17] raw WME integer at calibration (big-endian uint16)
      [17:19] reference WME (not needed for calibration)
    """
    if not data or len(data) < 17:
        return None
    return CalibrationOffset(
        slot        = data[4],
        raw_int     = _u16(data[15], data[16]),
        temperature = _decode_temperature(data[13], data[14]),
    )


def parse_current_reading(
    data: bytes | bytearray,
    cal_offsets: list[CalibrationOffset] | None = None,
) -> ProtimeterReading | None:
    """
    Parse the 12-byte response to command 'S'.

    Byte layout (from ByteHelper.GetSensorReadingFromBytes):
      [0:4]  unknown / status
      [4:6]  humidity   big-endian uint16
      [6:8]  temperature  special 14-bit encoding
      [8:10] raw WME integer  big-endian uint16
      [10]   battery  0–100
      [11]   unknown
    """
    if not data or len(data) < CURRENT_READING_LEN:
        return None

    temp = _decode_temperature(data[6], data[7])
    battery = data[10]
    return ProtimeterReading(
        humidity    = round(_decode_humidity(data[4], data[5]), 1),
        temperature = round(temp, 1),
        wme         = round(_decode_wme(_u16(data[8], data[9]), temp, battery, cal_offsets), 1),
        battery     = battery,
    )


def parse_history_record(
    data: bytes | bytearray,
    cal_offsets: list[CalibrationOffset] | None = None,
) -> ProtimeterRecord | None:
    """
    Parse a 20-byte history record from command 'R'.

    Byte layout (from ByteHelper.GetSensorReadingFromRecordBytes):
      [0:4]  MAC tail (last 4 bytes of device address)
      [4:6]  record ID  big-endian uint16
      [6]    year  2-digit (e.g. 0x1A → 26 → 2026)
      [7]    month
      [8]    day
      [9]    hour
      [10]   minute
      [11]   second
      [12:14] humidity
      [14:16] temperature
      [16:18] raw WME integer
      [18]   battery
      [19]   unknown / checksum
    """
    if not data or len(data) < HISTORY_RECORD_LEN:
        return None

    century = (datetime.utcnow().year // 100) * 100
    year = century + data[6]

    temp = _decode_temperature(data[14], data[15])
    battery = data[18]
    return ProtimeterRecord(
        record_id   = _u16(data[4], data[5]),
        year        = year,
        month       = data[7],
        day         = data[8],
        hour        = data[9],
        minute      = data[10],
        second      = data[11],
        humidity    = round(_decode_humidity(data[12], data[13]), 1),
        temperature = round(temp, 1),
        wme         = round(_decode_wme(_u16(data[16], data[17]), temp, battery, cal_offsets), 1),
        battery     = battery,
    )


def build_set_clock_command(dt: "datetime") -> bytes:
    """
    Build the 8-byte payload for command 'T' (set real-time clock).

    Format:
      [0]  0x54  ('T')
      [1]  year - 2000  (e.g. 2026 → 0x1A)
      [2]  month  (1–12)
      [3]  day    (1–31)
      [4]  hour   (0–23)
      [5]  minute (0–59)
      [6]  second (0–59)
      [7]  XOR of bytes 1–6
    """
    year_byte = dt.year - 2000
    payload = [year_byte, dt.month, dt.day, dt.hour, dt.minute, dt.second]
    checksum = 0
    for b in payload:
        checksum ^= b
    return bytes([0x54] + payload + [checksum])


def build_history_request(start: int, end: int) -> bytes:
    """
    Build the 6-byte payload for command 'R'.
    Checksum = XOR of the four index bytes.
    """
    s_hi, s_lo = (start >> 8) & 0xFF, start & 0xFF
    e_hi, e_lo = (end   >> 8) & 0xFF, end   & 0xFF
    checksum   = s_hi ^ s_lo ^ e_hi ^ e_lo
    return bytes([0x52, s_hi, s_lo, e_hi, e_lo, checksum])
