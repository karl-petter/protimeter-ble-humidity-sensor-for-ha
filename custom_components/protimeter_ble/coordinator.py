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
    CMD_READ_COUNT,
    COMMAND_CHAR_UUID,
    CONF_FETCH_INTERVAL_DAYS,
    CONF_LAST_RECORD_ID,
    DEFAULT_FETCH_INTERVAL_DAYS,
    DOMAIN,
    HISTORY_OVERLAP,
    HISTORY_RECORD_LEN,
)
from .parser import ProtimeterRecord, build_history_request, parse_history_record

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
    def last_record_id(self) -> int | None:
        """Record ID of the last successfully imported record, or None on first run."""
        return self._entry.data.get(CONF_LAST_RECORD_ID)

    # ── DataUpdateCoordinator interface ───────────────────────────────────────

    async def _async_update_data(self) -> ProtimeterRecord | None:
        return await self._fetch_history()

    # ── BLE operations ────────────────────────────────────────────────────────

    async def _fetch_history(self) -> ProtimeterRecord | None:
        """Connect to the device and import any new history records."""
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
            count = await self._ble_read_count(client)
            if count == 0:
                _LOGGER.debug("Protimeter %s: device reports 0 records", self.address)
                return self.data

            last_id = self.last_record_id
            if last_id is None:
                # First run: read the complete history
                start = 0
            else:
                # Incremental: re-read last HISTORY_OVERLAP records to verify
                # no gap, then continue with new records
                start = max(0, last_id - HISTORY_OVERLAP + 1)

            end = count - 1
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
            records = await self._ble_read_records(client, start, end)

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

    async def _ble_read_count(self, client: BleakClient) -> int:
        """
        Send C command and return the total number of stored records.
        Response: 2-byte big-endian uint16.
        """
        result: list[int] = []
        done = asyncio.Event()

        def _handler(_sender: int, data: bytearray) -> None:
            if len(data) == 2 and not done.is_set():
                result.append(data[0] * 256 + data[1])
                done.set()

        await client.start_notify(COMMAND_CHAR_UUID, _handler)
        await client.write_gatt_char(COMMAND_CHAR_UUID, CMD_READ_COUNT, response=False)
        try:
            await asyncio.wait_for(done.wait(), timeout=BLE_RESPONSE_TIMEOUT_S)
        except asyncio.TimeoutError as exc:
            await client.stop_notify(COMMAND_CHAR_UUID)
            raise UpdateFailed(
                f"Protimeter {self.address}: timed out reading record count"
            ) from exc
        await client.stop_notify(COMMAND_CHAR_UUID)
        return result[0] if result else 0

    async def _ble_read_records(
        self, client: BleakClient, start: int, end: int
    ) -> list[ProtimeterRecord]:
        """
        Send R command and collect all records from start..end (inclusive).
        Each record arrives as a separate 20-byte notification.
        """
        expected = end - start + 1
        received: list[ProtimeterRecord] = []
        done = asyncio.Event()

        def _handler(_sender: int, data: bytearray) -> None:
            if len(data) == HISTORY_RECORD_LEN and not done.is_set():
                rec = parse_history_record(data)
                if rec is not None:
                    received.append(rec)
                    if len(received) >= expected:
                        done.set()

        # Allow 0.3 s per record (BLE is fast; this is very conservative)
        timeout_s = min(300.0, 30.0 + expected * 0.3)

        await client.start_notify(COMMAND_CHAR_UUID, _handler)
        await client.write_gatt_char(
            COMMAND_CHAR_UUID,
            build_history_request(start, end),
            response=False,
        )
        try:
            await asyncio.wait_for(done.wait(), timeout=timeout_s)
        except asyncio.TimeoutError:
            _LOGGER.warning(
                "Protimeter %s: received %d/%d records before timeout "
                "(%.0f s); proceeding with partial data",
                self.address, len(received), expected, timeout_s,
            )
        await client.stop_notify(COMMAND_CHAR_UUID)
        return received

    # ── Statistics import ─────────────────────────────────────────────────────

    def _import_statistics(self, records: list[ProtimeterRecord]) -> None:
        """
        Import records as HA long-term statistics.

        Records are grouped into hourly buckets (mean/min/max per hour).
        Existing statistics for the same hour are overwritten, so the
        overlap re-reads are harmless.

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

        addr_slug = self.address.lower().replace(":", "")
        device_name = self._entry.data.get("name", self.address)

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
            statistic_id = f"{DOMAIN}:{addr_slug}_{key}"
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
