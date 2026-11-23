"""Tests for the SQLite load: re-runs don't duplicate, a failed load saves nothing."""
import sqlite3
from contextlib import closing
from datetime import date, datetime, timezone

import numpy as np
import pandas as pd
import pytest

from weatherflow.load import build_dim_date, count_rows, load, to_sql_value, write_parquet
from weatherflow.transform import transform

RUN_TIME = datetime(2026, 11, 23, 10, 30, tzinfo=timezone.utc)


@pytest.fixture
def weather_df(test_config, codes, payload_factory) -> pd.DataFrame:
    """5 cities x 48 hours, transformed and ready to load (240 rows)."""
    raw = [(city["name"], payload_factory()) for city in test_config["cities"]]
    return transform(raw, codes, RUN_TIME)


def query(db_path, sql):
    """Run one SELECT on the test database and return all rows."""
    with closing(sqlite3.connect(db_path)) as conn:
        return conn.execute(sql).fetchall()


def test_load_writes_every_row(weather_df, test_config):
    assert load(weather_df, test_config) == 240
    assert count_rows(test_config["paths"]["database"]) == 240
    assert query(test_config["paths"]["database"], "SELECT COUNT(*) FROM dim_city") == [(5,)]


def test_loading_twice_does_not_duplicate_rows(weather_df, test_config):
    load(weather_df, test_config)
    load(weather_df, test_config)
    assert count_rows(test_config["paths"]["database"]) == 240


def test_rerun_updates_values_in_place(weather_df, test_config):
    load(weather_df, test_config)
    weather_df["temperature_c"] = 11.0
    load(weather_df, test_config)
    db = test_config["paths"]["database"]
    assert count_rows(db) == 240
    assert query(db, "SELECT DISTINCT temperature_c FROM fact_weather_hourly") == [(11.0,)]


def test_failed_load_saves_nothing(weather_df, test_config):
    weather_df.loc[120, "outdoor_work_risk"] = "extreme"     # breaks the CHECK constraint
    with pytest.raises(sqlite3.IntegrityError):
        load(weather_df, test_config)
    db = test_config["paths"]["database"]
    assert count_rows(db) == 0
    assert query(db, "SELECT COUNT(*) FROM dim_city") == [(0,)]   # dimensions rolled back too


def test_dim_date_has_one_row_per_day_and_marks_weekends():
    dates = build_dim_date(date(2026, 11, 21), date(2026, 11, 23))     # Sat, Sun, Mon
    assert dates["date_id"].tolist() == [20261121, 20261122, 20261123]
    assert dates["day_of_week"].tolist() == [6, 7, 1]
    assert dates["is_weekend"].tolist() == [1, 1, 0]


@pytest.mark.parametrize("value, expected", [
    (pd.NA, None),
    (float("nan"), None),
    (np.int64(5), 5),
    (np.float64(2.5), 2.5),
    (np.bool_(True), 1),
    (pd.Timestamp("2026-11-23 09:00", tz="UTC"), "2026-11-23T09:00:00+00:00"),
])
def test_to_sql_value_gives_plain_python_values(value, expected):
    converted = to_sql_value(value)
    assert converted == expected
    assert type(converted) is type(expected)


def test_parquet_goes_into_a_run_date_folder(weather_df, tmp_path):
    path = write_parquet(weather_df, tmp_path, RUN_TIME)
    assert path.parent.name == "run_date=2026-11-23"
    assert len(pd.read_parquet(path)) == 240