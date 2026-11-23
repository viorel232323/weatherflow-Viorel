"""Load: write the star schema (dim_city, dim_date, fact_weather_hourly) into SQLite.

Dimensions and facts are written in ONE transaction: if anything fails, nothing
is saved. Facts are upserted on (city_id, observed_at_utc, source), so running
the load again updates rows instead of duplicating them.
"""
import logging
import sqlite3
from contextlib import closing
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

FACT_COLUMNS = [
    "city_id", "date_id", "observed_at_utc", "observed_at_local", "hour_local",
    "temperature_c", "feels_like_c", "temperature_f", "humidity_pct", "precipitation_mm",
    "wind_speed_kmh", "wind_speed_ms", "beaufort_scale", "weather_code",
    "weather_description", "weather_category", "is_daylight", "outdoor_work_risk",
    "source", "ingested_at_utc",
]
FACT_KEY = ["city_id", "observed_at_utc", "source"]

UPSERT_FACT_SQL = (
    f"INSERT INTO fact_weather_hourly ({', '.join(FACT_COLUMNS)}) "
    f"VALUES ({', '.join('?' for _ in FACT_COLUMNS)}) "
    f"ON CONFLICT ({', '.join(FACT_KEY)}) DO UPDATE SET "
    + ", ".join(f"{column} = excluded.{column}" for column in FACT_COLUMNS if column not in FACT_KEY)
)
UPSERT_CITY_SQL = """
    INSERT INTO dim_city (city_name, country, latitude, longitude) VALUES (?, ?, ?, ?)
    ON CONFLICT (city_name) DO UPDATE SET
        country = excluded.country, latitude = excluded.latitude, longitude = excluded.longitude
"""
INSERT_DATE_SQL = """
    INSERT INTO dim_date (date_id, full_date, year, month, month_name, day, day_of_week, day_name, is_weekend)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT (date_id) DO NOTHING
"""


def to_sql_value(value: Any) -> Any:
    """Convert a pandas/numpy value to a plain Python value that SQLite can store."""
    if value is None or value is pd.NA or (isinstance(value, float) and np.isnan(value)):
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()  # e.g. 2026-11-22T00:00:00+00:00
    if isinstance(value, (bool, np.bool_)):
        return int(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    return value


def to_rows(df: pd.DataFrame) -> list[tuple]:
    """Turn every DataFrame row into a tuple of plain Python values."""
    return [tuple(to_sql_value(v) for v in row) for row in df.itertuples(index=False, name=None)]


def build_dim_date(start: date, end: date) -> pd.DataFrame:
    """One row per calendar day from start to end, inclusive."""
    days = pd.date_range(start, end, freq="D")
    return pd.DataFrame({
        "date_id": days.strftime("%Y%m%d").astype(int),
        "full_date": days.strftime("%Y-%m-%d"),
        "year": days.year,
        "month": days.month,
        "month_name": days.strftime("%B"),
        "day": days.day,
        "day_of_week": days.day_of_week + 1,  # pandas counts Monday as 0
        "day_name": days.strftime("%A"),
        "is_weekend": (days.day_of_week >= 5).astype(int),
    })


def build_fact_rows(df: pd.DataFrame, city_ids: dict[str, int]) -> list[tuple]:
    """Add city_id, date_id (the London date) and hour_local, and return the fact rows."""
    facts = df.copy()
    facts["city_id"] = facts["city"].map(city_ids)
    facts["date_id"] = facts["observed_at_local"].dt.strftime("%Y%m%d").astype(int)
    facts["hour_local"] = facts["observed_at_local"].dt.hour
    return to_rows(facts[FACT_COLUMNS])


def apply_schema(conn: sqlite3.Connection, schema_file: Path) -> None:
    """Create the tables if they don't exist yet."""
    conn.executescript(schema_file.read_text(encoding="utf-8"))


def load(df: pd.DataFrame, config: dict[str, Any]) -> int:
    """Upsert cities, dates and facts in one transaction. Return the number of fact rows written."""
    db_path = config["paths"]["database"]
    db_path.parent.mkdir(parents=True, exist_ok=True)
    dim_date = build_dim_date(config["dim_date"]["start"], config["dim_date"]["end"])
    cities = [(c["name"], c["country"], c["latitude"], c["longitude"]) for c in config["cities"]]

    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute("PRAGMA foreign_keys = ON")  # SQLite only checks foreign keys when asked
        apply_schema(conn, config["paths"]["schema"])
        with conn:  # one transaction: dimensions and facts are all saved, or none are
            conn.executemany(UPSERT_CITY_SQL, cities)
            conn.executemany(INSERT_DATE_SQL, to_rows(dim_date))
            city_ids = dict(conn.execute("SELECT city_name, city_id FROM dim_city").fetchall())
            rows = build_fact_rows(df, city_ids)
            conn.executemany(UPSERT_FACT_SQL, rows)
    logger.info("Loaded %d fact rows into %s", len(rows), db_path.name)
    return len(rows)


def count_rows(db_path: Path) -> int:
    """Total rows in fact_weather_hourly, used to prove that re-runs add no duplicates."""
    with closing(sqlite3.connect(db_path)) as conn:
        return conn.execute("SELECT COUNT(*) FROM fact_weather_hourly").fetchone()[0]


def write_parquet(df: pd.DataFrame, processed_dir: Path, run_time: datetime) -> Path:
    """Save df as processed_dir/weather_hourly/run_date=<YYYY-MM-DD>/part-<timestamp>.parquet."""
    folder = processed_dir / "weather_hourly" / f"run_date={run_time:%Y-%m-%d}"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"part-{run_time:%Y%m%dT%H%M%S}.parquet"
    df.to_parquet(path, index=False)
    logger.info("Wrote %d rows to %s", len(df), path.relative_to(processed_dir))
    return path