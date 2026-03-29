"""
bronze_ingestion.py
-------------------
Bronze layer: ingest raw Olist CSV files into Apache Iceberg tables.

All 9 source tables are written as-is (no transformation) into the
``local.db`` namespace with sensible partitioning and Snappy compression.
Each table write is wrapped in retry logic and full audit logging.
"""

from __future__ import annotations
import sys
import os

sys.path.append("/home/rohan/projects/airflow")

from dataclasses import dataclass, field
from typing import List

from pyspark.sql import SparkSession, DataFrame

from src.utils.spark_session import get_spark_session
from src.utils.logger import get_logger


log = get_logger(__name__)

DATA_ROOT = "/home/rohan/projects/airflow/data"

# ---------------------------------------------------------------------------
# Table definitions
# ---------------------------------------------------------------------------

@dataclass
class TableSpec:
    csv_file: str
    iceberg_table: str
    partition_col: str | None = None
    max_records_per_file: int = 500_000
    coalesce_n: int = 3


TABLE_SPECS: List[TableSpec] = [
    TableSpec("customers_dataset.csv",              "local.db.customers",                   "customer_state"),
    TableSpec("geolocation_dataset.csv",            "local.db.geolocation",                 "geolocation_state"),
    TableSpec("orders_dataset.csv",                 "local.db.orders",                      "order_status"),
    TableSpec("order_items_dataset.csv",            "local.db.order_items"),
    TableSpec("order_reviews_dataset.csv",          "local.db.order_reviews"),
    TableSpec("order_payments_dataset.csv",         "local.db.order_payments",              "payment_type"),
    TableSpec("product_category_name_translation.csv", "local.db.product_category_translation"),
    TableSpec("products_dataset.csv",               "local.db.products",                    "product_category_name"),
    TableSpec("sellers_dataset.csv",                "local.db.sellers",                     "seller_state"),
]


# ---------------------------------------------------------------------------
# Core write helper
# ---------------------------------------------------------------------------

def _write_iceberg(df: DataFrame, spec: TableSpec) -> None:
    """Write a DataFrame to an Iceberg table (create or replace)."""
    writer = (
        df.coalesce(spec.coalesce_n)
        .writeTo(spec.iceberg_table)
        .using("iceberg")
        .option("format", "parquet")
        .option("compression", "snappy")
        .option("maxRecordsPerFile", str(spec.max_records_per_file))
    )
    if spec.partition_col:
        writer = writer.partitionedBy(spec.partition_col)
    writer.createOrReplace()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def ingest_table(spark: SparkSession, spec: TableSpec, retries: int = 3) -> bool:
    """
    Read one CSV file and write it to Iceberg.

    Returns True on success, False if all retry attempts fail.
    """
    csv_path = f"{DATA_ROOT}/{spec.csv_file}"
    log.info("Ingesting %s → %s", csv_path, spec.iceberg_table)

    for attempt in range(1, retries + 1):
        try:
            # multiline=true: Olist order_reviews (and similar) have quoted fields with
            # embedded newlines; without this, rows split and columns shift into review_score.
            df: DataFrame = (
                spark.read.option("multiLine", "true")
                .csv(csv_path, header=True, inferSchema=True)
            )
            row_count = df.count()
            _write_iceberg(df, spec)
            log.info(
                "✅ %s loaded  rows=%d  partition=%s",
                spec.iceberg_table, row_count, spec.partition_col or "none",
            )
            return True
        except Exception as exc:  # noqa: BLE001
            log.warning("Attempt %d/%d failed for %s: %s", attempt, retries, spec.iceberg_table, exc)
            if attempt == retries:
                log.error("❌ Giving up on %s after %d attempts", spec.iceberg_table, retries)
                return False
    return False


def run_bronze_ingestion(spark: SparkSession | None = None) -> dict[str, bool]:
    """
    Ingest all tables.  Returns a dict mapping table name → success flag.
    """
    spark = spark or get_spark_session(app_name="olist-bronze")
    spark.sql("CREATE NAMESPACE IF NOT EXISTS local.db")

    results: dict[str, bool] = {}
    for spec in TABLE_SPECS:
        results[spec.iceberg_table] = ingest_table(spark, spec)

    failed = [t for t, ok in results.items() if not ok]
    if failed:
        log.error("Bronze ingestion finished with failures: %s", failed)
    else:
        log.info("Bronze ingestion complete — all %d tables loaded ✅", len(results))

    return results


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    results = run_bronze_ingestion()
    sys.exit(0 if all(results.values()) else 1)