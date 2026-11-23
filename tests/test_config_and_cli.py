"""Tests for config.yaml checks, logging setup and the command line."""
import logging

import pytest
import yaml

from weatherflow.__main__ import main
from weatherflow.config import CONFIG_FILE, ConfigError, load_config
from weatherflow.log_setup import setup_logging


@pytest.fixture
def settings() -> dict:
    """The real config.yaml as a plain dict, before any checks."""
    return yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8"))


def write_config(folder, settings):
    """Save settings as folder/config.yaml and return its path."""
    path = folder / "config.yaml"
    path.write_text(yaml.safe_dump(settings), encoding="utf-8")
    return path


def test_real_config_loads_with_absolute_paths():
    config = load_config()
    assert len(config["cities"]) == 5
    assert all(path.is_absolute() for path in config["paths"].values())


def test_paths_are_built_from_the_config_folder(settings, tmp_path):
    config = load_config(write_config(tmp_path, settings))
    assert config["paths"]["database"] == (tmp_path / "data" / "weather.db").resolve()


def test_missing_config_file_is_a_clear_error(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "missing.yaml")


def test_missing_section_is_named_in_the_error(settings, tmp_path):
    del settings["data_quality"]
    with pytest.raises(ConfigError, match="missing data_quality in the top level"):
        load_config(write_config(tmp_path, settings))


def test_missing_api_key_is_named_in_the_error(settings, tmp_path):
    del settings["api"]["timeout_seconds"]
    with pytest.raises(ConfigError, match="missing timeout_seconds in api"):
        load_config(write_config(tmp_path, settings))


def test_city_missing_a_key_is_named_in_the_error(settings, tmp_path):
    del settings["cities"][1]["latitude"]
    with pytest.raises(ConfigError, match="missing latitude in city number 2"):
        load_config(write_config(tmp_path, settings))


@pytest.mark.parametrize("exit_code", [0, 1])
def test_cli_run_returns_the_pipeline_exit_code(monkeypatch, test_config, exit_code):
    received = []

    def fake_run(config):
        received.append(config)
        return exit_code

    monkeypatch.setattr("weatherflow.__main__.load_config", lambda: test_config)
    monkeypatch.setattr("weatherflow.__main__.setup_logging", lambda log_file, level: None)
    monkeypatch.setattr("weatherflow.__main__.run", fake_run)
    assert main(["run"]) == exit_code
    assert received == [test_config]


def test_cli_returns_1_when_config_is_broken(monkeypatch):
    def broken_config():
        raise ConfigError("config.yaml: missing api in the top level")

    monkeypatch.setattr("weatherflow.__main__.load_config", broken_config)
    assert main(["run"]) == 1


@pytest.mark.parametrize("argv", [["fly"], []])
def test_cli_rejects_a_missing_or_unknown_command(argv):
    with pytest.raises(SystemExit) as caught:
        main(argv)
    assert caught.value.code == 2      #exit code for bad usage


def test_setup_logging_writes_to_the_log_file(tmp_path):
    log_file = tmp_path / "logs" / "test.log"
    setup_logging(log_file, "INFO")
    logging.getLogger("weatherflow.test").info("hello from the test")
    logging.basicConfig(force=True)    # closes the log file so we can read it (and Windows can delete it)
    assert "hello from the test" in log_file.read_text(encoding="utf-8")