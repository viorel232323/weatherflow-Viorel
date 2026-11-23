"""Validate: data quality checks that run between transform and load.

Row-level checks quarantine bad rows (kept aside with a reason, never silently
dropped). Dataset-level checks can fail the whole run before anything is loaded.
"""
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

KEY = ["city", "observed_at_utc", "source"]


@dataclass
class CheckResult:
    """The outcome of one data quality check."""
    name: str
    dimension: str    # completeness, validity, uniqueness, timeliness or consistency
    severity: str     # "quarantine", "fail" or "warn"
    passed: bool
    failed_rows: int
    details: str


class DataQualityError(Exception):
    """Raised when a blocking ("fail") check fails, so nothing is loaded."""

    def __init__(self, message: str, results: list[CheckResult]):
        super().__init__(message)
        self.results = results


def row_checks(df: pd.DataFrame, dq: dict[str, Any]) -> list[tuple[str, str, str, pd.Series]]:
    """Row-level checks as (name, dimension, severity, mask of the rows that FAIL)."""
    return [
        ("required_fields_present", "completeness", "quarantine",
         df[["city", "observed_at_utc", "temperature_c"]].isna().any(axis=1)),
        ("temperature_in_range", "validity", "quarantine",
         df["temperature_c"].notna()
         & ~df["temperature_c"].between(dq["temperature_c_min"], dq["temperature_c_max"])),
        ("humidity_in_range", "validity", "quarantine",
         df["humidity_pct"].notna()
         & ~df["humidity_pct"].between(dq["humidity_pct_min"], dq["humidity_pct_max"])),
        ("precipitation_and_wind_not_negative", "validity", "quarantine",
         (df["precipitation_mm"] < 0) | (df["wind_speed_kmh"] < 0)),
        ("feels_like_close_to_temperature", "consistency", "warn",
         (df["feels_like_c"] - df["temperature_c"]).abs() > dq["max_feels_like_gap_c"]),
        ("weather_code_known", "validity", "warn",
         df["weather_category"] == "unknown"),
    ]


def dataset_checks(df: pd.DataFrame, cities: list[str], expected_hours: int, run_time: datetime,
                   check_timeliness: bool, dq: dict[str, Any]) -> list[CheckResult]:
    """Checks on the whole run: unique keys, every city has every hour, data is recent."""
    results = []

    duplicates = int(df.duplicated(subset=KEY).sum())
    results.append(CheckResult("key_is_unique", "uniqueness", "fail", duplicates == 0, duplicates,
                               f"{duplicates} duplicate (city, observed_at_utc, source) row(s)"))

    hours = df.groupby("city")["observed_at_utc"].nunique()
    short = {name: int(hours.get(name, 0)) for name in cities if hours.get(name, 0) < expected_hours}
    results.append(CheckResult("every_city_every_hour", "completeness", "fail", not short, len(short),
                               f"expected {expected_hours} hours per city; short: {short or 'none'}"))

    if check_timeliness:
        past = df.loc[df["observed_at_utc"] <= run_time, "observed_at_utc"]
        age_hours = (run_time - past.max()).total_seconds() / 3600 if not past.empty else float("inf")
        recent = age_hours <= dq["max_hours_since_latest"]
        results.append(CheckResult("latest_hour_is_recent", "timeliness", "warn", recent, int(not recent),
                                   f"newest past hour is {age_hours:.1f} h old "
                                   f"(limit {dq['max_hours_since_latest']} h)"))
    return results


def validate(df: pd.DataFrame, config: dict[str, Any], expected_hours: int, run_time: datetime,
             check_timeliness: bool = True) -> tuple[pd.DataFrame, pd.DataFrame, list[CheckResult]]:
    """Run every check. Return (good_rows, quarantined_rows, results).

    Raises DataQualityError if a blocking check fails; nothing should then be loaded.
    """
    dq = config["data_quality"]
    results = []
    reasons = pd.Series("", index=df.index)
    for name, dimension, severity, mask in row_checks(df, dq):
        mask = mask.fillna(False).astype(bool)
        count = int(mask.sum())
        results.append(CheckResult(name, dimension, severity, count == 0, count,
                                   f"{count} row(s) failed" if count else "all rows passed"))
        if severity == "quarantine":
            reasons[mask] = reasons[mask] + name + "; "

    cities = [city["name"] for city in config["cities"]]
    results += dataset_checks(df, cities, expected_hours, run_time, check_timeliness, dq)

    bad = reasons != ""
    quarantined = df[bad].assign(dq_failure_reason=reasons[bad].str.rstrip("; "))
    good = df[~bad]
    for r in results:
        log = logger.info if r.passed else (logger.error if r.severity == "fail" else logger.warning)
        log("DQ %-36s %-10s %s", r.name, "PASS" if r.passed else r.severity.upper(), r.details)

    failed = [r.name for r in results if r.severity == "fail" and not r.passed]
    if failed:
        raise DataQualityError(f"blocking check(s) failed: {', '.join(failed)}", results)
    return good, quarantined, results


def write_quarantine(quarantined: pd.DataFrame, quarantine_dir: Path, run_time: datetime) -> Path | None:
    """Save quarantined rows (with dq_failure_reason) to quarantine_dir/run_date=<date>/."""
    if quarantined.empty:
        return None
    folder = quarantine_dir / f"run_date={run_time:%Y-%m-%d}"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"quarantine-{run_time:%Y%m%dT%H%M%S}.parquet"
    quarantined.to_parquet(path, index=False)
    logger.warning("Quarantined %d row(s) -> %s", len(quarantined), path.name)
    return path


def write_dq_report(results: list[CheckResult], quarantined_rows: int, run_time: datetime,
                    report_dir: Path) -> Path:
    """Write a Markdown summary of every check for this run."""
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"dq_{run_time:%Y%m%dT%H%M%S}.md"
    lines = [f"# Data quality report: run at {run_time:%Y-%m-%d %H:%M:%S} UTC", "",
             f"Quarantined rows: {quarantined_rows}", "",
             "| Check | Dimension | Severity | Result | Failed | Details |",
             "|---|---|---|---|---|---|"]
    for r in results:
        result = "PASS" if r.passed else "FAIL"
        lines.append(f"| {r.name} | {r.dimension} | {r.severity} | {result} | {r.failed_rows} | {r.details} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("DQ report -> %s", path.name)
    return path