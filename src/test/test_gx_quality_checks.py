"""
test_gx_quality_checks.py
--------------------------
Unit tests for the GX data quality layer.

Tests use small in-memory Spark DataFrames and a temporary YAML suite
so no Iceberg catalog or real data is needed.
"""

from __future__ import annotations
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import yaml
from pyspark.sql import SparkSession


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def spark():
    return (
        SparkSession.builder
        .master("local[1]")
        .appName("test-gx")
        .getOrCreate()
    )


@pytest.fixture()
def good_df(spark):
    data = [
        ("o1", "c1", "delivered", 5, 0, "good",  "credit_card", 120.0),
        ("o2", "c2", "delivered", 3, 0, "neutral","boleto",      80.5),
    ]
    cols = ["order_id","customer_id","order_status","review_score",
            "is_late","review_category","payment_type","payment_value"]
    return spark.createDataFrame(data, cols)


@pytest.fixture()
def bad_df(spark):
    """Contains nulls and out-of-range values that should trigger failures."""
    data = [
        (None, "c1", "delivered", 5, 0, "good", "credit_card", 120.0),
        ("o2", None, "delivered", 9, 2, "unknown", "cash",      -50.0),
    ]
    cols = ["order_id","customer_id","order_status","review_score",
            "is_late","review_category","payment_type","payment_value"]
    return spark.createDataFrame(data, cols)


@pytest.fixture()
def tmp_suite_yaml(tmp_path):
    """Write a minimal GX suite YAML to a temp directory."""
    suite = {
        "name": "test_suite",
        "expectations": [
            {"type": "expect_column_to_exist",              "kwargs": {"column": "order_id"}},
            {"type": "expect_column_values_to_not_be_null", "kwargs": {"column": "order_id"}},
            {"type": "expect_column_values_to_be_unique",   "kwargs": {"column": "order_id"}},
            {"type": "expect_column_values_to_be_between",
             "kwargs": {"column": "review_score", "min_value": 1, "max_value": 5, "mostly": 0.8}},
            {"type": "expect_table_row_count_to_be_between","kwargs": {"min_value": 1, "max_value": 1000}},
        ]
    }
    yaml_file = tmp_path / "test_suite.yml"
    yaml_file.write_text(yaml.dump(suite))
    return tmp_path, "test_suite.yml"


# ── Suite loader tests ─────────────────────────────────────────────────────

class TestLoadSuite:
    def test_loads_from_yaml(self, tmp_suite_yaml):
        import great_expectations as gx
        from src.quality.gx_quality_checks import load_suite

        tmp_dir, yaml_file = tmp_suite_yaml
        context = gx.get_context()

        with patch("src.quality.gx_quality_checks.GX_SUITES_DIR", tmp_dir):
            suite = load_suite(context, yaml_file)

        assert suite.name == "test_suite"
        assert len(suite.expectations) == 5

    def test_reuse_existing_suite(self, tmp_suite_yaml):
        """Calling load_suite twice should not raise."""
        import great_expectations as gx
        from src.quality.gx_quality_checks import load_suite

        tmp_dir, yaml_file = tmp_suite_yaml
        context = gx.get_context()

        with patch("src.quality.gx_quality_checks.GX_SUITES_DIR", tmp_dir):
            suite1 = load_suite(context, yaml_file)
            suite2 = load_suite(context, yaml_file)  # should reuse

        assert suite1.name == suite2.name


# ── Report printer ─────────────────────────────────────────────────────────

class TestPrintReport:
    def test_does_not_raise(self, good_df, tmp_suite_yaml, spark):
        import great_expectations as gx
        from src.quality.gx_quality_checks import load_suite, print_report

        tmp_dir, yaml_file = tmp_suite_yaml
        context = gx.get_context()

        ds   = context.data_sources.add_spark(name="test_ds_report")
        asset = ds.add_dataframe_asset(name="test_asset_report")
        bd   = asset.add_batch_definition_whole_dataframe("test_batch_report")
        batch = bd.get_batch(batch_parameters={"dataframe": good_df})

        with patch("src.quality.gx_quality_checks.GX_SUITES_DIR", tmp_dir):
            suite = load_suite(context, yaml_file)
            vr = batch.validate(suite)

        # Should not raise
        print_report(vr, "local.db.test_table")


# ── Quality check runner ───────────────────────────────────────────────────

class TestRunQualityChecks:
    def test_bad_layer_raises(self, spark):
        from src.quality.gx_quality_checks import run_quality_checks
        with pytest.raises(ValueError, match="No suites registered"):
            run_quality_checks(layer="invalid", spark=spark)

    def test_critical_failure_raises_runtime_error(self, spark, tmp_suite_yaml):
        """A critical suite failing should raise RuntimeError."""
        from src.quality.gx_quality_checks import (
            run_quality_checks, SUITE_REGISTRY, SuiteSpec
        )
        import great_expectations as gx

        tmp_dir, yaml_file = tmp_suite_yaml

        # Patch registry to a single spec pointing at our temp suite
        fake_spec = SuiteSpec(
            iceberg_table="local.db.fake",
            suite_yaml=yaml_file,
            datasource_name="ds_critical_test",
            layer="bronze",
            critical=True,
        )

        bad_data = [("o1", "c1"), ("o1", "c2")]  # duplicate order_id → fails unique check
        bad_df = spark.createDataFrame(bad_data, ["order_id", "customer_id"])

        with patch("src.quality.gx_quality_checks.SUITE_REGISTRY", [fake_spec]), \
             patch("src.quality.gx_quality_checks.GX_SUITES_DIR", tmp_dir), \
             patch("src.quality.gx_quality_checks.get_spark_session", return_value=spark):

            # Patch iceberg read to return our bad df
            with patch("pyspark.sql.SparkSession.read") as mock_read:
                mock_read.format.return_value.load.return_value = bad_df
                with pytest.raises(RuntimeError, match="Data quality FAILED"):
                    run_quality_checks(layer="bronze", spark=spark, fail_on_critical=True)

    def test_no_fail_flag_suppresses_error(self, spark, tmp_suite_yaml):
        """--no-fail mode returns results without raising."""
        from src.quality.gx_quality_checks import run_quality_checks, SuiteSpec

        tmp_dir, yaml_file = tmp_suite_yaml
        fake_spec = SuiteSpec(
            iceberg_table="local.db.fake2",
            suite_yaml=yaml_file,
            datasource_name="ds_nofail_test",
            layer="bronze",
            critical=True,
        )

        bad_df = spark.createDataFrame([("o1", "c1"), ("o1", "c2")], ["order_id", "x"])

        with patch("src.quality.gx_quality_checks.SUITE_REGISTRY", [fake_spec]), \
             patch("src.quality.gx_quality_checks.GX_SUITES_DIR", tmp_dir), \
             patch("src.quality.gx_quality_checks.get_spark_session", return_value=spark):

            with patch("pyspark.sql.SparkSession.read") as mock_read:
                mock_read.format.return_value.load.return_value = bad_df
                results = run_quality_checks(
                    layer="bronze", spark=spark, fail_on_critical=False
                )

        assert isinstance(results, list)
