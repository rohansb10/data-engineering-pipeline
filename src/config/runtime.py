"""Runtime configuration loader for the Olist pipeline."""

from __future__ import annotations

import os
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SETTINGS_FILE = PROJECT_ROOT / "src" / "config" / "settings.yaml"


DEFAULT_SETTINGS: dict[str, Any] = {
    "spark": {
        "app_name": "olist-pipeline",
        "mode": "local",
        "master": "local[*]",
        "log_level": "ERROR",
    },
    "paths": {
        "data_root": "data",
        "warehouse": "data_warehouse/iceberg_warehouse",
        "iceberg_jar": "data_warehouse/iceberg-spark-runtime-4.0_2.13-1.10.1.jar",
        "logs": "logs",
    },
    "iceberg": {
        "catalog": "local",
        "namespace": "db",
        "format": "parquet",
        "compression": "snappy",
        "max_records_per_file": 500000,
        "coalesce_partitions": 3,
    },
    "pipeline": {
        "bronze_retries": 2,
        "silver_retries": 2,
        "gold_retries": 2,
    },
    "logging": {
        "level": "INFO",
        "max_bytes": 5242880,
        "backup_count": 5,
    },
    "airflow": {
        "schedule": "@daily",
        "catchup": False,
        "max_active_runs": 1,
        "default_retries": 2,
        "retry_delay_minutes": 5,
        "email_on_failure": False,
        "email_on_retry": False,
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _to_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _apply_env_overrides(settings: dict[str, Any]) -> None:
    env_map = {
        ("spark", "app_name"): ("SPARK_APP_NAME", str),
        ("spark", "mode"): ("SPARK_MODE", str),
        ("spark", "master"): ("SPARK_MASTER", str),
        ("spark", "log_level"): ("SPARK_LOG_LEVEL", str),
        ("paths", "data_root"): ("DATA_ROOT", str),
        ("paths", "warehouse"): ("ICEBERG_WAREHOUSE", str),
        ("paths", "iceberg_jar"): ("ICEBERG_JAR", str),
        ("paths", "logs"): ("LOG_DIR", str),
        ("iceberg", "catalog"): ("ICEBERG_CATALOG", str),
        ("iceberg", "namespace"): ("ICEBERG_NAMESPACE", str),
        ("pipeline", "bronze_retries"): ("BRONZE_RETRIES", int),
        ("pipeline", "silver_retries"): ("SILVER_RETRIES", int),
        ("pipeline", "gold_retries"): ("GOLD_RETRIES", int),
        ("logging", "level"): ("LOG_LEVEL", str),
        ("logging", "max_bytes"): ("LOG_MAX_BYTES", int),
        ("logging", "backup_count"): ("LOG_BACKUP_COUNT", int),
        ("airflow", "schedule"): ("AIRFLOW_SCHEDULE", str),
        ("airflow", "catchup"): ("AIRFLOW_CATCHUP", _to_bool),
        ("airflow", "max_active_runs"): ("AIRFLOW_MAX_ACTIVE_RUNS", int),
        ("airflow", "default_retries"): ("AIRFLOW_DEFAULT_RETRIES", int),
        ("airflow", "retry_delay_minutes"): ("AIRFLOW_RETRY_DELAY_MINUTES", int),
    }
    for (section, key), (env_name, caster) in env_map.items():
        raw_value = os.getenv(env_name)
        if raw_value is None:
            continue
        settings[section][key] = caster(raw_value)


def _resolve_project_path(value: str) -> str:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return str(path.resolve())


def _normalize_paths(settings: dict[str, Any]) -> None:
    for key in ("data_root", "warehouse", "iceberg_jar", "logs"):
        settings["paths"][key] = _resolve_project_path(settings["paths"][key])


@lru_cache(maxsize=1)
def get_runtime_settings() -> dict[str, Any]:
    loaded: dict[str, Any] = {}
    if SETTINGS_FILE.exists():
        with SETTINGS_FILE.open("r", encoding="utf-8") as fh:
            loaded = yaml.safe_load(fh) or {}

    settings = _deep_merge(DEFAULT_SETTINGS, loaded)
    _apply_env_overrides(settings)
    _normalize_paths(settings)
    return settings


def project_root() -> Path:
    return PROJECT_ROOT


def iceberg_namespace(settings: dict[str, Any] | None = None) -> str:
    cfg = settings or get_runtime_settings()
    return f"{cfg['iceberg']['catalog']}.{cfg['iceberg']['namespace']}"


def fq_table(table: str, settings: dict[str, Any] | None = None) -> str:
    if table.count(".") >= 2:
        return table
    return f"{iceberg_namespace(settings)}.{table}"

