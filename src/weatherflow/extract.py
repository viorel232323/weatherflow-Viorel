"""Extract: call Open-Meteo for each city and land the raw JSON unchanged."""
import json
import logging
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# Use the operating system's certificate store for HTTPS (antivirus re-signs
# HTTPS traffic on some machines). Verification stays switched on.
import truststore

truststore.inject_into_ssl()

import requests  

logger = logging.getLogger(__name__)

HOUR_FORMAT = "%Y-%m-%dT%H:%M"  # how Open-Meteo writes hours, e.g. 2026-11-24T09:00


class ExtractError(Exception):
    """Raised when a request fails after every retry, or must not be retried."""


def get_with_retries(url: str, params: dict[str, Any], timeout: float, max_retries: int) -> dict[str, Any]:
    """GET a URL and return its JSON, retrying timeouts, connection errors and 5xx.

    After the first try it retries up to max_retries times, waiting 1s, 2s, 4s...
    A 4xx answer (a mistake on my side, such as a bad parameter) is never retried.
    """
    for attempt in range(max_retries + 1):
        try:
            response = requests.get(url, params=params, timeout=timeout)
        except (requests.Timeout, requests.ConnectionError) as error:
            reason = type(error).__name__
        else:
            if response.status_code < 400:
                return response.json()
            if response.status_code < 500:
                raise ExtractError(f"HTTP {response.status_code} (not retried): {response.text[:200]}")
            reason = f"HTTP {response.status_code}"
        if attempt < max_retries:
            wait = 2 ** attempt  # 1, 2, 4 seconds
            logger.warning("%s, retry %d of %d in %ds", reason, attempt + 1, max_retries, wait)
            time.sleep(wait)
    raise ExtractError(f"{reason} after {max_retries + 1} attempts")


def build_forecast_params(city: dict[str, Any], api: dict[str, Any],
                          window: tuple[datetime, datetime] | None = None) -> dict[str, Any]:
    """Query parameters for the Open-Meteo forecast API, with times in UTC.

    Without a window: the last past_days plus the next forecast_days.
    With a window (first hour, last hour): exactly those hours, for an incremental run.
    """
    params = {
        "latitude": city["latitude"],
        "longitude": city["longitude"],
        "hourly": ",".join(api["hourly_variables"]),
        "timezone": api["timezone"],
    }
    if window is None:
        params["past_days"] = api["past_days"]
        params["forecast_days"] = api["forecast_days"]
    else:
        params["start_hour"] = window[0].strftime(HOUR_FORMAT)
        params["end_hour"] = window[1].strftime(HOUR_FORMAT)
    return params


def build_archive_params(city: dict[str, Any], api: dict[str, Any], start: date, end: date) -> dict[str, Any]:
    """Query parameters for the Open-Meteo historical (archive) API: whole days from start to end, in UTC."""
    return {
        "latitude": city["latitude"],
        "longitude": city["longitude"],
        "hourly": ",".join(api["hourly_variables"]),
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "timezone": api["timezone"],
    }


def date_chunks(start: date, end: date, days: int) -> list[tuple[date, date]]:
    """Split start..end (both included) into (first day, last day) chunks of at most `days` days."""
    chunks = []
    first = start
    while first <= end:
        last = min(first + timedelta(days=days - 1), end)
        chunks.append((first, last))
        first = last + timedelta(days=1)
    return chunks


def save_raw(raw_dir: Path, city_name: str, payload: dict[str, Any], run_time: datetime, tag: str = "") -> Path:
    """Write the payload unchanged to raw_dir/<YYYY-MM-DD>/<city>[_<tag>]_<timestamp>.json.

    run_time must be in UTC. The tag tells backfill chunks apart (e.g. "archive_20261021").
    Mode "x" refuses to overwrite an existing file.
    """
    folder = raw_dir / run_time.strftime("%Y-%m-%d")
    folder.mkdir(parents=True, exist_ok=True)
    slug = city_name.lower().replace(" ", "_")
    name = f"{slug}_{tag}" if tag else slug
    path = folder / f"{name}_{run_time.strftime('%Y%m%dT%H%M%S')}.json"
    with open(path, "x", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return path


def fetch_and_land(url: str, params: dict[str, Any], config: dict[str, Any], city_name: str,
                   run_time: datetime, tag: str = "") -> dict[str, Any]:
    """Call the API (with retries), save the raw JSON, and return the payload."""
    api = config["api"]
    payload = get_with_retries(url, params, api["timeout_seconds"], api["max_retries"])
    path = save_raw(config["paths"]["raw_dir"], city_name, payload, run_time, tag)
    logger.info("%s: %d hourly records -> %s", city_name, len(payload["hourly"]["time"]), path.name)
    return payload


def extract(config: dict[str, Any], run_time: datetime | None = None,
            window: tuple[datetime, datetime] | None = None) -> tuple[list[tuple[str, dict]], list[str]]:
    """Fetch the forecast API for every city and land each response.

    Returns (results, failed): results holds (city name, payload) pairs, and
    failed lists the cities that still failed after retries. One failing city
    does not stop the others. window limits the request to those hours.
    """
    run_time = run_time or datetime.now(timezone.utc)
    api = config["api"]
    results, failed = [], []
    for city in config["cities"]:
        name = city["name"]
        try:
            params = build_forecast_params(city, api, window)
            payload = fetch_and_land(api["forecast_url"], params, config, name, run_time)
        except (ExtractError, requests.RequestException, OSError) as error:
            logger.error("%s failed: %s", name, error)
            failed.append(name)
            continue
        results.append((name, payload))
    logger.info("Extract finished: %d of %d cities landed", len(results), len(config["cities"]))
    return results, failed


def extract_archive(config: dict[str, Any], start: date, end: date,
                    run_time: datetime | None = None) -> tuple[list[tuple[str, dict]], list[str]]:
    """Fetch the archive API for every city in chunks, and land each chunk.

    Returns (results, failed) like extract(), with one (city, payload) pair per chunk.
    If any chunk of a city fails, none of that city's chunks are returned.
    """
    run_time = run_time or datetime.now(timezone.utc)
    api = config["api"]
    chunks = date_chunks(start, end, api["backfill_chunk_days"])
    logger.info("Backfill %s to %s: %d chunk(s) per city", start, end, len(chunks))
    results, failed = [], []
    for city in config["cities"]:
        name = city["name"]
        city_results = []
        try:
            for first, last in chunks:
                params = build_archive_params(city, api, first, last)
                payload = fetch_and_land(api["archive_url"], params, config, name, run_time,
                                         tag=f"archive_{first:%Y%m%d}")
                city_results.append((name, payload))
                time.sleep(api["request_pause_seconds"])  #free API limit
        except (ExtractError, requests.RequestException, OSError) as error:
            logger.error("%s failed: %s", name, error)
            failed.append(name)
            continue
        results.extend(city_results)
    logger.info("Backfill extract finished: %d of %d cities landed",
                len(config["cities"]) - len(failed), len(config["cities"]))
    return results, failed