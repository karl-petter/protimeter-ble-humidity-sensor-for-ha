"""
Protimeter BLE protocol parser.

All formulas are reverse-engineered from ProtimeterApp.dll
(Xamarin/.NET assembly inside ProtimeterBLE.apk).
See PROTOCOL.md for the full specification.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .const import CURRENT_READING_LEN, HISTORY_RECORD_LEN


# ── Lookup tables (from ByteHelper static constructor) ─────────────────────────

# AdcTable: maps (adc_value) → raw_wme via piecewise linear interpolation
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

def _wme_to_adc(raw_int: int) -> float:
    """Scale raw WME integer to internal ADC units."""
    return round(raw_int / 1000.0 * 758.51851851851848)


def _adc_to_raw_wme(adc: float) -> float:
    """Piecewise linear interpolation through AdcTable."""
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
    NOMINAL_TEMP    = 2200    # 22.00 °C × 100
    LOW_THRESHOLD   = 1300
    HIGH_THRESHOLD  = 2500
    LOW_FACTOR      = -3
    HIGH_FACTOR     = -6

    v = float(raw_wme)
    if v > HIGH_THRESHOLD:
        v = ((v - HIGH_THRESHOLD) * HIGH_FACTOR
             + (HIGH_THRESHOLD - LOW_THRESHOLD) * LOW_FACTOR)
    else:
        v = (v - LOW_THRESHOLD) * LOW_FACTOR

    temp_delta = temp_c * 100.0 - NOMINAL_TEMP
    v = v * temp_delta / 65536.0
    return round(raw_wme + v)


def _decode_wme(raw_int: int, temp_c: float) -> float:
    """
    Wood Moisture Equivalent (%) — approximate, without device calibration.

    Full accuracy requires calibration offsets fetched via the 'O' command
    and battery voltage compensation via BatteryLevelTable.  Those are
    omitted here since they require a connected device at setup time.

    Returns 0.0 if the value is below the 6 % noise floor.
    Clamped to [0, 100].
    """
    if raw_int == 0:
        return 0.0
    adc     = _wme_to_adc(raw_int)
    raw     = _adc_to_raw_wme(adc)
    t_comp  = _temperature_compensate_wme(raw, temp_c)
    # Nominal calibration fallback (no device-specific offsets)
    cal     = t_comp / 100.0
    # Clamp
    if cal < 6.0:
        return 0.0
    return min(cal, 100.0)


# ── Public data types ──────────────────────────────────────────────────────────

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

def parse_current_reading(data: bytes | bytearray) -> ProtimeterReading | None:
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
    return ProtimeterReading(
        humidity    = round(_decode_humidity(data[4], data[5]), 1),
        temperature = round(temp, 1),
        wme         = round(_decode_wme(_u16(data[8], data[9]), temp), 1),
        battery     = data[10],
    )


def parse_history_record(data: bytes | bytearray) -> ProtimeterRecord | None:
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

    # Reconstruct 4-digit year from 2-digit device value + current century
    from datetime import datetime
    century = (datetime.utcnow().year // 100) * 100
    year = century + data[6]

    temp = _decode_temperature(data[14], data[15])
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
        wme         = round(_decode_wme(_u16(data[16], data[17]), temp), 1),
        battery     = data[18],
    )


def build_history_request(start: int, end: int) -> bytes:
    """
    Build the 6-byte payload for command 'R'.
    Checksum = XOR of the four index bytes.
    """
    s_hi, s_lo = (start >> 8) & 0xFF, start & 0xFF
    e_hi, e_lo = (end   >> 8) & 0xFF, end   & 0xFF
    checksum   = s_hi ^ s_lo ^ e_hi ^ e_lo
    return bytes([0x52, s_hi, s_lo, e_hi, e_lo, checksum])
