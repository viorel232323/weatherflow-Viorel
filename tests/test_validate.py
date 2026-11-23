"""Tests for the data quality checks: what is quarantined, what blocks the load, what only warns."""
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from weatherflow.transform import transform
from weatherflow.validate import DataQualityError, validate, write_dq_report, write_quarantine

RUN_TIME = datetime(2026, 11, 23, 10, 30, tzinfo=timezone.utc)
HOURS = 48


@pytest.fixture
def clean_df(test_config, codes, payload_factory) -> pd.DataFrame:
    """5 cities x 48 calm hours, already transformed: every check should pass."""
    raw = [(city["name"], payload_factory(HOURS)) for city in test_config["cities"]]
    return transform(raw, codes, RUN_TIME)


def result(results, name):
    """Find one check's result by its name."""
    return next(r for r in results if r.name == name)


def test_clean_data_passes_every_check(clean_df, test_config):
    good, quarantined, results = validate(clean_df, test_config, HOURS, RUN_TIME)
    assert len(good) == 240
    assert quarantined.empty
    assert len(results) == 9
    assert all(r.passed for r in results)


@pytest.mark.parametrize("column, bad_value, reason", [
    ("temperature_c", 99.0, "temperature_in_range"),
    ("temperature_c", -45.0, "temperature_in_range"),
    ("temperature_c", None, "required_fields_present"),
    ("humidity_pct", 150, "humidity_in_range"),
    ("precipitation_mm", -1.0, "precipitation_and_wind_not_negative"),
    ("wind_speed_kmh", -5.0, "precipitation_and_wind_not_negative"),
])
def test_bad_row_is_quarantined_with_its_reason(clean_df, test_config, column, bad_value, reason):
    clean_df.loc[0, column] = bad_value
    good, quarantined, _ = validate(clean_df, test_config, HOURS, RUN_TIME)
    assert len(good) == 239
    assert len(quarantined) == 1
    assert quarantined["dq_failure_reason"].iloc[0] == reason


def test_row_failing_two_checks_lists_both_reasons(clean_df, test_config):
    clean_df.loc[0, "temperature_c"] = 99.0
    clean_df.loc[0, "humidity_pct"] = 150
    _, quarantined, _ = validate(clean_df, test_config, HOURS, RUN_TIME)
    assert quarantined["dq_failure_reason"].iloc[0] == "temperature_in_range; humidity_in_range"


def test_duplicate_key_blocks_the_load(clean_df, test_config):
    with_duplicate = pd.concat([clean_df, clean_df.iloc[[0]]], ignore_index=True)
    with pytest.raises(DataQualityError, match="key_is_unique") as caught:
        validate(with_duplicate, test_config, HOURS, RUN_TIME)
    assert result(caught.value.results, "key_is_unique").failed_rows == 1


def test_missing_city_blocks_the_load(clean_df, test_config):
    without_cardiff = clean_df[clean_df["city"] != "Cardiff"]
    with pytest.raises(DataQualityError, match="every_city_every_hour"):
        validate(without_cardiff, test_config, HOURS, RUN_TIME)


def test_missing_hour_blocks_the_load(clean_df, test_config):
    with pytest.raises(DataQualityError, match="every_city_every_hour"):
        validate(clean_df.drop(index=0), test_config, HOURS, RUN_TIME)


def test_unknown_weather_code_only_warns(clean_df, test_config):
    clean_df.loc[0, "weather_category"] = "unknown"
    good, quarantined, results = validate(clean_df, test_config, HOURS, RUN_TIME)
    assert len(good) == 240
    assert quarantined.empty
    assert not result(results, "weather_code_known").passed


def test_old_data_only_warns(clean_df, test_config):
    a_week_later = RUN_TIME + timedelta(days=7)
    good, _, results = validate(clean_df, test_config, HOURS, a_week_later)
    assert len(good) == 240
    assert not result(results, "latest_hour_is_recent").passed


def test_timeliness_check_can_be_switched_off(clean_df, test_config):
    _, _, results = validate(clean_df, test_config, HOURS, RUN_TIME, check_timeliness=False)
    assert "latest_hour_is_recent" not in [r.name for r in results]


def test_quarantined_rows_are_saved_with_their_reason(clean_df, test_config, tmp_path):
    clean_df.loc[0, "temperature_c"] = 99.0
    _, quarantined, _ = validate(clean_df, test_config, HOURS, RUN_TIME)
    path = write_quarantine(quarantined, tmp_path, RUN_TIME)
    saved = pd.read_parquet(path)
    assert path.parent.name == "run_date=2026-11-23"
    assert saved["dq_failure_reason"].tolist() == ["temperature_in_range"]


def test_nothing_to_quarantine_writes_no_file(tmp_path):
    assert write_quarantine(pd.DataFrame(), tmp_path, RUN_TIME) is None
    assert list(tmp_path.iterdir()) == []


def test_dq_report_lists_every_check(clean_df, test_config, tmp_path):
    _, _, results = validate(clean_df, test_config, HOURS, RUN_TIME)
    path = write_dq_report(results, 0, RUN_TIME, tmp_path)
    text = path.read_text(encoding="utf-8")
    assert path.name == "dq_20261123T103000.md"
    assert "Quarantined rows: 0" in text
    for r in results:
        assert f"| {r.name} |" in text