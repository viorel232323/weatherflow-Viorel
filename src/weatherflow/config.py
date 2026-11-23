"""Load and check config.yaml, the one place for every setting."""
from pathlib import Path
from typing import Any

import yaml

# This file is src/weatherflow/config.py, so 2 folders up is the project root.
CONFIG_FILE = Path(__file__).resolve().parents[2] / "config.yaml"

REQUIRED_SECTIONS = ["api", "cities", "paths", "dim_date"]
REQUIRED_API_KEYS = ["forecast_url", "archive_url", "timeout_seconds", "max_retries",
                     "past_days", "forecast_days", "timezone", "hourly_variables"]
REQUIRED_PATH_KEYS = ["raw_dir", "processed_dir", "quarantine_dir", "database", "log_file", "schema"]
REQUIRED_CITY_KEYS = ["name", "country", "latitude", "longitude"]


class ConfigError(Exception):
    """Raised when config.yaml is missing or incomplete."""


def _require(section: dict, keys: list[str], where: str) -> None:
    """Raise ConfigError listing every key from `keys` that `section` lacks."""
    missing = [key for key in keys if key not in section]
    if missing:
        raise ConfigError(f"config.yaml: missing {', '.join(missing)} in {where}")


def load_config(config_file: Path = CONFIG_FILE) -> dict[str, Any]:
    """Read config.yaml, check the required keys, and make every path absolute.

    Paths are built from the folder that contains config.yaml, so the pipeline
    behaves the same whichever folder it is run from.
    """
    if not config_file.exists():
        raise ConfigError(f"config file not found: {config_file}")
    with open(config_file, encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    _require(config, REQUIRED_SECTIONS, "the top level")
    _require(config["api"], REQUIRED_API_KEYS, "api")
    _require(config["paths"], REQUIRED_PATH_KEYS, "paths")
    for number, city in enumerate(config["cities"], start=1):
        _require(city, REQUIRED_CITY_KEYS, f"city number {number}")

    root = config_file.parent
    config["paths"] = {key: (root / value).resolve() for key, value in config["paths"].items()}
    return config