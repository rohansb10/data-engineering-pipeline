"""
logger.py
---------
Centralised logging setup for the Olist Data Engineering project.

Usage
-----
    from src.utils.logger import get_logger
    log = get_logger(__name__)
    log.info("Pipeline started")
"""

from __future__ import annotations
import logging
import os
from logging.handlers import RotatingFileHandler

LOG_DIR = os.getenv("LOG_DIR", "/home/rohan/projects/airflow/logs")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()


def get_logger(name: str, log_file: str | None = None) -> logging.Logger:
    """
    Return a named logger that writes to both console and a rotating file.

    Parameters
    ----------
    name : str
        Logger name – typically ``__name__``.
    log_file : str | None
        Override the log file path. Defaults to ``<LOG_DIR>/<name>.log``.
    """
    logger = logging.getLogger(name)

    # Avoid adding duplicate handlers when module is re-imported
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # ── Console handler ──────────────────────────────────────────────────────
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt)
    logger.addHandler(console_handler)

    # ── Rotating file handler ────────────────────────────────────────────────
    os.makedirs(LOG_DIR, exist_ok=True)
    safe_name = name.replace(".", "_")
    file_path = log_file or os.path.join(LOG_DIR, f"{safe_name}.log")

    file_handler = RotatingFileHandler(
        file_path,
        maxBytes=5 * 1024 * 1024,   # 5 MB per file
        backupCount=5,
    )
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    return logger
