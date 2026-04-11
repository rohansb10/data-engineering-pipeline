"""
gx_quality_checks.py
--------------------
Great Expectations data quality checks for the Olist Medallion pipeline.

Supports all three layers:
  Bronze  → raw schema, nulls, uniqueness, row counts
  Silver  → domain values, range checks, cleaned column checks
  Gold    → derived column integrity, business KPI sanity

Each layer loads its Expectation Suite from a YAML file under gx/suites/,
validates the live Spark/Pandas DataFrame, prints a rich report, and
returns a structured result dict so callers (or Airflow tasks) can
decide whether to halt the pipeline.

Usage
-----
  python -m src.quality.gx_quality_checks --layer bronze
  python -m src.quality.gx_quality_checks --layer silver
  python -m src.quality.gx_quality_checks --layer gold
  python -m src.quality.gx_quality_checks --layer all
"""

from __future__ import annotations

import argparse
import sys
import yaml
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import great_expectations as gx
from pyspark.sql import SparkSession, DataFrame

from src.config.runtime import fq_table, get_runtime_settings, project_root
from src.utils.spark_session import get_spark_session
from src.utils.logger import get_logger

log = get_logger(__name__)
SETTINGS = get_runtime_settings()

# ── Paths ──────────────────────────────────────────────────────────────────

GX_SUITES_DIR = project_root() / "gx" / "suites"


# ── Suite spec ─────────────────────────────────────────────────────────────

@dataclass
class SuiteSpec:
    """Links an Iceberg table to its GX suite YAML and data source name."""
    iceberg_table: str
    suite_yaml: str          # filename inside GX_SUITES_DIR
    datasource_name: str
    layer: str               # 'bronze' | 'silver' | 'gold'
    critical: bool = True    # if True, pipeline halts on failure


SUITE_REGISTRY: list[SuiteSpec] = [
    # Bronze
    SuiteSpec(fq_table("orders", SETTINGS), "bronze_orders_suite.yml", "bronze_orders", "bronze"),
    SuiteSpec(fq_table("customers", SETTINGS), "bronze_customers_suite.yml", "bronze_customers", "bronze"),
    # Silver
    SuiteSpec(fq_table("silver_order_payments", SETTINGS), "silver_order_payments_suite.yml", "silver_payments", "silver"),
    # Gold
    SuiteSpec(fq_table("gold_order_summary", SETTINGS), "gold_order_summary_suite.yml", "gold_order_summary", "gold", critical=True),
]


# ── Suite loader ───────────────────────────────────────────────────────────

def load_suite(context: gx.AbstractDataContext, yaml_file: str) -> gx.ExpectationSuite:
    """Load (or retrieve if already registered) an ExpectationSuite from YAML."""
    yaml_path = GX_SUITES_DIR / yaml_file
    if not yaml_path.exists():
        raise FileNotFoundError(f"GX suite file does not exist: {yaml_path}")
    with open(yaml_path, "r") as fh:
        cfg = yaml.safe_load(fh)

    try:
        suite = context.suites.add(gx.ExpectationSuite(**cfg))
        log.info("Loaded suite from YAML: %s", yaml_file)
    except (ValueError, Exception):
        # Suite name already registered in this context session — reuse it
        suite = context.suites.get(cfg["name"])
        log.debug("Reused existing suite: %s", cfg["name"])
    return suite


# ── Reporter ───────────────────────────────────────────────────────────────

def print_report(validation_results: Any, table: str) -> None:
    """Pretty-print a GX validation result to stdout and the logger."""
    total   = len(validation_results.results)
    passed  = sum(1 for r in validation_results.results if r.success)
    failed  = total - passed
    status  = "✅ PASSED" if validation_results.success else "❌ FAILED"

    sep = "=" * 64
    log.info(sep)
    log.info("GX VALIDATION REPORT  |  %s", table)
    log.info(sep)
    log.info("Overall: %s  |  Passed: %d  Failed: %d  Total: %d",
             status, passed, failed, total)
    log.info("-" * 64)

    for i, result in enumerate(validation_results.results, 1):
        etype  = result.expectation_config.type
        kwargs = result.expectation_config.kwargs
        col    = kwargs.get("column", "table-level")

        desc = f"{etype} on [{col}]"
        if "type_" in kwargs:
            desc += f" type={kwargs['type_']}"
        if "min_value" in kwargs or "max_value" in kwargs:
            desc += f" range=[{kwargs.get('min_value','*')} – {kwargs.get('max_value','*')}]"
        if "value_set" in kwargs:
            desc += f" set={kwargs['value_set']}"
        if "mostly" in kwargs:
            desc += f" mostly={kwargs['mostly']*100:.0f}%"

        mark = "✅" if result.success else "❌"
        log.info("%2d. %s  %s", i, mark, desc)

        if not result.success:
            res = getattr(result, "result", {})
            if "unexpected_count" in res:
                log.warning(
                    "    ↳ %d unexpected value(s)  (%.1f%% of rows)",
                    res["unexpected_count"],
                    res.get("unexpected_percent", 0),
                )
            exc = getattr(result, "exception_info", None)
            if exc and exc.get("exception_message"):
                log.error("    ↳ Exception: %s", exc["exception_message"])

    log.info(sep)


# ── Core validator ─────────────────────────────────────────────────────────

def validate_table(
    spec: SuiteSpec,
    spark: SparkSession,
    context: gx.AbstractDataContext,
) -> dict[str, Any]:
    """
    Read one Iceberg table, run its GX suite, return a result dict.

    Returns
    -------
    {
        "table":   str,
        "success": bool,
        "passed":  int,
        "failed":  int,
        "total":   int,
        "critical": bool,
    }
    """
    log.info("Validating %s [%s layer] …", spec.iceberg_table, spec.layer.upper())

    try:
        df: DataFrame = spark.read.format("iceberg").load(spec.iceberg_table)
    except Exception as exc:
        log.error("Cannot read table %s: %s", spec.iceberg_table, exc)
        return {"table": spec.iceberg_table, "success": False,
                "passed": 0, "failed": 1, "total": 1, "critical": spec.critical}

    # ── Wire up GX datasource ──────────────────────────────────────────────
    try:
        datasource = context.data_sources.add_spark(name=spec.datasource_name)
    except Exception:
        datasource = context.data_sources.get(spec.datasource_name)

    try:
        asset = datasource.add_dataframe_asset(name=f"{spec.datasource_name}_asset")
    except Exception:
        asset = datasource.get_asset(f"{spec.datasource_name}_asset")

    try:
        batch_def = asset.add_batch_definition_whole_dataframe(
            f"{spec.datasource_name}_batch"
        )
    except Exception:
        batch_def = asset.get_batch_definition(f"{spec.datasource_name}_batch")

    batch = batch_def.get_batch(batch_parameters={"dataframe": df})

    # ── Load suite & validate ──────────────────────────────────────────────
    suite = load_suite(context, spec.suite_yaml)
    vr = batch.validate(suite)
    print_report(vr, spec.iceberg_table)

    passed = sum(1 for r in vr.results if r.success)
    total  = len(vr.results)
    return {
        "table":    spec.iceberg_table,
        "success":  vr.success,
        "passed":   passed,
        "failed":   total - passed,
        "total":    total,
        "critical": spec.critical,
    }


# ── Layer runner ───────────────────────────────────────────────────────────

def run_quality_checks(
    layer: str = "all",
    spark: SparkSession | None = None,
    fail_on_critical: bool = True,
) -> list[dict[str, Any]]:
    """
    Run GX checks for a given layer (bronze | silver | gold | all).

    Parameters
    ----------
    layer : str
        Which layer(s) to validate.
    spark : SparkSession | None
        Reuse an existing session or create one.
    fail_on_critical : bool
        If True, raises RuntimeError when any critical suite fails.

    Returns
    -------
    List of per-table result dicts.
    """
    spark = spark or get_spark_session(app_name="olist-gx-checks")
    context = gx.get_context()

    specs = (
        SUITE_REGISTRY
        if layer == "all"
        else [s for s in SUITE_REGISTRY if s.layer == layer]
    )

    if not specs:
        raise ValueError(f"No suites registered for layer '{layer}'.")

    results = []
    for spec in specs:
        result = validate_table(spec, spark, context)
        results.append(result)

    # ── Summary ────────────────────────────────────────────────────────────
    log.info("=" * 64)
    log.info("GX QUALITY CHECK SUMMARY  |  layer=%s", layer.upper())
    log.info("=" * 64)
    for r in results:
        mark = "✅" if r["success"] else "❌"
        crit = " [CRITICAL]" if r["critical"] else ""
        log.info("%s  %s  passed=%d failed=%d%s",
                 mark, r["table"], r["passed"], r["failed"], crit)

    critical_failures = [r for r in results if not r["success"] and r["critical"]]
    if critical_failures and fail_on_critical:
        tables = [r["table"] for r in critical_failures]
        raise RuntimeError(
            f"Data quality FAILED on critical tables: {tables}. "
            "Pipeline halted."
        )

    return results


# ── CLI ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run GX data quality checks")
    parser.add_argument(
        "--layer",
        choices=["bronze", "silver", "gold", "all"],
        default="all",
        help="Which Medallion layer to validate (default: all)",
    )
    parser.add_argument(
        "--no-fail",
        action="store_true",
        help="Do not exit with error on critical failures (useful for reporting-only runs)",
    )
    args = parser.parse_args()

    try:
        run_quality_checks(layer=args.layer, fail_on_critical=not args.no_fail)
    except RuntimeError as e:
        log.critical(str(e))
        sys.exit(1)
