"""Extract: call Open-Meteo for each city and land the raw JSON unchanged.

Run:  python extract.py

Each run writes one file per city to
    data/raw/<YYYY-MM-DD>/<city>_<YYYYMMDDTHHMMSS>.json
where the date and timestamp are the run time in UTC.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

# Use the operating system's certificate store for HTTPS. On machines where
# antivirus or a corporate proxy re-signs HTTPS traffic, requests' own
# certificate bundle fails; the OS store has the right root certificate.
# Verification stays switched on.
import truststore

truststore.inject_into_ssl()

import requests  # noqa: E402  (must come after inject_into_ssl)

BASE_URL = "https://api.open-meteo.com/v1/forecast"
PROJECT_ROOT = Path(__file__).resolve().parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"

HOURLY_VARIABLES = [
    "temperature_2m",
    "relative_humidity_2m",
    "apparent_temperature",
    "precipitation",
    "wind_speed_10m",
    "weather_code",
]

# Coordinates from the Open-Meteo Geocoding API, for example
# https://geocoding-api.open-meteo.com/v1/search?name=Manchester&count=1&country=GB
CITIES = [
    {"name": "London", "latitude": 51.50853, "longitude": -0.12574},
    {"name": "Manchester", "latitude": 53.48095, "longitude": -2.23743},
    {"name": "Birmingham", "latitude": 52.48142, "longitude": -1.89983},
    {"name": "Edinburgh", "latitude": 55.95206, "longitude": -3.19648},
    {"name": "Cardiff", "latitude": 51.48, "longitude": -3.18},
]


def fetch_city(city: dict) -> dict:
    """Call the forecast API for one city and return the parsed JSON."""
    params = {
        "latitude": city["latitude"],
        "longitude": city["longitude"],
        "hourly": ",".join(HOURLY_VARIABLES),
        "past_days": 1,
        "forecast_days": 1,
        "timezone": "Europe/London",
    }
    response = requests.get(BASE_URL, params=params, timeout=10)
    response.raise_for_status()
    return response.json()


def save_raw(city_name: str, payload: dict, run_time: datetime | None = None) -> Path:
    """Write the payload unchanged to data/raw/<date>/<city>_<timestamp>.json.

    run_time must be in UTC. Mode "x" refuses to overwrite an existing file,
    so a clash raises an error instead of silently replacing raw data.
    """
    now = run_time or datetime.now(timezone.utc)
    folder = RAW_DIR / now.strftime("%Y-%m-%d")
    folder.mkdir(parents=True, exist_ok=True)
    slug = city_name.lower().replace(" ", "_")
    path = folder / f"{slug}_{now.strftime('%Y%m%dT%H%M%S')}.json"
    with open(path, "x", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return path


def describe_error(error: Exception) -> str:
    """Turn an error into one readable line, including the API's reason if there is one."""
    response = getattr(error, "response", None)
    if response is not None:
        try:
            reason = response.json().get("reason", response.text)
        except ValueError:
            reason = response.text
        return f"HTTP {response.status_code}: {reason}"
    return f"{type(error).__name__}: {error}"


def run(cities: list[dict]) -> list[tuple[str, dict]]:
    """Fetch and land every city. A failing city is reported and skipped."""
    run_time = datetime.now(timezone.utc)
    results = []
    for city in cities:
        name = city["name"]
        try:
            payload = fetch_city(city)
            path = save_raw(name, payload, run_time)
        except (requests.RequestException, OSError) as error:
            print(f"  FAILED  {name:<11} {describe_error(error)}")
            continue
        records = len(payload["hourly"]["time"])
        print(f"  OK      {name:<11} {records} hourly records -> {path.relative_to(PROJECT_ROOT)}")
        results.append((name, payload))
    print(f"Extract finished: {len(results)} of {len(cities)} cities landed.")
    return results


if __name__ == "__main__":
    run(CITIES)
