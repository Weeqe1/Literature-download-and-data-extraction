"""Centralized logging configuration for the NFP-PDF-to-DB project.

Import and call `setup_logging()` early in the entry point to configure
all loggers with a consistent format. Individual modules should use:
    import logging
    logger = logging.getLogger(__name__)
"""

import logging
import sys


def setup_logging(level: int = logging.INFO, log_file: str = None) -> None:
    """Configure root logger with console and optional file handlers.

    Args:
        level: Logging level (default: INFO).
        log_file: Optional path to a log file.
    """
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    date_fmt = "%Y-%m-%d %H:%M:%S"

    handlers: list = [logging.StreamHandler(sys.stdout)]
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(
        level=level,
        format=fmt,
        datefmt=date_fmt,
        handlers=handlers,
    )

    # Quiet noisy third-party loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
