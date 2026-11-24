"""Command line: python -m weatherflow run | backfill"""
import argparse
import logging
import sys
from datetime import date, datetime, timezone

from weatherflow.config import ConfigError, load_config
from weatherflow.log_setup import LOG_FORMAT, setup_logging
from weatherflow.pipeline import backfill, backfill_range, run

logger = logging.getLogger("weatherflow")


def build_parser() -> argparse.ArgumentParser:
    """Describe the commands the tool accepts."""
    parser = argparse.ArgumentParser(prog="weatherflow", description="Hourly UK weather pipeline.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("run", help="fetch the hours since the last run plus the forecast, and load them")
    history = commands.add_parser("backfill", help="load past days from the historical archive API")
    history.add_argument("--days", type=int, default=30, help="how many days to load (default 30)")
    history.add_argument("--start-date", type=date.fromisoformat, help="first day, YYYY-MM-DD")
    history.add_argument("--end-date", type=date.fromisoformat, help="last day, YYYY-MM-DD (default: 5 days ago)")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse the command, load config, set up logging, run it, and return the exit code."""
    args = build_parser().parse_args(argv)
    logging.basicConfig(level="INFO", format=LOG_FORMAT)  # screen only, until config is read
    try:
        config = load_config()
    except ConfigError as error:
        logger.error("%s", error)
        return 1
    setup_logging(config["paths"]["log_file"], config.get("logging", {}).get("level", "INFO"))

    if args.command == "run":
        return run(config)
    if args.command == "backfill":
        today = datetime.now(timezone.utc).date()
        try:
            start, end = backfill_range(today, args.days, config["api"]["archive_lag_days"],
                                        args.start_date, args.end_date)
        except ValueError as error:
            logger.error("%s", error)
            return 1
        return backfill(config, start, end)
    return 1


if __name__ == "__main__":
    sys.exit(main())