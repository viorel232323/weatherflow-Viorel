"""Command line: python -m weatherflow run"""
import argparse
import logging
import sys

from weatherflow.config import ConfigError, load_config
from weatherflow.log_setup import LOG_FORMAT, setup_logging
from weatherflow.pipeline import run

logger = logging.getLogger("weatherflow")


def build_parser() -> argparse.ArgumentParser:
    """Describe the commands the tool accepts."""
    parser = argparse.ArgumentParser(prog="weatherflow", description="Hourly UK weather pipeline.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("run", help="extract, transform and load the latest hours")
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
    return 1


if __name__ == "__main__":
    sys.exit(main())