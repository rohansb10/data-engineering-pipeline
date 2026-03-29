"""
test_silver_transform.py
------------------------
Unit tests for Silver transformation functions.
Uses small in-memory DataFrames — no Iceberg I/O.
"""

from __future__ import annotations
from unittest.mock import patch

import pytest
from pyspark.sql import SparkSession
from pyspark.sql.types import (
    StructType, StructField, StringType, DoubleType, IntegerType
)


@pytest.fixture(scope="module")
def spark():
    return (
        SparkSession.builder.master("local[1]")
        .appName("test-silver")
        .getOrCreate()
    )


class TestCleanOrders:
    def test_removes_null_order_ids(self, spark):
        from pyspark.sql.functions import col

        schema = StructType([
            StructField("order_id", StringType()),
            StructField("customer_id", StringType()),
            StructField("order_status", StringType()),
            StructField("order_purchase_timestamp", StringType()),
            StructField("order_delivered_customer_date", StringType()),
            StructField("order_estimated_delivery_date", StringType()),
        ])
        data = [
            ("o1", "c1", "delivered", "2021-01-10 10:00:00", "2021-01-15 10:00:00", "2021-01-16 10:00:00"),
            (None, "c2", "shipped",   "2021-02-01 10:00:00", None,                  "2021-02-10 10:00:00"),
        ]
        df = spark.createDataFrame(data, schema)

        with patch("src.transform.silver_transform._read", return_value=df):
            from src.transform.silver_transform import clean_orders
            result = clean_orders(spark)

        # Null order_id row should be dropped
        assert result.filter(col("order_id").isNull()).count() == 0

    def test_delivery_days_column_added(self, spark):
        schema = StructType([
            StructField("order_id", StringType()),
            StructField("customer_id", StringType()),
            StructField("order_status", StringType()),
            StructField("order_purchase_timestamp", StringType()),
            StructField("order_delivered_customer_date", StringType()),
            StructField("order_estimated_delivery_date", StringType()),
        ])
        data = [("o1", "c1", "delivered", "2021-01-01 00:00:00", "2021-01-06 00:00:00", "2021-01-07 00:00:00")]
        df = spark.createDataFrame(data, schema)

        with patch("src.transform.silver_transform._read", return_value=df):
            from src.transform.silver_transform import clean_orders
            result = clean_orders(spark)

        assert "delivery_days" in result.columns
        row = result.collect()[0]
        assert row["delivery_days"] == 5


class TestCleanOrderReviews:
    def test_review_category_mapping(self, spark):
        schema = StructType([
            StructField("order_id", StringType()),
            StructField("review_score", IntegerType()),
        ])
        data = [("o1", 5), ("o2", 3), ("o3", 1), ("o4", 4)]
        df = spark.createDataFrame(data, schema)

        with patch("src.transform.silver_transform._read", return_value=df):
            from src.transform.silver_transform import clean_order_reviews
            result = clean_order_reviews(spark)

        cats = {r["order_id"]: r["review_category"] for r in result.collect()}
        assert cats["o1"] == "good"
        assert cats["o2"] == "neutral"
        assert cats["o3"] == "bad"
        assert cats["o4"] == "good"
