"""Transform: turn raw Open-Meteo payloads into one clean table (one row per city per hour).

Every function here is pure: it takes data and returns data. Nothing here reads
files, calls APIs or writes to the database.
"""
import numpy as np
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

# Beaufort scale: lower bound of each force in m/s (WMO table). Force 0 starts at 0 m/s.
BEAUFORT_LOWER_BOUNDS_MS = [0, 0.3, 1.6, 3.4, 5.5, 8.0, 10.8, 13.9, 17.2, 20.8, 24.5, 28.5, 32.7]
HIGH_RISK_CATEGORIES = ["storm", "snow"]


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

def add_weather_description(df: pd.DataFrame, codes: pd.DataFrame) -> pd.DataFrame:
    """Join the WMO description and category. Codes not in the table become "unknown"."""
    df = df.merge(codes, on="weather_code", how="left")
    for column in ["weather_description", "weather_category"]:
        df[column] = df[column].fillna("unknown")
    return df


def beaufort_scale(wind_speed_ms: pd.Series) -> pd.Series:
    """Beaufort force 0-12 from wind speed in m/s. A value exactly on a bound gets the higher force."""
    bins = BEAUFORT_LOWER_BOUNDS_MS + [float("inf")]
    return pd.cut(wind_speed_ms, bins=bins, right=False, labels=False).astype("Int64")


def outdoor_work_risk(beaufort: pd.Series, category: pd.Series,
                      precipitation_mm: pd.Series, temperature_c: pd.Series) -> pd.Series:
    """Return "high", "medium" or "low" for each row, following the rules in the data dictionary."""
    high = ((beaufort >= 7) | category.isin(HIGH_RISK_CATEGORIES) | (precipitation_mm >= 4)).fillna(False)
    medium = ((beaufort >= 5) | (precipitation_mm >= 1) | (temperature_c <= 0)).fillna(False)
    labels = np.select([high.to_numpy(dtype=bool), medium.to_numpy(dtype=bool)],
                       ["high", "medium"], default="low")
    return pd.Series(labels, index=beaufort.index)


def add_derived_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """Add temperature_f, wind_speed_ms, beaufort_scale, is_daylight and outdoor_work_risk."""
    df = df.copy()
    df["temperature_f"] = df["temperature_c"] * 9 / 5 + 32
    df["wind_speed_ms"] = (df["wind_speed_kmh"] / 3.6).round(2)
    df["beaufort_scale"] = beaufort_scale(df["wind_speed_ms"])
    df["is_daylight"] = df["is_day"] == 1
    df["outdoor_work_risk"] = outdoor_work_risk(df["beaufort_scale"], df["weather_category"],
                                                df["precipitation_mm"], df["temperature_c"])
    return df


def deduplicate(df: pd.DataFrame) -> pd.DataFrame:
    """Keep one row per city and hour: the most recently ingested one."""
    return (
        df.sort_values("ingested_at_utc")
        .drop_duplicates(subset=["city", "observed_at_utc"], keep="last")
        .sort_values(["city", "observed_at_utc"])
        .reset_index(drop=True)
    )


def transform(raw: list[tuple[str, dict]], codes: pd.DataFrame, run_time: datetime | None = None) -> pd.DataFrame:
    """Run every transform step in order and return the clean table."""
    run_time = run_time or datetime.now(timezone.utc)
    if not raw:
        return pd.DataFrame()
    df = pd.concat([flatten_payload(payload, city) for city, payload in raw], ignore_index=True)
    df = standardise_columns(df)
    df = add_weather_description(df, codes)
    df = add_derived_metrics(df)
    df["ingested_at_utc"] = pd.Timestamp(run_time)
    df = deduplicate(df)
    logger.info("Transform finished: %d rows, %d cities", len(df), df["city"].nunique())
    return df