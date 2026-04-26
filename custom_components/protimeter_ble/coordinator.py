"""DataUpdateCoordinator for Protimeter BLE history fetching."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from bleak import BleakClient, BleakError
from bleak_retry_connector import establish_connection

from homeassistant.components.bluetooth import async_ble_device_from_address
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
import homeassistant.util.dt as dt_util

from .const import (
    BLE_RESPONSE_TIMEOUT_S,
    CMD_READ_CALIB,
    CMD_READ_COUNT,
    COMMAND_CHAR_UUID,
    COMMAND_SERVICE_UUID,
    CONF_FETCH_INTERVAL_DAYS,
    CONF_LAST_RECORD_ID,
    DEFAULT_FETCH_INTERVAL_DAYS,
    DOMAIN,
    HISTORY_OVERLAP,
    HISTORY_RECORD_LEN,
    NOTIFY_CHAR_UUID,
)
from .parser import (
    CalibrationOffset,
    ProtimeterRecord,
    build_history_request,
    parse_calibration_offset,
    parse_history_record,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)


class ProtimeterCoordinator(DataUpdateCoordinator[ProtimeterRecord | None]):
    """
    Fetch history from a Protimeter BLE sensor.

    On each update (scheduled weekly by default, or triggered manually):
      1. Connect via BLE.
      2. Send C command → get total record count.
      3. Send R command for new records (full history on first run,
         incremental with a small overlap on subsequent runs).
      4. Import records as HA long-term statistics.
      5. Persist the highest record_id for the next run.
      6. Disconnect.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._entry = entry
        self.address: str = entry.data["address"].upper()
        self._fetching: bool = False
        self._consecutive_failures: int = 0
        self._notification_id = (
            f"protimeter_ble_{self.address.lower().replace(':', '')}_error"
        )
        fetch_days: int = entry.options.get(
            CONF_FETCH_INTERVAL_DAYS,
            entry.data.get(CONF_FETCH_INTERVAL_DAYS, DEFAULT_FETCH_INTERVAL_DAYS),
        )
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{self.address}",
            update_interval=timedelta(days=fetch_days),
        )

    # ── Public helpers ─────────────────────────────────────────────────────────

    @property
    def fetching(self) -> bool:
        """True while a history fetch is in progress."""
        return self._fetching

    @property
    def last_record_id(self) -> int | None:
        """Record ID of the last successfully imported record, or None on first run."""
        return self._entry.data.get(CONF_LAST_RECORD_ID)

    # ── DataUpdateCoordinator interface ───────────────────────────────────────

    async def _async_update_data(self) -> ProtimeterRecord | None:
        return await self._fetch_history()

    # ── BLE operations ────────────────────────────────────────────────────────

    async def _fetch_history(self) -> ProtimeterRecord | None:
        """Connect to the device and import any new history records."""
        if self._fetching:
            _LOGGER.warning(
                "Protimeter %s: fetch already in progress, ignoring duplicate request",
                self.address,
            )
            return self.data

        self._fetching = True
        self.async_update_listeners()
        _LOGGER.warning("Protimeter %s: starting history fetch", self.address)

        try:
            result = await self._do_fetch()
            # Success — reset failure tracking and dismiss any outstanding notification
            if self._consecutive_failures > 0:
                self._consecutive_failures = 0
                self.hass.async_create_task(
                    self.hass.services.async_call(
                        "persistent_notification",
                        "dismiss",
                        {"notification_id": self._notification_id},
                        blocking=False,
                    )
                )
            return result
        except UpdateFailed as exc:
            self._consecutive_failures += 1
            _LOGGER.warning(
                "Protimeter %s: fetch failed (consecutive failures: %d) — %s",
                self.address, self._consecutive_failures, exc,
            )
            if self._consecutive_failures >= 3:
                self.hass.async_create_task(
                    self.hass.services.async_call(
                        "persistent_notification",
                        "create",
                        {
                            "title": f"Protimeter {self.address} unreachable",
                            "message": (
                                f"{exc}\n\n"
                                f"Failed to fetch history {self._consecutive_failures} "
                                f"time(s) in a row. Check device battery and BLE proxy "
                                f"placement. This notification will clear automatically "
                                f"when the next fetch succeeds."
                            ),
                            "notification_id": self._notification_id,
                        },
                        blocking=False,
                    )
                )
            raise
        finally:
            self._fetching = False
            # async_update_listeners is called by the coordinator framework after
            # _async_update_data returns, so the button re-enables automatically.

    async def _do_fetch(self) -> ProtimeterRecord | None:
        """Inner fetch — called only when no fetch is already running."""
        device = async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if device is None:
            raise UpdateFailed(
                f"Protimeter {self.address}: device not found by HA Bluetooth scanner "
                "(not in range, or no connectable advertisement seen recently)"
            )

        _LOGGER.debug("Protimeter %s: connecting (rssi=%s)", self.address,
                      getattr(device, "rssi", "?"))

        try:
            client = await establish_connection(BleakClient, device, self.address)
        except (asyncio.TimeoutError, BleakError) as exc:
            raise UpdateFailed(
                f"Protimeter {self.address}: failed to connect — {exc}"
            ) from exc

        try:
            # Dump all GATT characteristics (debug) and discover the right
            # command characteristic for this device/proxy combination.
            cmd_uuid = self._discover_command_char(client)
            _LOGGER.debug(
                "Protimeter %s: using command char %s", self.address, cmd_uuid
            )

            count = await self._ble_read_count(client, cmd_uuid)
            if count == 0:
                _LOGGER.debug("Protimeter %s: device reports 0 records", self.address)
                return self.data

            cal_offsets = await self._ble_read_calibration(client, cmd_uuid)
            _LOGGER.debug(
                "Protimeter %s: got %d calibration slot(s)", self.address, len(cal_offsets)
            )

            last_id = self.last_record_id
            if last_id is None:
                # First run: read the complete history.
                # Device records are 1-indexed (record 1 = oldest, record count = newest).
                start = 1
            else:
                # Incremental: re-read last HISTORY_OVERLAP records to verify
                # no gap, then continue with new records
                start = max(1, last_id - HISTORY_OVERLAP + 1)

            end = count  # last valid record index = count (1-indexed)
            if start > end:
                _LOGGER.debug(
                    "Protimeter %s: already up to date (count=%d, last_id=%d)",
                    self.address, count, last_id,
                )
                return self.data

            _LOGGER.debug(
                "Protimeter %s: fetching records %d–%d (%d on device)",
                self.address, start, end, count,
            )
            records = await self._ble_read_records(client, start, end, cmd_uuid, cal_offsets)

        except (asyncio.TimeoutError, BleakError) as exc:
            raise UpdateFailed(
                f"Protimeter {self.address}: BLE error during read — {exc}"
            ) from exc
        finally:
            await client.disconnect()

        if not records:
            return self.data

        self._import_statistics(records)

        new_last_id = max(r.record_id for r in records)
        self.hass.config_entries.async_update_entry(
            self._entry,
            data={**self._entry.data, CONF_LAST_RECORD_ID: new_last_id},
        )
        _LOGGER.info(
            "Protimeter %s: imported %d records, last_id=%d",
            self.address, len(records), new_last_id,
        )

        # Return the most-recent record as coordinator.data (shown on sensor entities)
        return max(records, key=lambda r: r.record_id)

    def _discover_command_char(self, client: BleakClient) -> str:
        """
        Find the best characteristic UUID for sending commands and receiving
        responses. Logs all characteristics for debugging.

        Priority:
          1. A char in the Protimeter service (00005500) that has write+notify.
          2. COMMAND_CHAR_UUID constant (00005501) if present anywhere.
          3. NOTIFY_CHAR_UUID constant (00001014) as last resort.
        """
        candidates: list[tuple[int, str]] = []  # (priority, uuid)
        for svc in client.services:
            for ch in svc.characteristics:
                _LOGGER.debug(
                    "Protimeter %s: GATT char uuid=%s handle=%d props=%s",
                    self.address, ch.uuid, ch.handle, ch.properties,
                )
                props = set(ch.properties)
                has_write = bool(props & {"write", "write-without-response"})
                has_notify = bool(props & {"notify", "indicate"})
                in_proto_svc = svc.uuid.lower() == COMMAND_SERVICE_UUID.lower()

                if in_proto_svc and has_write and has_notify:
                    candidates.append((0, ch.uuid))
                elif ch.uuid.lower() == COMMAND_CHAR_UUID.lower():
                    candidates.append((1, ch.uuid))
                elif ch.uuid.lower() == NOTIFY_CHAR_UUID.lower():
                    candidates.append((2, ch.uuid))

        if candidates:
            candidates.sort()
            return candidates[0][1]

        # Nothing matched — fall back to the constant and let bleak fail loudly
        _LOGGER.warning(
            "Protimeter %s: no suitable command characteristic found in GATT; "
            "falling back to %s", self.address, COMMAND_CHAR_UUID,
        )
        return COMMAND_CHAR_UUID

    async def _start_notify_best_effort(
        self, client: BleakClient, uuid: str, handler
    ) -> bool:
        """
        Call start_notify and return True on success.
        If the CCCD write is refused (bonding required), log a warning and
        return False — the caller will still send the command in case the
        device fires unsolicited notifications.
        """
        try:
            await client.start_notify(uuid, handler)
            return True
        except BleakError as exc:
            _LOGGER.warning(
                "Protimeter %s: could not enable notifications on %s: %s — "
                "will send command anyway (device may notify without CCCD)",
                self.address, uuid, exc,
            )
            return False

    async def _ble_read_count(self, client: BleakClient, cmd_uuid: str) -> int:
        """
        Send C command and return the total number of stored records.
        Response: 2-byte big-endian uint16.
        """
        result: list[int] = []
        done = asyncio.Event()

        def _handler(_sender: int, data: bytearray) -> None:
            _LOGGER.debug(
                "Protimeter %s: C response %d bytes: %s",
                self.address, len(data), data.hex(),
            )
            # Response format: MAC(4) + count_hi + count_lo + xor_checksum
            # e.g. a300c757 0142 70  →  count = 0x0142 = 322
            if len(data) == 7 and not done.is_set():
                count = data[4] * 256 + data[5]
                result.append(count)
                done.set()

        subscribed = await self._start_notify_best_effort(client, cmd_uuid, _handler)
        await client.write_gatt_char(cmd_uuid, CMD_READ_COUNT, response=True)
        try:
            await asyncio.wait_for(done.wait(), timeout=BLE_RESPONSE_TIMEOUT_S)
        except asyncio.TimeoutError as exc:
            if subscribed:
                await client.stop_notify(cmd_uuid)
            raise UpdateFailed(
                f"Protimeter {self.address}: timed out reading record count"
            ) from exc
        if subscribed:
            await client.stop_notify(cmd_uuid)
        return result[0] if result else 0

    async def _ble_read_calibration(
        self, client: BleakClient, cmd_uuid: str
    ) -> list[CalibrationOffset]:
        """
        Send O command and collect per-slot calibration offsets.
        The device returns one 19-byte notification per calibration slot (up to 4).
        Used by GetCalibratedWme to map device-specific t_comp values to
        NominalCalibrationConstants reference points [1320, 1820, 2690, 4000].
        """
        received: list[CalibrationOffset] = []
        done = asyncio.Event()

        def _handler(_sender: int, data: bytearray) -> None:
            if len(data) == 19:
                offset = parse_calibration_offset(data)
                if offset is not None:
                    _LOGGER.debug(
                        "Protimeter %s: calibration slot %d raw_int=%d temp=%.1f",
                        self.address, offset.slot, offset.raw_int, offset.temperature,
                    )
                    received.append(offset)
                    if len(received) >= 4:
                        done.set()

        subscribed = await self._start_notify_best_effort(client, cmd_uuid, _handler)
        await client.write_gatt_char(cmd_uuid, CMD_READ_CALIB, response=True)
        try:
            await asyncio.wait_for(done.wait(), timeout=BLE_RESPONSE_TIMEOUT_S)
        except asyncio.TimeoutError:
            # Fewer than 4 slots is acceptable — use what we got
            if not received:
                _LOGGER.warning(
                    "Protimeter %s: no calibration data received; WME will be uncalibrated",
                    self.address,
                )
        if subscribed:
            await client.stop_notify(cmd_uuid)
        return received

    async def _ble_read_records(
        self, client: BleakClient, start: int, end: int, cmd_uuid: str,
        cal_offsets: list[CalibrationOffset] | None = None,
    ) -> list[ProtimeterRecord]:
        """
        Send R command and collect all records from start..end (inclusive).
        Each record arrives as a separate 20-byte notification.
        """
        expected = end - start + 1
        received: list[ProtimeterRecord] = []
        done = asyncio.Event()

        def _handler(_sender: int, data: bytearray) -> None:
            _LOGGER.debug(
                "Protimeter %s: R notification %d bytes: %s",
                self.address, len(data), data.hex(),
            )
            if len(data) == HISTORY_RECORD_LEN and not done.is_set():
                rec = parse_history_record(data, cal_offsets)
                if rec is not None:
                    received.append(rec)
                    if len(received) >= expected:
                        done.set()
                else:
                    _LOGGER.debug(
                        "Protimeter %s: parse_history_record returned None for %s",
                        self.address, data.hex(),
                    )

        # Allow 0.3 s per record (BLE is fast; this is very conservative)
        timeout_s = min(300.0, 30.0 + expected * 0.3)

        cmd_bytes = build_history_request(start, end)
        _LOGGER.debug(
            "Protimeter %s: sending R command %s (records %d–%d, timeout %.0fs)",
            self.address, cmd_bytes.hex(), start, end, timeout_s,
        )
        subscribed = await self._start_notify_best_effort(client, cmd_uuid, _handler)
        await client.write_gatt_char(cmd_uuid, cmd_bytes, response=True)
        try:
            await asyncio.wait_for(done.wait(), timeout=timeout_s)
        except asyncio.TimeoutError:
            _LOGGER.warning(
                "Protimeter %s: received %d/%d records before timeout "
                "(%.0f s); proceeding with partial data",
                self.address, len(received), expected, timeout_s,
            )
        if subscribed:
            await client.stop_notify(cmd_uuid)
        return received

    # ── Statistics import ─────────────────────────────────────────────────────

    def _import_statistics(self, records: list[ProtimeterRecord]) -> None:
        """
        Import records as HA long-term statistics (external, source=DOMAIN).

        Records are grouped into hourly buckets (mean/min/max per hour).
        Existing statistics for the same hour are overwritten, so the
        overlap re-reads are harmless.

        Note: HA 2026.x does not allow custom integrations to use
        source="homeassistant", so statistics cannot be entity-linked.
        Use a statistics-graph card with the statistic IDs to visualise history.

        Device timestamps are interpreted as being in HA's configured timezone.
        """
        try:
            from homeassistant.components.recorder.models import (  # noqa: PLC0415
                StatisticData,
                StatisticMetaData,
            )
            from homeassistant.components.recorder.statistics import (  # noqa: PLC0415
                async_add_external_statistics,
            )
        except ImportError:
            _LOGGER.warning(
                "Protimeter %s: recorder not available, skipping statistics import",
                self.address,
            )
            return

        device_name = self._entry.data.get("name", self.address)
        addr_slug = self.address.lower().replace(":", "")

        # (key, unit, human label)
        sensors: list[tuple[str, str, str]] = [
            ("humidity",    PERCENTAGE,                 "Humidity"),
            ("temperature", UnitOfTemperature.CELSIUS, "Temperature"),
            ("wme",         PERCENTAGE,                 "Wood Moisture Equivalent"),
            ("battery",     PERCENTAGE,                 "Battery"),
        ]

        # Group values by (sensor_key → hour_start_utc → [values])
        hourly: dict[str, dict[datetime, list[float]]] = {
            key: defaultdict(list) for key, *_ in sensors
        }
        skipped = 0
        for rec in records:
            try:
                naive_local = datetime(
                    rec.year, rec.month, rec.day,
                    rec.hour, rec.minute, rec.second,
                )
                # Interpret device clock as HA's configured timezone
                local_aware = naive_local.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
                utc_ts = dt_util.as_utc(local_aware)
                hour_start = utc_ts.replace(minute=0, second=0, microsecond=0)
            except (ValueError, OverflowError):
                skipped += 1
                continue

            hourly["humidity"][hour_start].append(rec.humidity)
            hourly["temperature"][hour_start].append(rec.temperature)
            hourly["wme"][hour_start].append(rec.wme)
            hourly["battery"][hour_start].append(float(rec.battery))

        if skipped:
            _LOGGER.warning(
                "Protimeter %s: skipped %d records with invalid timestamps",
                self.address, skipped,
            )

        for key, unit, label in sensors:
            stats = [
                StatisticData(
                    start=hour_start,
                    mean=sum(vals) / len(vals),
                    min=min(vals),
                    max=max(vals),
                )
                for hour_start, vals in sorted(hourly[key].items())
                if vals
            ]
            if not stats:
                continue

            statistic_id = f"{DOMAIN}:{addr_slug}_{key}"

            # Build metadata — try both old (has_mean) and new (mean_type) API
            try:
                from homeassistant.components.recorder.statistics import (  # noqa: PLC0415
                    StatisticMeanType,
                )
                metadata = StatisticMetaData(
                    source=DOMAIN,
                    statistic_id=statistic_id,
                    name=f"{device_name} {label}",
                    unit_of_measurement=unit,
                    unit_class=None,
                    mean_type=StatisticMeanType.ARITHMETIC,
                    has_sum=False,
                )
            except (ImportError, TypeError):
                try:
                    metadata = StatisticMetaData(
                        source=DOMAIN,
                        statistic_id=statistic_id,
                        name=f"{device_name} {label}",
                        unit_of_measurement=unit,
                        unit_class=None,
                        has_mean=True,
                        has_sum=False,
                    )
                except TypeError:
                    _LOGGER.warning(
                        "Protimeter %s: could not build StatisticMetaData for %s "
                        "(unsupported HA recorder API version)",
                        self.address, key,
                    )
                    continue

            async_add_external_statistics(self.hass, metadata, stats)
            _LOGGER.debug(
                "Protimeter %s: imported %d hourly %s statistics",
                self.address, len(stats), key,
            )
