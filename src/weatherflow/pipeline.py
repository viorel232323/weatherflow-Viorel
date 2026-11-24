"""Pipeline: extract -> transform -> validate -> load, for incremental runs and backfills."""
import logging
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

from weatherflow.extract import HOUR_FORMAT, extract, extract_archive
from weatherflow.load import count_rows, load, read_watermark, write_parquet
from weatherflow.reference import read_wmo_codes
from weatherflow.transform import transform
from weatherflow.validate import DataQualityError, validate, write_dq_report, write_quarantine

logger = logging.getLogger(__name__)
FORECAST = "open_meteo_forecast"
ARCHIVE = "open_meteo_archive"
ONE_HOUR = timedelta(hours=1)


def incremental_window(config: dict[str, Any], now: datetime) -> tuple[datetime, datetime]:
    """The hours the next run should fetch, as (first hour, last hour) in UTC.

    Each city's watermark is the latest hour already loaded, up to now. The window
    starts overlap_hours before the earliest watermark (a city with no data falls back
    to past_days) and ends at the last forecast hour, so forecasts are refreshed.
    """
    api = config["api"]
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    fallback = midnight - timedelta(days=api["past_days"])
    last_hour = midnight + timedelta(days=api["forecast_days"]) - ONE_HOUR
    starts = []
    for city in config["cities"]:
        mark = read_watermark(config["paths"]["database"], city["name"], FORECAST, now)
        logger.info("%s watermark: %s", city["name"], mark.strftime(HOUR_FORMAT) if mark else "none, use past_days")
        starts.append(mark - timedelta(hours=api["overlap_hours"]) if mark else fallback)
    return min(starts), last_hour


def backfill_range(today: date, days: int, lag_days: int,
                   start: date | None = None, end: date | None = None) -> tuple[date, date]:
    """The first and last day to backfill. By default: `days` days, ending lag_days before today."""
    end = end or today - timedelta(days=lag_days)
    start = start or end - timedelta(days=days - 1)
    if start > end:
        raise ValueError(f"start date {start} is after end date {end}")
    return start, end


def process_and_load(raw: list[tuple[str, dict]], failed: list[str], config: dict[str, Any],
                     run_time: datetime, source: str, expected_hours: int, check_timeliness: bool) -> int:
    """The path shared by run and backfill: transform -> validate -> load. Return the exit code."""
    paths = config["paths"]
    if not raw:
        logger.error("No city could be extracted, so nothing was loaded")
        return 1

    df = transform(raw, read_wmo_codes(), run_time, source)
    try:
        good, quarantined, results = validate(df, config, expected_hours, run_time, check_timeliness)
    except DataQualityError as error:
        write_dq_report(error.results, 0, run_time, paths["dq_report_dir"])
        logger.error("Load stopped, nothing loaded: %s", error)
        return 1
    write_quarantine(quarantined, paths["quarantine_dir"], run_time)
    write_dq_report(results, len(quarantined), run_time, paths["dq_report_dir"])

    write_parquet(good, paths["processed_dir"], run_time)
    load(good, config)
    logger.info("Table now holds %d rows", count_rows(paths["database"]))

    if failed:
        logger.error("Run incomplete: %d city(ies) failed: %s", len(failed), ", ".join(failed))
        return 1
    return 0


def run(config: dict[str, Any], now: datetime | None = None) -> int:
    """Incremental run: fetch from each city's watermark to the end of the forecast, and load it."""
    started = time.perf_counter()
    run_time = now or datetime.now(timezone.utc)
    logger.info("Run started at %s UTC", run_time.strftime("%Y-%m-%d %H:%M:%S"))

    window = incremental_window(config, run_time)
    expected_hours = int((window[1] - window[0]) / ONE_HOUR) + 1
    logger.info("Requesting %s to %s UTC (%d hours per city)",
                window[0].strftime(HOUR_FORMAT), window[1].strftime(HOUR_FORMAT), expected_hours)
    raw, failed = extract(config, run_time, window)

    code = process_and_load(raw, failed, config, run_time, FORECAST, expected_hours, check_timeliness=True)
    logger.info("Run finished with exit code %d in %.1f s", code, time.perf_counter() - started)
    return code


def backfill(config: dict[str, Any], start: date, end: date, now: datetime | None = None) -> int:
    """Load whole days start..end from the archive API, through the same path as run."""
    started = time.perf_counter()
    run_time = now or datetime.now(timezone.utc)
    expected_hours = ((end - start).days + 1) * 24
    logger.info("Backfill started: %s to %s (%d hours per city)", start, end, expected_hours)

    raw, failed = extract_archive(config, start, end, run_time)

    # Old data is never "recent", so the timeliness check is switched off; completeness still applies.
    code = process_and_load(raw, failed, config, run_time, ARCHIVE, expected_hours, check_timeliness=False)
    logger.info("Backfill finished with exit code %d in %.1f s", code, time.perf_counter() - started)
    return code