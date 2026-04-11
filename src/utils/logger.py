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

from src.config.runtime import get_runtime_settings


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
    settings = get_runtime_settings()
    logging_cfg = settings["logging"]
    logs_dir = os.getenv("LOG_DIR", settings["paths"]["logs"])
    level_name = os.getenv("LOG_LEVEL", str(logging_cfg["level"])).upper()
    logger_level = getattr(logging, level_name, logging.INFO)

    # Avoid adding duplicate handlers when module is re-imported
    if logger.handlers:
        logger.setLevel(logger_level)
        return logger

    logger.setLevel(logger_level)
    logger.propagate = False

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # ── Console handler ──────────────────────────────────────────────────────
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt)
    logger.addHandler(console_handler)

    # ── Rotating file handler ────────────────────────────────────────────────
    os.makedirs(logs_dir, exist_ok=True)
    safe_name = name.replace(".", "_")
    file_path = log_file or os.path.join(logs_dir, f"{safe_name}.log")

    file_handler = RotatingFileHandler(
        file_path,
        maxBytes=int(logging_cfg["max_bytes"]),
        backupCount=int(logging_cfg["backup_count"]),
    )
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    return logger
