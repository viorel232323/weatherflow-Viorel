"""End-to-end tests of run(): extract is faked, everything after it is real."""
import pytest

from weatherflow.load import count_rows
from weatherflow.pipeline import run


@pytest.fixture
def fake_extract(monkeypatch, test_config, payload_factory):
    """Replace extract() in the pipeline. Call it with how many hours each city returns."""
    def use(hours=48, failed=()):
        names = [city["name"] for city in test_config["cities"]]
        raw = [(name, payload_factory(hours)) for name in names if name not in failed]
        monkeypatch.setattr("weatherflow.pipeline.extract", lambda config, run_time: (raw, list(failed)))
    return use


def test_good_run_loads_every_city_and_returns_0(fake_extract, test_config):
    fake_extract(hours=48)
    assert run(test_config) == 0
    assert count_rows(test_config["paths"]["database"]) == 240
    assert len(list(test_config["paths"]["dq_report_dir"].glob("*.md"))) == 1


def test_running_twice_still_gives_240_rows(fake_extract, test_config):
    fake_extract(hours=48)
    assert run(test_config) == 0
    assert run(test_config) == 0
    assert count_rows(test_config["paths"]["database"]) == 240


def test_missing_hours_stop_the_load_and_return_1(fake_extract, test_config):
    fake_extract(hours=6)                     # like the 6-hour fixture: far short of 48
    assert run(test_config) == 1
    assert not test_config["paths"]["database"].exists()
    assert len(list(test_config["paths"]["dq_report_dir"].glob("*.md"))) == 1   # report still written


def test_failed_city_returns_1_and_loads_nothing(fake_extract, test_config):
    fake_extract(hours=48, failed=["Manchester"])
    assert run(test_config) == 1
    assert not test_config["paths"]["database"].exists()


def test_no_city_extracted_returns_1(fake_extract, test_config):
    fake_extract(failed=[city["name"] for city in test_config["cities"]])
    assert run(test_config) == 1
    assert not test_config["paths"]["database"].exists()