"""Extract: call Open-Meteo for each city and land the raw JSON unchanged."""
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Use the operating system's certificate store for HTTPS (antivirus re-signs
# HTTPS traffic on some machines). Verification stays switched on.
import truststore

truststore.inject_into_ssl()

import requests  # noqa: E402  (must come after inject_into_ssl)

logger = logging.getLogger(__name__)


class ExtractError(Exception):
    """Raised when a request fails after every retry, or must not be retried."""


def get_with_retries(url: str, params: dict[str, Any], timeout: float, max_retries: int) -> dict[str, Any]:
    """GET a URL and return its JSON, retrying timeouts, connection errors and 5xx.

    After the first try it retries up to max_retries times, waiting 1s, 2s, 4s...
    A 4xx answer (a mistake on our side, such as a bad parameter) is never retried.
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


def build_forecast_params(city: dict[str, Any], api: dict[str, Any]) -> dict[str, Any]:
    """Query parameters for the Open-Meteo forecast API, with times in UTC."""
    return {
        "latitude": city["latitude"],
        "longitude": city["longitude"],
        "hourly": ",".join(api["hourly_variables"]),
        "past_days": api["past_days"],
        "forecast_days": api["forecast_days"],
        "timezone": api["timezone"],
    }


def save_raw(raw_dir: Path, city_name: str, payload: dict[str, Any], run_time: datetime) -> Path:
    """Write the payload unchanged to raw_dir/<YYYY-MM-DD>/<city>_<timestamp>.json.

    run_time must be in UTC. Mode "x" refuses to overwrite an existing file.
    """
    folder = raw_dir / run_time.strftime("%Y-%m-%d")
    folder.mkdir(parents=True, exist_ok=True)
    slug = city_name.lower().replace(" ", "_")
    path = folder / f"{slug}_{run_time.strftime('%Y%m%dT%H%M%S')}.json"
    with open(path, "x", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return path


def extract(config: dict[str, Any], run_time: datetime | None = None) -> tuple[list[tuple[str, dict]], list[str]]:
    """Fetch and land every configured city.

    Returns (results, failed): results holds (city name, payload) pairs, and
    failed lists the cities that still failed after retries. One failing city
    does not stop the others.
    """
    run_time = run_time or datetime.now(timezone.utc)
    api = config["api"]
    results, failed = [], []
    for city in config["cities"]:
        name = city["name"]
        try:
            params = build_forecast_params(city, api)
            payload = get_with_retries(api["forecast_url"], params, api["timeout_seconds"], api["max_retries"])
            path = save_raw(config["paths"]["raw_dir"], name, payload, run_time)
        except (ExtractError, requests.RequestException, OSError) as error:
            logger.error("%s failed: %s", name, error)
            failed.append(name)
            continue
        logger.info("%s: %d hourly records -> %s", name, len(payload["hourly"]["time"]), path.name)
        results.append((name, payload))
    logger.info("Extract finished: %d of %d cities landed", len(results), len(config["cities"]))
    return results, failed