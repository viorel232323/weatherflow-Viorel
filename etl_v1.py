"""Week 1 pipeline: Extract -> Transform -> Load into SQLite, in one command.

Run:
    python etl_v1.py                          # all five cities
    python etl_v1.py --cities London Cardiff  # a subset
    python etl_v1.py --db other.db            # a different database file
"""
import argparse
import sqlite3
import sys
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import extract as ex
from transform_utils import flatten

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_DB = PROJECT_ROOT / "weather.db"

# Source name -> clear snake_case name with its unit
COLUMN_MAP = {
    "time": "observed_at",
    "temperature_2m": "temperature_c",
    "apparent_temperature": "feels_like_c",
    "relative_humidity_2m": "humidity_pct",
    "precipitation": "precipitation_mm",
    "wind_speed_10m": "wind_speed_kmh",
    "weather_code": "weather_code",
}
OUTPUT_COLUMNS = [
    "city",
    "observed_at",
    "temperature_c",
    "feels_like_c",
    "humidity_pct",
    "precipitation_mm",
    "wind_speed_kmh",
    "weather_code",
    "ingested_at_utc",
]

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS weather_hourly (
    city              TEXT    NOT NULL,
    observed_at       TEXT    NOT NULL,
    temperature_c     REAL,
    feels_like_c      REAL,
    humidity_pct      INTEGER,
    precipitation_mm  REAL,
    wind_speed_kmh    REAL,
    weather_code      INTEGER,
    ingested_at_utc   TEXT    NOT NULL,
    PRIMARY KEY (city, observed_at)
);
"""

# INSERT OR REPLACE makes the load idempotent: a row whose (city, observed_at)
# already exists is replaced by the newer one instead of failing or duplicating.
INSERT_SQL = (
    f"INSERT OR REPLACE INTO weather_hourly ({', '.join(OUTPUT_COLUMNS)}) "
    f"VALUES ({', '.join('?' for _ in OUTPUT_COLUMNS)})"
)


def extract(cities: list[dict] | None = None, run_time: datetime | None = None) -> list[tuple[str, dict]]:
    """Call the API for each city, save raw JSON, return (city, payload) pairs."""
    return ex.run(cities or ex.CITIES, run_time)


def transform(raw: list[tuple[str, dict]], run_time: datetime | None = None) -> pd.DataFrame:
    """Flatten, clean and standardise."""
    if not raw:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    run_time = run_time or datetime.now(timezone.utc)

    df = pd.concat([flatten(payload, city) for city, payload in raw], ignore_index=True)
    df = df.rename(columns=COLUMN_MAP)
    df["observed_at"] = pd.to_datetime(df["observed_at"], format="%Y-%m-%dT%H:%M")
    df["ingested_at_utc"] = run_time.strftime("%Y-%m-%dT%H:%M:%SZ")
    # Integer columns use pandas' nullable Int64 so a missing value stays missing
    # instead of turning the whole column into floats.
    df["humidity_pct"] = df["humidity_pct"].astype("Int64")
    df["weather_code"] = df["weather_code"].astype("Int64")
    # Rows are in fetch order, so the last copy of a (city, hour) is the latest one.
    df = df.drop_duplicates(subset=["city", "observed_at"], keep="last")
    return df[OUTPUT_COLUMNS].sort_values(["city", "observed_at"]).reset_index(drop=True)


def _to_sql_value(value):
    """Convert pandas/numpy values to plain Python values sqlite3 can store."""
    if value is None or value is pd.NA or (isinstance(value, float) and np.isnan(value)):
        return None
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%dT%H:%M")
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    return value


def load(df: pd.DataFrame, db_path: str | Path = DEFAULT_DB) -> int:
    """Write to SQLite. Return number of rows written."""
    rows = [tuple(_to_sql_value(v) for v in record) for record in df.itertuples(index=False, name=None)]
    with closing(sqlite3.connect(db_path)) as conn:
        with conn:  # one transaction: commit if everything succeeds, roll back if anything fails
            conn.execute(CREATE_TABLE_SQL)
            cursor = conn.executemany(INSERT_SQL, rows)
            return cursor.rowcount if rows else 0


def table_summary(db_path: str | Path = DEFAULT_DB) -> pd.DataFrame:
    """Rows and time range per city currently in weather_hourly."""
    with closing(sqlite3.connect(db_path)) as conn:
        return pd.read_sql_query(
            "SELECT city, COUNT(*) AS rows, MIN(observed_at) AS first_hour, MAX(observed_at) AS last_hour "
            "FROM weather_hourly GROUP BY city ORDER BY city",
            conn,
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    names = [c["name"] for c in ex.CITIES]
    parser = argparse.ArgumentParser(description="Extract, transform and load hourly UK weather into SQLite.")
    parser.add_argument("--cities", nargs="+", metavar="CITY", help=f"cities to load (default: all). Choices: {', '.join(names)}")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="SQLite database file (default: weather.db)")
    args = parser.parse_args(argv)
    if args.cities:
        by_name = {c["name"].lower(): c for c in ex.CITIES}
        unknown = [n for n in args.cities if n.lower() not in by_name]
        if unknown:
            parser.error(f"unknown city: {', '.join(unknown)}. Choices: {', '.join(names)}")
        args.cities = [by_name[n.lower()] for n in args.cities]
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    started = time.perf_counter()
    run_time = datetime.now(timezone.utc)
    print(f"WeatherFlow ETL v1 · run at {run_time:%Y-%m-%d %H:%M:%S} UTC")

    print("[1/3] Extract")
    raw = extract(args.cities, run_time)
    if not raw:
        print("No city could be extracted, so nothing was loaded.")
        return 1

    print("[2/3] Transform")
    df = transform(raw, run_time)
    print(f"  {len(df)} rows after cleaning ({df['city'].nunique()} cities)")

    print("[3/3] Load")
    rows = load(df, args.db)
    print(f"Loaded {rows} rows into {Path(args.db).name}, table weather_hourly")

    print("\nRows per city now in the table:")
    print(table_summary(args.db).to_string(index=False))
    print(f"\nRun time: {time.perf_counter() - started:.1f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
