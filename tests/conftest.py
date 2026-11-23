"""Shared test fixtures: sample API payloads and a config that writes only to a temporary folder."""
import copy
import json
from pathlib import Path

import pandas as pd
import pytest

from weatherflow.config import load_config
from weatherflow.reference import read_wmo_codes

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def london_payload() -> dict:
    """A real Open-Meteo response for London, trimmed to 6 hours."""
    path = FIXTURES / "open_meteo_london.json"
    return json.loads(path.read_text(encoding="utf-8"))  


@pytest.fixture
def codes() -> pd.DataFrame:
    """The WMO weather-code lookup table."""
    return read_wmo_codes()


@pytest.fixture
def test_config(tmp_path: Path) -> dict:
    """The real config, with every output path moved into a temporary folder."""
    config = copy.deepcopy(load_config())
    for key in ["raw_dir", "processed_dir", "quarantine_dir", "dq_report_dir"]:
        config["paths"][key] = tmp_path / key
    config["paths"]["database"] = tmp_path / "test.db"
    config["paths"]["log_file"] = tmp_path / "test.log"
    return config


def make_payload(hours: int = 48, start: str = "2026-11-22T00:00") -> dict:
    """A made-up Open-Meteo payload with `hours` calm, dry hours (for end-to-end tests)."""
    times = pd.date_range(start, periods=hours, freq="h").strftime("%Y-%m-%dT%H:%M").tolist()
    return {
        "latitude": 51.5,
        "longitude": -0.12,
        "hourly": {
            "time": times,
            "temperature_2m": [10.0] * hours,
            "relative_humidity_2m": [80] * hours,
            "apparent_temperature": [9.0] * hours,
            "precipitation": [0.0] * hours,
            "wind_speed_10m": [10.0] * hours,
            "weather_code": [3] * hours,
            "is_day": [1] * hours,
        },
    }


@pytest.fixture
def payload_factory():
    """Gives tests the make_payload function, to build payloads of any length."""
    return make_payload