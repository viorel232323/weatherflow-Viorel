"""Load: write the clean table into SQLite in one transaction, safe to re-run."""
import logging
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

COLUMNS = ["city", "observed_at_utc", "observed_at_local", "temperature_c", "feels_like_c",
           "humidity_pct", "precipitation_mm", "wind_speed_kmh", "weather_code", "is_day",
           "ingested_at_utc"]

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS weather_hourly (
    city              TEXT    NOT NULL,
    observed_at_utc   TEXT    NOT NULL,
    observed_at_local TEXT    NOT NULL,
    temperature_c     REAL,
    feels_like_c      REAL,
    humidity_pct      INTEGER,
    precipitation_mm  REAL,
    wind_speed_kmh    REAL,
    weather_code      INTEGER,
    is_day            INTEGER,
    ingested_at_utc   TEXT    NOT NULL,
    PRIMARY KEY (city, observed_at_utc)
);
"""

# If a (city, hour) row already exists, it is replaced, so re-running never duplicates.
INSERT_SQL = (
    f"INSERT OR REPLACE INTO weather_hourly ({', '.join(COLUMNS)}) "
    f"VALUES ({', '.join('?' for _ in COLUMNS)})"
)


def to_sql_value(value: Any) -> Any:
    """Convert a pandas/numpy value to a plain Python value that SQLite can store."""
    if value is None or value is pd.NA or (isinstance(value, float) and np.isnan(value)):
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()  # e.g. 2026-11-22T00:00:00+00:00
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    return value


def load(df: pd.DataFrame, db_path: Path) -> int:
    """Write df into weather_hourly in one transaction. Return the number of rows written."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [tuple(to_sql_value(v) for v in record)
            for record in df[COLUMNS].itertuples(index=False, name=None)]
    with closing(sqlite3.connect(db_path)) as conn:
        with conn:  # one transaction: all rows are saved, or none are
            conn.execute(CREATE_TABLE_SQL)
            conn.executemany(INSERT_SQL, rows)
    logger.info("Loaded %d rows into %s", len(rows), db_path.name)
    return len(rows)


def count_rows(db_path: Path) -> int:
    """Total rows in weather_hourly, used to prove that re-runs add no duplicates."""
    with closing(sqlite3.connect(db_path)) as conn:
        return conn.execute("SELECT COUNT(*) FROM weather_hourly").fetchone()[0]


def write_parquet(df: pd.DataFrame, processed_dir: Path, run_time: datetime) -> Path:
    """Save df as processed_dir/weather_hourly/run_date=<YYYY-MM-DD>/part-<timestamp>.parquet."""
    folder = processed_dir / "weather_hourly" / f"run_date={run_time:%Y-%m-%d}"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"part-{run_time:%Y%m%dT%H%M%S}.parquet"
    df.to_parquet(path, index=False)
    logger.info("Wrote %d rows to %s", len(df), path.relative_to(processed_dir))
    return path