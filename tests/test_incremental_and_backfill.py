"""Tests: the watermark, the incremental window, and the backfill."""
from datetime import date, datetime, timezone

import pytest

from weatherflow.__main__ import main
from weatherflow.extract import ExtractError, build_forecast_params, date_chunks, extract_archive
from weatherflow.load import count_rows, load, read_watermark
from weatherflow.pipeline import ARCHIVE, FORECAST, backfill, backfill_range, incremental_window
from weatherflow.transform import transform

NOW = datetime(2026, 11, 23, 10, 30, tzinfo=timezone.utc)


def utc(day, hour):
    """A November 2026 hour in UTC, to keep the tests short."""
    return datetime(2026, 11, day, hour, tzinfo=timezone.utc)


@pytest.fixture
def loaded_db(test_config, codes, payload_factory):
    """The test database after one run: 22 Nov 00:00 to 23 Nov 23:00 for 5 cities (240 rows)."""
    raw = [(city["name"], payload_factory()) for city in test_config["cities"]]
    load(transform(raw, codes, NOW, FORECAST), test_config)
    return test_config["paths"]["database"]


# ---------- Watermark ----------

def test_watermark_is_none_before_anything_is_loaded(test_config):
    assert read_watermark(test_config["paths"]["database"], "London", FORECAST, NOW) is None


def test_watermark_ignores_forecast_hours_that_have_not_happened(loaded_db):
    # Rows go up to 23 Nov 23:00, but at 10:30 only the hours up to 10:00 have happened.
    assert read_watermark(loaded_db, "London", FORECAST, NOW) == utc(23, 10)


def test_watermark_is_kept_per_source(loaded_db):
    assert read_watermark(loaded_db, "London", ARCHIVE, NOW) is None


# ---------- Incremental window ----------

def test_first_run_falls_back_to_past_days(test_config):
    assert incremental_window(test_config, NOW) == (utc(22, 0), utc(23, 23))


def test_next_run_starts_2_hours_before_the_watermark(loaded_db, test_config):
    assert incremental_window(test_config, NOW) == (utc(23, 8), utc(23, 23))


def test_forecast_request_asks_for_exactly_the_window(test_config):
    params = build_forecast_params(test_config["cities"][0], test_config["api"], (utc(23, 8), utc(23, 23)))
    assert params["start_hour"] == "2026-11-23T08:00"
    assert params["end_hour"] == "2026-11-23T23:00"
    assert "past_days" not in params


def test_load_logs_new_and_updated_rows(loaded_db, test_config, codes, payload_factory, caplog):
    # 24 hours from 23 Nov 12:00: 12 hours already loaded (updated) and 12 new, per city.
    raw = [(city["name"], payload_factory(24, "2026-11-23T12:00")) for city in test_config["cities"]]
    with caplog.at_level("INFO"):
        load(transform(raw, codes, NOW, FORECAST), test_config)
    assert "60 new, 60 updated" in caplog.text


# ---------- Backfill dates and chunks ----------

def test_default_backfill_is_the_30_days_ending_5_days_ago():
    assert backfill_range(date(2026, 11, 24), days=30, lag_days=5) == (date(2026, 10, 21), date(2026, 11, 19))


def test_backfill_dates_can_be_given():
    chosen = backfill_range(date(2026, 11, 24), 30, 5, start=date(2026, 10, 1), end=date(2026, 10, 7))
    assert chosen == (date(2026, 10, 1), date(2026, 10, 7))


def test_backfill_rejects_a_start_after_the_end():
    with pytest.raises(ValueError, match="after end date"):
        backfill_range(date(2026, 11, 24), 30, 5, start=date(2026, 11, 10), end=date(2026, 11, 1))


def test_30_days_split_into_7_day_chunks():
    chunks = date_chunks(date(2026, 10, 21), date(2026, 11, 19), 7)
    assert [(last - first).days + 1 for first, last in chunks] == [7, 7, 7, 7, 2]
    assert chunks[0][0] == date(2026, 10, 21)
    assert chunks[-1][1] == date(2026, 11, 19)


# ---------- Backfill extract (API faked) ----------

def test_archive_extract_lands_one_file_per_city_and_chunk(monkeypatch, test_config):
    asked = []

    def fake_get(url, params, timeout, max_retries):
        asked.append((params["start_date"], params["end_date"]))
        return {"hourly": {"time": []}}

    monkeypatch.setattr("weatherflow.extract.get_with_retries", fake_get)
    monkeypatch.setattr("weatherflow.extract.time.sleep", lambda seconds: None)
    results, failed = extract_archive(test_config, date(2026, 11, 1), date(2026, 11, 10), NOW)

    assert failed == []
    assert len(results) == 5 * 2                         # 5 cities x 2 chunks (7 days + 3 days)
    assert asked[:2] == [("2026-11-01", "2026-11-07"), ("2026-11-08", "2026-11-10")]
    assert len(list(test_config["paths"]["raw_dir"].rglob("*.json"))) == 10


def test_city_with_a_failed_chunk_is_left_out_completely(monkeypatch, test_config):
    london = test_config["cities"][0]

    def fake_get(url, params, timeout, max_retries):
        if params["latitude"] == london["latitude"] and params["start_date"] == "2026-11-08":
            raise ExtractError("HTTP 503 after 4 attempts")
        return {"hourly": {"time": []}}

    monkeypatch.setattr("weatherflow.extract.get_with_retries", fake_get)
    monkeypatch.setattr("weatherflow.extract.time.sleep", lambda seconds: None)
    results, failed = extract_archive(test_config, date(2026, 11, 1), date(2026, 11, 10), NOW)

    assert failed == ["London"]
    assert "London" not in [name for name, _ in results]
    assert len(results) == 4 * 2


# ---------- Backfill end to end (extract faked, the rest real) ----------

@pytest.fixture
def fake_archive(monkeypatch, payload_factory):
    """Replace extract_archive: every city returns 24 calm hours for each day asked for."""
    def fake(config, start, end, run_time):
        hours = ((end - start).days + 1) * 24
        return [(city["name"], payload_factory(hours, f"{start}T00:00")) for city in config["cities"]], []

    monkeypatch.setattr("weatherflow.pipeline.extract_archive", fake)


def test_backfill_of_30_days_loads_3600_rows_and_a_rerun_changes_nothing(fake_archive, test_config):
    db = test_config["paths"]["database"]
    assert backfill(test_config, date(2026, 10, 21), date(2026, 11, 19), NOW) == 0
    assert count_rows(db) == 30 * 24 * 5
    assert backfill(test_config, date(2026, 10, 21), date(2026, 11, 19), NOW) == 0
    assert count_rows(db) == 3600
    assert read_watermark(db, "London", ARCHIVE, NOW) == utc(19, 23)    # stored as archive rows


def test_cli_backfill_passes_the_dates_on(monkeypatch, test_config):
    received = []

    def fake_backfill(config, start, end):
        received.append((start, end))
        return 0

    monkeypatch.setattr("weatherflow.__main__.load_config", lambda: test_config)
    monkeypatch.setattr("weatherflow.__main__.setup_logging", lambda log_file, level: None)
    monkeypatch.setattr("weatherflow.__main__.backfill", fake_backfill)
    assert main(["backfill", "--start-date", "2026-10-01", "--end-date", "2026-10-07"]) == 0
    assert received == [(date(2026, 10, 1), date(2026, 10, 7))]


def test_cli_backfill_with_dates_the_wrong_way_round_returns_1(monkeypatch, test_config):
    monkeypatch.setattr("weatherflow.__main__.load_config", lambda: test_config)
    monkeypatch.setattr("weatherflow.__main__.setup_logging", lambda log_file, level: None)
    assert main(["backfill", "--start-date", "2026-11-10", "--end-date", "2026-11-01"]) == 1