"""Transform: turn raw Open-Meteo payloads into one clean table (one row per city per hour).

Every function here is pure: it takes data and returns data. Nothing here reads
files, calls APIs or writes to the database.
"""
import logging
from datetime import datetime, timezone

import pandas as pd

logger = logging.getLogger(__name__)

# API name -> clear snake_case name with its unit
COLUMN_MAP = {
    "time": "observed_at_utc",
    "temperature_2m": "temperature_c",
    "apparent_temperature": "feels_like_c",
    "relative_humidity_2m": "humidity_pct",
    "precipitation": "precipitation_mm",
    "wind_speed_10m": "wind_speed_kmh",
    "weather_code": "weather_code",
    "is_day": "is_day",
}
LOCAL_TIMEZONE = "Europe/London"


def flatten_payload(payload: dict, city: str) -> pd.DataFrame:
    """Turn one Open-Meteo response into a table with one row per hour."""
    df = pd.DataFrame(payload["hourly"])
    df["city"] = city
    return df


def standardise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename to clear names, set types, and add London local time next to UTC."""
    df = df.rename(columns=COLUMN_MAP)
    df["observed_at_utc"] = pd.to_datetime(df["observed_at_utc"], utc=True)
    df["observed_at_local"] = df["observed_at_utc"].dt.tz_convert(LOCAL_TIMEZONE)
    for column in ["humidity_pct", "weather_code", "is_day"]:
        df[column] = df[column].astype("Int64")
    return df


def deduplicate(df: pd.DataFrame) -> pd.DataFrame:
    """Keep one row per city and hour: the most recently ingested one."""
    return (
        df.sort_values("ingested_at_utc")
        .drop_duplicates(subset=["city", "observed_at_utc"], keep="last")
        .sort_values(["city", "observed_at_utc"])
        .reset_index(drop=True)
    )


def transform(raw: list[tuple[str, dict]], run_time: datetime | None = None) -> pd.DataFrame:
    """Run every transform step in order and return the clean table."""
    run_time = run_time or datetime.now(timezone.utc)
    if not raw:
        return pd.DataFrame()
    df = pd.concat([flatten_payload(payload, city) for city, payload in raw], ignore_index=True)
    df = standardise_columns(df)
    df["ingested_at_utc"] = pd.Timestamp(run_time)
    df = deduplicate(df)
    logger.info("Transform finished: %d rows, %d cities", len(df), df["city"].nunique())
    return df