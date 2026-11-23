"""Tests for extract. The API is faked with monkeypatch, so no test touches the internet."""
import json
from datetime import datetime, timezone

import pytest
import requests

from weatherflow.extract import ExtractError, extract, get_with_retries, save_raw

URL = "https://example.test/forecast"
RUN_TIME = datetime(2026, 11, 23, 9, 0, tzinfo=timezone.utc)
PAYLOAD = {"hourly": {"time": ["2026-11-23T09:00"], "temperature_2m": [7.5]}}


class FakeResponse:
    """Stands in for requests.Response: only the parts code uses."""

    def __init__(self, status_code: int, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = json.dumps(self._payload)

    def json(self) -> dict:
        return self._payload


@pytest.fixture
def fake_api(monkeypatch):
    """Replace requests.get and time.sleep. Returns (set_answers, calls, waits)."""
    answers, calls, waits = [], [], []

    def fake_get(url, params=None, timeout=None):
        calls.append(params)
        answer = answers[len(calls) - 1]
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr("weatherflow.extract.requests.get", fake_get)
    monkeypatch.setattr("weatherflow.extract.time.sleep", waits.append)
    return answers.extend, calls, waits


def test_server_error_is_retried_until_it_works(fake_api):
    set_answers, calls, waits = fake_api
    set_answers([FakeResponse(503), FakeResponse(503), FakeResponse(200, PAYLOAD)])
    assert get_with_retries(URL, {}, timeout=10, max_retries=3) == PAYLOAD
    assert len(calls) == 3
    assert waits == [1, 2]          # exponential backoff


def test_client_error_is_not_retried(fake_api):
    set_answers, calls, waits = fake_api
    set_answers([FakeResponse(404)])
    with pytest.raises(ExtractError, match="HTTP 404"):
        get_with_retries(URL, {}, timeout=10, max_retries=3)
    assert len(calls) == 1
    assert waits == []


def test_timeout_and_connection_error_are_retried(fake_api):
    set_answers, calls, _ = fake_api
    set_answers([requests.Timeout(), requests.ConnectionError(), FakeResponse(200, PAYLOAD)])
    assert get_with_retries(URL, {}, timeout=10, max_retries=3) == PAYLOAD
    assert len(calls) == 3


def test_gives_up_after_the_last_retry(fake_api):
    set_answers, calls, waits = fake_api
    set_answers([FakeResponse(503)] * 4)
    with pytest.raises(ExtractError, match="HTTP 503 after 4 attempts"):
        get_with_retries(URL, {}, timeout=10, max_retries=3)
    assert len(calls) == 4
    assert waits == [1, 2, 4]


def test_save_raw_writes_the_payload_unchanged(tmp_path):
    path = save_raw(tmp_path, "London", PAYLOAD, RUN_TIME)
    assert path == tmp_path / "2026-11-23" / "london_20261123T090000.json"
    assert json.loads(path.read_text(encoding="utf-8")) == PAYLOAD


def test_save_raw_never_overwrites_a_file(tmp_path):
    save_raw(tmp_path, "London", PAYLOAD, RUN_TIME)
    with pytest.raises(FileExistsError):
        save_raw(tmp_path, "London", PAYLOAD, RUN_TIME)


def test_one_failing_city_does_not_stop_the_others(fake_api, test_config):
    set_answers, calls, _ = fake_api
    names = [city["name"] for city in test_config["cities"]]
    set_answers([FakeResponse(404) if name == "Manchester" else FakeResponse(200, PAYLOAD) for name in names])

    results, failed = extract(test_config, RUN_TIME)

    assert failed == ["Manchester"]
    assert [name for name, _ in results] == [name for name in names if name != "Manchester"]
    assert len(list(test_config["paths"]["raw_dir"].rglob("*.json"))) == 4