"""
spark_session.py
----------------
Centralised SparkSession factory for the Olist Data Engineering project.
Supports local (Iceberg / Hadoop catalog) and AWS Glue catalog modes.
"""

from __future__ import annotations
import os
from pathlib import Path
from warnings import warn

from pyspark.sql import SparkSession

from src.config.runtime import get_runtime_settings

def get_spark_session(
    app_name: str | None = None,
    mode: str | None = None,
    warehouse_path: str | None = None,
) -> SparkSession:
    """
    Build and return a configured SparkSession.

    Parameters
    ----------
    app_name : str
        Spark application name shown in the UI.
    mode : str
        'local' uses a Hadoop-backed Iceberg catalog.
        'aws'   uses AWS Glue catalog (requires env creds).
    warehouse_path : str | None
        Override the warehouse root directory (local mode only).
        Falls back to the ICEBERG_WAREHOUSE env var or a sensible default.

    Returns
    -------
    SparkSession
    """
    settings = get_runtime_settings()
    spark_cfg = settings["spark"]
    iceberg_cfg = settings["iceberg"]
    paths_cfg = settings["paths"]

    session_app_name = app_name or os.getenv("SPARK_APP_NAME", spark_cfg["app_name"])
    session_mode = mode or os.getenv("SPARK_MODE", spark_cfg["mode"])
    jar_path = os.getenv("ICEBERG_JAR", paths_cfg["iceberg_jar"])
    wh_path = warehouse_path or os.getenv("ICEBERG_WAREHOUSE", paths_cfg["warehouse"])
    catalog = os.getenv("ICEBERG_CATALOG", iceberg_cfg["catalog"])
    namespace = os.getenv("ICEBERG_NAMESPACE", iceberg_cfg["namespace"])
    master = os.getenv("SPARK_MASTER", spark_cfg["master"])
    spark_log_level = os.getenv("SPARK_LOG_LEVEL", spark_cfg["log_level"])

    shuffle_partitions = os.getenv("SPARK_SQL_SHUFFLE_PARTITIONS", "200")

    builder = (
        SparkSession.builder.appName(session_app_name)
        .config(
            "spark.sql.extensions",
            "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",
        )
        .config("spark.sql.shuffle.partitions", shuffle_partitions)
        .config("spark.sql.adaptive.enabled", "true")
        .config("spark.sql.adaptive.coalescePartitions.enabled", "true")
        .config("spark.sql.defaultCatalog", catalog)
    )

    if Path(jar_path).exists():
        builder = builder.config("spark.jars", jar_path)
    else:
        warn(f"Configured Iceberg JAR does not exist: {jar_path}")

    if session_mode == "local":
        builder = (
            builder.master(master)
            .config(f"spark.sql.catalog.{catalog}", "org.apache.iceberg.spark.SparkCatalog")
            .config(f"spark.sql.catalog.{catalog}.type", "hadoop")
            .config(f"spark.sql.catalog.{catalog}.warehouse", wh_path)
        )
    elif session_mode == "aws":
        builder = (
            builder
            .config(f"spark.sql.catalog.{catalog}", "org.apache.iceberg.spark.SparkCatalog")
            .config(f"spark.sql.catalog.{catalog}.catalog-impl",
                    "org.apache.iceberg.aws.glue.GlueCatalog")
            .config(f"spark.sql.catalog.{catalog}.warehouse",
                    os.getenv("S3_WAREHOUSE", "s3://my-iceberg-lake-rohan/warehouse"))
            .config(f"spark.sql.catalog.{catalog}.io-impl",
                    "org.apache.iceberg.aws.s3.S3FileIO")
        )
    else:
        raise ValueError(f"Unknown mode '{session_mode}'. Choose 'local' or 'aws'.")

    builder = builder.config("spark.sql.catalogImplementation", "in-memory")
    builder = builder.config("spark.sql.session.timeZone", os.getenv("SPARK_TZ", "UTC"))
    builder = builder.config("spark.sql.catalog.currentNamespace", namespace)

    spark = builder.getOrCreate()
    spark.sparkContext.setLogLevel(spark_log_level)
    return spark
