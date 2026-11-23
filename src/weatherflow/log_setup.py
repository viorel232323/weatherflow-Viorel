"""Configure logging once: messages go to the terminal and to logs/pipeline.log."""
import logging
from pathlib import Path

LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def setup_logging(log_file: Path, level: str = "INFO") -> None:
    """Send log messages to the terminal and to log_file (its folder is created if missing)."""
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=level,
        format=LOG_FORMAT,
        handlers=[
            logging.StreamHandler(),                          # the terminal
            logging.FileHandler(log_file, encoding="utf-8"),  # the log file
        ],
        force=True,
    )