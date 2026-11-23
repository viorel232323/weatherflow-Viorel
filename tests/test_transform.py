"""Unit tests for the pure transform functions."""
import pandas as pd
import pytest

from weatherflow.transform import (
    add_derived_metrics,
    add_weather_description,
    beaufort_scale,
    deduplicate,
    flatten_payload,
    outdoor_work_risk,
    standardise_columns,
    transform,
)


def one_row(**overrides) -> pd.DataFrame:
    """A single calm, dry, daytime row. Pass column=value to change any field."""
    row = {"temperature_c": 10.0, "wind_speed_kmh": 0.0, "precipitation_mm": 0.0,
           "is_day": 1, "weather_category": "clear"}
    row.update(overrides)
    return pd.DataFrame([row])


def test_flatten_payload_gives_one_row_per_hour_with_city(london_payload):
    df = flatten_payload(london_payload, "London")
    assert len(df) == 6
    assert (df["city"] == "London").all()
    assert {"time", "temperature_2m", "weather_code", "is_day"} <= set(df.columns)


def test_standardise_columns_renames_and_marks_times_as_utc(london_payload):
    df = standardise_columns(flatten_payload(london_payload, "London"))
    assert {"observed_at_utc", "observed_at_local", "temperature_c", "wind_speed_kmh"} <= set(df.columns)
    assert str(df["observed_at_utc"].dt.tz) == "UTC"
    assert str(df["observed_at_local"].dt.tz) == "Europe/London"


@pytest.mark.parametrize("celsius, fahrenheit", [(0, 32), (100, 212), (-40, -40)])
def test_temperature_is_converted_to_fahrenheit(celsius, fahrenheit):
    df = add_derived_metrics(one_row(temperature_c=float(celsius)))
    assert df.loc[0, "temperature_f"] == pytest.approx(fahrenheit)


def test_wind_speed_is_converted_to_metres_per_second():
    df = add_derived_metrics(one_row(wind_speed_kmh=36.0))
    assert df.loc[0, "wind_speed_ms"] == pytest.approx(10.0)


def test_known_weather_code_gets_description_and_category(codes):
    df = pd.DataFrame({"weather_code": pd.array([63], dtype="Int64")})
    out = add_weather_description(df, codes)
    assert out.loc[0, "weather_description"] == "Moderate rain"
    assert out.loc[0, "weather_category"] == "rain"


def test_unknown_weather_code_becomes_unknown_not_a_crash(codes):
    df = pd.DataFrame({"weather_code": pd.array([12345], dtype="Int64")})
    out = add_weather_description(df, codes)
    assert out.loc[0, "weather_description"] == "unknown"
    assert out.loc[0, "weather_category"] == "unknown"


def test_deduplicate_keeps_the_latest_ingested_row():
    hour = pd.Timestamp("2026-11-23 09:00", tz="UTC")
    df = pd.DataFrame({
        "city": ["London", "London"],
        "observed_at_utc": [hour, hour],
        "source": ["open_meteo_forecast", "open_meteo_forecast"],
        "ingested_at_utc": [pd.Timestamp("2026-11-23 11:00", tz="UTC"),   # newer row first
                            pd.Timestamp("2026-11-23 10:00", tz="UTC")],
        "temperature_c": [6.0, 5.0],
    })
    out = deduplicate(df)
    assert len(out) == 1
    assert out.loc[0, "temperature_c"] == 6.0


@pytest.mark.parametrize("speed_ms, force",
                         [(0, 0), (0.29, 0), (0.3, 1), (13.89, 6), (13.9, 7), (32.7, 12)])
def test_beaufort_scale_boundaries(speed_ms, force):
    assert beaufort_scale(pd.Series([speed_ms])).iloc[0] == force


@pytest.mark.parametrize("beaufort, category, precipitation_mm, temperature_c, expected", [
    (7, "clear", 0.0, 10.0, "high"),     # exactly Beaufort 7
    (6, "clear", 0.0, 10.0, "medium"),   # Beaufort 6 is only medium
    (0, "storm", 0.0, 10.0, "high"),
    (0, "snow", 0.0, 10.0, "high"),
    (0, "clear", 4.0, 10.0, "high"),     # exactly 4 mm
    (0, "clear", 3.9, 10.0, "medium"),
    (5, "clear", 0.0, 10.0, "medium"),   # exactly Beaufort 5
    (4, "clear", 0.0, 10.0, "low"),
    (0, "clear", 1.0, 10.0, "medium"),   # exactly 1 mm
    (0, "clear", 0.9, 10.0, "low"),
    (0, "clear", 0.0, 0.0, "medium"),    # exactly 0 °C
    (0, "clear", 0.0, 0.1, "low"),
    (0, "rain", 0.0, 10.0, "low"),       # the rain category alone is not a risk; the amount is
])
def test_outdoor_work_risk_rules_and_boundaries(beaufort, category, precipitation_mm, temperature_c, expected):
    risk = outdoor_work_risk(pd.Series([beaufort], dtype="Int64"), pd.Series([category]),
                             pd.Series([precipitation_mm]), pd.Series([temperature_c]))
    assert risk.iloc[0] == expected


def test_transform_runs_every_step_on_the_fixture(london_payload, codes):
    df = transform([("London", london_payload)], codes)
    assert len(df) == 6
    assert (df["source"] == "open_meteo_forecast").all()
    assert set(df["outdoor_work_risk"]) <= {"low", "medium", "high"}
    assert "time" not in df.columns


def test_transform_of_nothing_is_an_empty_table(codes):
    assert transform([], codes).empty