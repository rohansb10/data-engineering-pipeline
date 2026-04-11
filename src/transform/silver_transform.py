"""
silver_transform.py
-------------------
Silver layer: clean, deduplicate, cast, and enrich Olist data.

Reads from Bronze Iceberg tables → writes clean Silver tables back to
the same catalog under ``local.db`` (prefixed with ``silver_``).
"""

from __future__ import annotations
import sys

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import col, datediff, expr, when

from src.config.runtime import fq_table, get_runtime_settings
from src.utils.spark_session import get_spark_session
from src.utils.logger import get_logger

log = get_logger(__name__)
SETTINGS = get_runtime_settings()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read(spark: SparkSession, table: str) -> DataFrame:
    log.info("Reading bronze table: %s", table)
    return spark.read.format("iceberg").load(table)


def _write(df: DataFrame, table: str) -> None:
    """Overwrite a Silver Iceberg table."""
    log.info("Writing silver table: %s  rows=%d", table, df.count())
    df.writeTo(table).using("iceberg").option("format", "parquet") \
      .option("compression", "snappy").createOrReplace()


# ---------------------------------------------------------------------------
# Per-table transformations
# ---------------------------------------------------------------------------

def clean_orders(spark: SparkSession) -> DataFrame:
    """Cast timestamps, drop nulls, deduplicate, add delivery_days feature."""
    orders = _read(spark, fq_table("orders", SETTINGS))
    orders = (
        orders
        .dropDuplicates(["order_id"])
        .filter(col("order_id").isNotNull())
        .withColumn("order_purchase_timestamp",
                    col("order_purchase_timestamp").cast("timestamp"))
        .withColumn("order_delivered_customer_date",
                    col("order_delivered_customer_date").cast("timestamp"))
        .withColumn("order_estimated_delivery_date",
                    col("order_estimated_delivery_date").cast("timestamp"))
        # ── Derived columns ────────────────────────────────────────────────
        .withColumn(
            "delivery_days",
            datediff(col("order_delivered_customer_date"),
                     col("order_purchase_timestamp")),
        )
        .withColumn(
            "is_late",
            when(
                col("order_delivered_customer_date")
                > col("order_estimated_delivery_date"), 1
            ).otherwise(0),
        )
    )
    return orders


def clean_customers(spark: SparkSession) -> DataFrame:
    return (
        _read(spark, fq_table("customers", SETTINGS))
        .dropDuplicates(["customer_id"])
        .filter(col("customer_id").isNotNull())
    )


def clean_order_reviews(spark: SparkSession) -> DataFrame:
    # review_score must be int; mis-parsed CSV rows can put timestamps in this column.
    # try_cast avoids CAST_INVALID_INPUT; null scores get category "unknown".
    return (
        _read(spark, fq_table("order_reviews", SETTINGS))
        .dropDuplicates(["order_id"])
        .filter(col("order_id").isNotNull())
        .withColumn(
            "review_score",
            expr("try_cast(trim(cast(review_score as string)) as int)"),
        )
        .withColumn(
            "review_category",
            when(col("review_score").isNull(), "unknown")
            .when(col("review_score") >= 4, "good")
            .when(col("review_score") == 3, "neutral")
            .otherwise("bad"),
        )
    )


def clean_order_payments(spark: SparkSession) -> DataFrame:
    return (
        _read(spark, fq_table("order_payments", SETTINGS))
        .dropDuplicates(["order_id"])
        .filter(col("order_id").isNotNull())
        .filter(col("payment_value").isNotNull())
        .drop("payment_sequential")
    )


def clean_order_items(spark: SparkSession) -> DataFrame:
    return (
        _read(spark, fq_table("order_items", SETTINGS))
        .dropDuplicates(["order_id"])
        .filter(col("order_id").isNotNull())
    )


def clean_products(spark: SparkSession) -> DataFrame:
    products = _read(spark, fq_table("products", SETTINGS))
    category_xlat = _read(spark, fq_table("product_category_translation", SETTINGS))
    return (
        products
        .filter(col("product_id").isNotNull())
        .join(category_xlat, "product_category_name", "left")
    )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def run_silver_transform(spark: SparkSession | None = None) -> None:
    spark = spark or get_spark_session(app_name="olist-silver")

    steps = {
        fq_table("silver_orders", SETTINGS):         clean_orders,
        fq_table("silver_customers", SETTINGS):      clean_customers,
        fq_table("silver_order_reviews", SETTINGS):  clean_order_reviews,
        fq_table("silver_order_payments", SETTINGS): clean_order_payments,
        fq_table("silver_order_items", SETTINGS):    clean_order_items,
        fq_table("silver_products", SETTINGS):       clean_products,
    }

    failed = []
    for target_table, fn in steps.items():
        try:
            df = fn(spark)
            _write(df, target_table)
            log.info("✅ Silver table ready: %s", target_table)
        except Exception as exc:  # noqa: BLE001
            log.error("❌ Failed to build %s: %s", target_table, exc)
            failed.append(target_table)

    if failed:
        log.error("Silver transform finished with failures: %s", failed)
        raise RuntimeError(f"Silver transform failed for tables: {failed}")
    else:
        log.info("Silver transform complete ✅")


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        run_silver_transform()
    except RuntimeError:
        sys.exit(1)
