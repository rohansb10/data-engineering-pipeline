"""
test_bronze_ingestion.py
------------------------
Unit tests for the Bronze ingestion layer using a local in-memory
SparkSession (no Iceberg writes required — we mock _write_iceberg).
"""

from __future__ import annotations
from unittest.mock import patch, MagicMock

import pytest
from pyspark.sql import SparkSession

from src.ingestion.bronze_ingestion import (
    TableSpec,
    ingest_table,
    run_bronze_ingestion,
)


@pytest.fixture(scope="module")
def spark():
    return (
        SparkSession.builder.master("local[1]")
        .appName("test-bronze")
        .getOrCreate()
    )


class TestIngestTable:
    def test_success_path(self, spark, tmp_path):
        """Happy path: valid CSV → returns True."""
        csv = tmp_path / "test.csv"
        csv.write_text("id,name\n1,Alice\n2,Bob\n")

        spec = TableSpec(
            csv_file=str(csv),
            iceberg_table="local.db.test_table",
        )

        with patch("src.ingestion.bronze_ingestion.DATA_ROOT", str(tmp_path)), \
             patch("src.ingestion.bronze_ingestion._write_iceberg") as mock_write:
            mock_write.return_value = None
            result = ingest_table(spark, spec)

        assert result is True
        mock_write.assert_called_once()

    def test_retry_on_failure(self, spark):
        """Should retry and return False after all attempts fail."""
        spec = TableSpec(
            csv_file="nonexistent.csv",
            iceberg_table="local.db.missing",
        )

        with patch("src.ingestion.bronze_ingestion.DATA_ROOT", "/nonexistent"):
            result = ingest_table(spark, spec, retries=2)

        assert result is False

    def test_run_bronze_ingestion_returns_dict(self, spark, tmp_path):
        """run_bronze_ingestion returns a dict of table → bool."""
        with patch("src.ingestion.bronze_ingestion.ingest_table", return_value=True) as mock_ingest, \
             patch("src.ingestion.bronze_ingestion.get_spark_session", return_value=spark):
            results = run_bronze_ingestion(spark=spark)

        assert isinstance(results, dict)
        assert all(isinstance(v, bool) for v in results.values())
