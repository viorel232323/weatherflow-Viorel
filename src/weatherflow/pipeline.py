"""Pipeline: extract -> transform -> validate -> load, then report the outcome."""
import logging
import time
from datetime import datetime, timezone
from typing import Any

from weatherflow.extract import extract
from weatherflow.load import count_rows, load, write_parquet
from weatherflow.reference import read_wmo_codes
from weatherflow.transform import transform
from weatherflow.validate import DataQualityError, validate, write_dq_report, write_quarantine

logger = logging.getLogger(__name__)
SOURCE = "open_meteo_forecast"


def run(config: dict[str, Any]) -> int:
    """Run the pipeline once. Return 0 on success, 1 if a city or a blocking DQ check failed."""
    started = time.perf_counter()
    run_time = datetime.now(timezone.utc)
    paths = config["paths"]
    logger.info("Run started at %s UTC", run_time.strftime("%Y-%m-%d %H:%M:%S"))

    raw, failed = extract(config, run_time)
    if not raw:
        logger.error("No city could be extracted, so nothing was loaded")
        return 1

    df = transform(raw, read_wmo_codes(), run_time, SOURCE)
    expected_hours = (config["api"]["past_days"] + config["api"]["forecast_days"]) * 24
    try:
        good, quarantined, results = validate(df, config, expected_hours, run_time)
    except DataQualityError as error:
        write_dq_report(error.results, 0, run_time, paths["dq_report_dir"])
        logger.error("Load stopped, nothing loaded: %s", error)
        return 1
    write_quarantine(quarantined, paths["quarantine_dir"], run_time)
    write_dq_report(results, len(quarantined), run_time, paths["dq_report_dir"])

    write_parquet(good, paths["processed_dir"], run_time)
    load(good, config)
    logger.info("Table now holds %d rows (%.1f s)", count_rows(paths["database"]), time.perf_counter() - started)

    if failed:
        logger.error("Run incomplete: %d city(ies) failed: %s", len(failed), ", ".join(failed))
        return 1
    return 0