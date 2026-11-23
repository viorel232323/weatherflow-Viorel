"""Pipeline: run extract -> transform -> load in order and report the outcome."""
import logging
import time
from datetime import datetime, timezone
from typing import Any

from weatherflow.extract import extract
from weatherflow.load import count_rows, load, write_parquet
from weatherflow.reference import read_wmo_codes
from weatherflow.transform import transform

logger = logging.getLogger(__name__)


def run(config: dict[str, Any]) -> int:
    """Run the pipeline once. Return 0 if every city loaded, 1 if any city failed."""
    started = time.perf_counter()
    run_time = datetime.now(timezone.utc)
    logger.info("Run started at %s UTC", run_time.strftime("%Y-%m-%d %H:%M:%S"))

    raw, failed = extract(config, run_time)
    if not raw:
        logger.error("No city could be extracted, so nothing was loaded")
        return 1

    df = transform(raw, read_wmo_codes(), run_time)
    write_parquet(df, config["paths"]["processed_dir"], run_time)
    db_path = config["paths"]["database"]
    load(df, db_path)
    logger.info("Table now holds %d rows (%.1f s)", count_rows(db_path), time.perf_counter() - started)

    if failed:
        logger.error("Run incomplete: %d city(ies) failed: %s", len(failed), ", ".join(failed))
        return 1
    return 0