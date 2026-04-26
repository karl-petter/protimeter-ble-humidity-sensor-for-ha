"""
Parser unit tests using real BLE notification bytes captured from the debug log
(2026-04-23 20:25 fetch).

Sensor addresses:
  Sensor A  00:22:A3:00:C7:57
  Sensor B  00:22:A3:00:C3:0E

Expected values are cross-referenced against the official Protimeter app.
"""

import pytest

from custom_components.protimeter_ble.parser import (
    CalibrationOffset,
    ProtimeterRecord,
    _adc_to_raw_wme,
    _calibrate_wme,
    _decode_humidity,
    _decode_temperature,
    _temperature_compensate_wme,
    _voltage_compensate_wme,
    _wme_to_adc,
    parse_history_record,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _hex(s: str) -> bytes:
    return bytes.fromhex(s)


# ── Calibration offsets (from O-command log, same fetch) ──────────────────────

SENSOR_A_CAL = [
    CalibrationOffset(slot=1, raw_int=304, temperature=21.6),
    CalibrationOffset(slot=2, raw_int=451, temperature=21.6),
    CalibrationOffset(slot=3, raw_int=635, temperature=21.6),
    CalibrationOffset(slot=4, raw_int=735, temperature=21.6),
]

SENSOR_B_CAL = [
    CalibrationOffset(slot=1, raw_int=302, temperature=18.1),
    CalibrationOffset(slot=2, raw_int=448, temperature=18.1),
    CalibrationOffset(slot=3, raw_int=635, temperature=18.1),
    CalibrationOffset(slot=4, raw_int=722, temperature=18.1),
]


# ── Pipeline unit tests ────────────────────────────────────────────────────────

class TestHumidityDecode:
    def test_75_percent(self):
        # 0x3000 = 12288 → 75.0%
        assert _decode_humidity(0x30, 0x00) == pytest.approx(75.0, abs=0.01)

    def test_74_8_percent(self):
        # 0x2FDC = 12252 → 74.78…% → rounds to 74.8
        assert round(_decode_humidity(0x2F, 0xDC), 1) == 74.8


class TestTemperatureDecode:
    def test_9_6_celsius(self):
        # data[14]=0x4C, data[15]=0xF0 from Sensor A record 328
        assert round(_decode_temperature(0x4C, 0xF0), 1) == 9.6

    def test_9_3_celsius(self):
        # data[14]=0x4C, data[15]=0x84 from Sensor A record 326
        assert round(_decode_temperature(0x4C, 0x84), 1) == 9.3

    def test_8_1_celsius(self):
        # data[14]=0x4A, data[15]=0xAC from Sensor B record 578
        assert round(_decode_temperature(0x4A, 0xAC), 1) == 8.1


class TestWmePipeline:
    """Step-by-step verification of the WME pipeline for Sensor A record 328."""

    RAW_INT = 288  # 0x0120

    def test_wme_to_adc(self):
        assert _wme_to_adc(self.RAW_INT) == 218

    def test_adc_to_raw_wme(self):
        assert _adc_to_raw_wme(218) == 1006

    def test_temperature_compensate(self):
        # raw_wme=1006, temp=9.589°C → t_comp=989
        assert _temperature_compensate_wme(1006, 9.589) == 989

    def test_calibrate_wme_sydvagg(self):
        # t_comp=989 with Sensor A cal → calibrated ≈ 12.57%
        cal = _calibrate_wme(989, SENSOR_A_CAL)
        assert cal == pytest.approx(12.57, abs=0.05)

    def test_voltage_compensate_wme_battery83(self):
        # battery=83 → floor entry is (82, …); calibrated≈12.57 → ~12.4
        result = _voltage_compensate_wme(83, 12.57)
        assert round(result, 1) == 12.4


class TestVoltageCompensate:
    def test_battery_86_identity(self):
        # At battery=86 the table is the identity mapping (no correction).
        # h2o13=13.2, h2o18=18.2; a value of 15.7 sits between the 13.2→18.2 bracket.
        result = _voltage_compensate_wme(86, 15.7)
        assert result == pytest.approx(15.7, abs=0.1)

    def test_battery_72_nordvagg(self):
        # For Sensor B record 578: battery=72, calibrated≈21.025 → ~22.2
        result = _voltage_compensate_wme(72, 21.025)
        assert round(result, 1) == 22.2


# ── Full parse_history_record tests ───────────────────────────────────────────

class TestParseHistoryRecordSydvagg:
    """
    Sensor A records 324–328 from the 2026-04-23 fetch.
    App-confirmed values: record 326 → WME=12.2%, record 328 → WME=12.4%.
    """

    # Raw 20-byte R-notifications captured from HA debug log
    RECORDS = {
        324: "a300c75701441a0413101c3b2fa84c34011253f3",
        325: "a300c75701451a0414101d082fc04c84011b5316",
        326: "a300c75701461a0415101d112fdc4c84011c5316",
        327: "a300c75701471a0416101d1a2ff84ccc011f5370",
        328: "a300c75701481a0417101d2430004cf0012053a4",
    }

    def _parse(self, record_id: int) -> ProtimeterRecord:
        rec = parse_history_record(_hex(self.RECORDS[record_id]), SENSOR_A_CAL)
        assert rec is not None
        return rec

    # ── Record 326 (app: WME=12.2%) ──

    def test_326_record_id(self):
        assert self._parse(326).record_id == 326

    def test_326_timestamp(self):
        r = self._parse(326)
        assert (r.year, r.month, r.day) == (2026, 4, 21)
        assert (r.hour, r.minute) == (16, 29)

    def test_326_humidity(self):
        assert self._parse(326).humidity == 74.8

    def test_326_temperature(self):
        assert self._parse(326).temperature == 9.3

    def test_326_wme_app_confirmed(self):
        # App reports 12.2% for this record
        assert self._parse(326).wme == 12.2

    def test_326_battery(self):
        assert self._parse(326).battery == 83

    # ── Record 328 (app: WME=12.4%, most-recent) ──

    def test_328_record_id(self):
        assert self._parse(328).record_id == 328

    def test_328_timestamp(self):
        r = self._parse(328)
        assert (r.year, r.month, r.day) == (2026, 4, 23)
        assert (r.hour, r.minute) == (16, 29)

    def test_328_humidity(self):
        assert self._parse(328).humidity == 75.0

    def test_328_temperature(self):
        assert self._parse(328).temperature == 9.6

    def test_328_wme_app_confirmed(self):
        # App reports 12.4% for this record
        assert self._parse(328).wme == 12.4

    def test_328_battery(self):
        assert self._parse(328).battery == 83


class TestParseHistoryRecordNordvagg:
    """
    Sensor B records 574–578 from the 2026-04-23 fetch.
    App-confirmed value: record 578 → WME=22.2%.
    """

    RECORDS = {
        574: "a300c30e023e1a041309092838884a7801f84448",
        575: "a300c30e023f1a041409093238a04a6801fb4962",
        576: "a300c30e02401a041509093b38884a3c01fd496f",
        577: "a300c30e02411a0416090a0838a04a8401fe43c4",
        578: "a300c30e02421a0417090a11389c4aac01fe48c0",
    }

    def _parse(self, record_id: int) -> ProtimeterRecord:
        rec = parse_history_record(_hex(self.RECORDS[record_id]), SENSOR_B_CAL)
        assert rec is not None
        return rec

    # ── Record 578 (app: WME=22.2%, most-recent) ──

    def test_578_record_id(self):
        assert self._parse(578).record_id == 578

    def test_578_timestamp(self):
        r = self._parse(578)
        assert (r.year, r.month, r.day) == (2026, 4, 23)
        assert (r.hour, r.minute) == (9, 10)

    def test_578_wme_app_confirmed(self):
        # App reports 22.2% for this record
        assert self._parse(578).wme == 22.2

    def test_578_battery(self):
        assert self._parse(578).battery == 72

    def test_578_temperature(self):
        assert self._parse(578).temperature == 8.1

    # ── Consistency across records ──

    def test_all_records_parse(self):
        for rid in self.RECORDS:
            rec = parse_history_record(_hex(self.RECORDS[rid]), SENSOR_B_CAL)
            assert rec is not None, f"record {rid} failed to parse"
            assert rec.record_id == rid


class TestParseHistoryRecordEdgeCases:
    def test_too_short_returns_none(self):
        assert parse_history_record(b"\x00" * 10) is None

    def test_empty_returns_none(self):
        assert parse_history_record(b"") is None

    def test_no_cal_offsets_still_parses(self):
        # Without cal offsets, falls back to t_comp/100 → result may differ but
        # should not raise.
        data = bytes.fromhex("a300c75701481a0417101d2430004cf0012053a4")
        rec = parse_history_record(data, cal_offsets=None)
        assert rec is not None
        assert rec.wme >= 0.0
