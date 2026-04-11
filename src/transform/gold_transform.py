"""
gold_transform.py
-----------------
Gold layer: business-ready analytical tables for the Olist project.

Reads from Silver Iceberg tables and produces three Gold outputs:

1. ``gold_order_summary``    – per-order enriched fact table
2. ``gold_state_payment_agg`` – state × payment-type aggregation
3. ``gold_revenue_by_order``  – revenue + freight per order
"""

from __future__ import annotations
import sys

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import (
    avg,
    col,
    count,
    round as spark_round,
    sum as spark_sum,
    when,
)

from src.config.runtime import fq_table, get_runtime_settings
from src.utils.spark_session import get_spark_session
from src.utils.logger import get_logger

log = get_logger(__name__)
SETTINGS = get_runtime_settings()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read(spark: SparkSession, table: str) -> DataFrame:
    log.info("Reading silver table: %s", table)
    return spark.read.format("iceberg").load(table)


def _write(df: DataFrame, table: str) -> None:
    row_count = df.count()
    log.info("Writing gold table: %s  rows=%d", table, row_count)
    df.writeTo(table).using("iceberg").option("format", "parquet") \
      .option("compression", "snappy").createOrReplace()


# ---------------------------------------------------------------------------
# Gold table builders
# ---------------------------------------------------------------------------

def build_order_summary(spark: SparkSession) -> DataFrame:
    """
    Enriched per-order fact table joining orders ▷ customers ▷
    reviews ▷ payments.
    """
    orders = _read(spark, fq_table("silver_orders", SETTINGS)).alias("o")
    customers = _read(spark, fq_table("silver_customers", SETTINGS)).alias("c")
    reviews = _read(spark, fq_table("silver_order_reviews", SETTINGS)).alias("r")
    payments = _read(spark, fq_table("silver_order_payments", SETTINGS)).alias("p")

    return (
        orders
        .join(customers, col("o.customer_id") == col("c.customer_id"), "left")
        .join(reviews,   col("o.order_id")    == col("r.order_id"),    "left")
        .join(payments,  col("o.order_id")    == col("p.order_id"),    "left")
        .select(
            col("o.order_id"),
            col("o.customer_id"),
            col("c.customer_city"),
            col("c.customer_state"),
            col("o.order_status"),
            col("o.order_purchase_timestamp"),
            col("o.delivery_days"),
            col("o.is_late"),
            col("r.review_score"),
            col("r.review_category"),
            col("p.payment_type"),
            col("p.payment_value"),
        )
    )


def build_state_payment_agg(spark: SparkSession) -> DataFrame:
    """
    KPI aggregation grouped by customer_state × payment_type.
    Great for dashboards & BI tools.
    """
    summary = _read(spark, fq_table("gold_order_summary", SETTINGS))
    return (
        summary
        .groupBy("customer_state", "payment_type")
        .agg(
            count("order_id").alias("total_orders"),
            spark_round(avg("payment_value"),  2).alias("avg_payment_value"),
            spark_round(avg("review_score"),   2).alias("avg_review_score"),
            spark_round(avg("delivery_days"),  2).alias("avg_delivery_days"),
            spark_round(
                (count(when(col("is_late") == 1, True)) / count("order_id")) * 100,
                2
            ).alias("late_delivery_pct"),
        )
    )


def build_revenue_by_order(spark: SparkSession) -> DataFrame:
    """Revenue + freight aggregated to order level."""
    order_items = _read(spark, fq_table("silver_order_items", SETTINGS))
    return (
        order_items
        .groupBy("order_id")
        .agg(
            spark_round(spark_sum("price"),         2).alias("total_revenue"),
            spark_round(spark_sum("freight_value"), 2).alias("total_freight"),
            spark_round(
                spark_sum("price") + spark_sum("freight_value"), 2
            ).alias("gross_amount"),
        )
    )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def run_gold_transform(spark: SparkSession | None = None) -> None:
    spark = spark or get_spark_session(app_name="olist-gold")

    # Order matters: state_payment_agg reads gold_order_summary
    pipeline = [
        (fq_table("gold_order_summary", SETTINGS), build_order_summary),
        (fq_table("gold_revenue_by_order", SETTINGS), build_revenue_by_order),
        (fq_table("gold_state_payment_agg", SETTINGS), build_state_payment_agg),
    ]

    failed = []
    for table, fn in pipeline:
        try:
            _write(fn(spark), table)
            log.info("✅ Gold table ready: %s", table)
        except Exception as exc:  # noqa: BLE001
            log.error("❌ Failed to build %s: %s", table, exc)
            failed.append(table)

    if failed:
        log.error("Gold transform finished with failures: %s", failed)
        raise RuntimeError(f"Gold transform failed for tables: {failed}")
    else:
        log.info("Gold transform complete ✅")


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        run_gold_transform()
    except RuntimeError:
        sys.exit(1)
