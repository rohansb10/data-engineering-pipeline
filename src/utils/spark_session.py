"""
spark_session.py
----------------
Centralised SparkSession factory for the Olist Data Engineering project.
Supports local (Iceberg / Hadoop catalog) and AWS Glue catalog modes.
"""

from __future__ import annotations
import os
from pyspark.sql import SparkSession


def get_spark_session(
    app_name: str = "olist-pipeline",
    mode: str = "local",
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
    jar_path = os.getenv(
        "ICEBERG_JAR",
        "/home/rohan/projects/airflow/data_warehouse/"
        "iceberg-spark-runtime-4.0_2.13-1.10.1.jar",
    )
    wh_path = warehouse_path or os.getenv(
        "ICEBERG_WAREHOUSE",
        "/home/rohan/projects/airflow/data_warehouse/iceberg_warehouse",
    )

    shuffle_partitions = os.getenv("SPARK_SQL_SHUFFLE_PARTITIONS", "200")

    builder = (
        SparkSession.builder.appName(app_name)
        .config("spark.jars", jar_path)
        .config(
            "spark.sql.extensions",
            "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",
        )
        .config("spark.sql.shuffle.partitions", shuffle_partitions)
        .config("spark.sql.adaptive.enabled", "true")
        .config("spark.sql.adaptive.coalescePartitions.enabled", "true")
    )

    if mode == "local":
        builder = (
            builder.master("local[*]")
            .config("spark.sql.catalog.local", "org.apache.iceberg.spark.SparkCatalog")
            .config("spark.sql.catalog.local.type", "hadoop")
            .config("spark.sql.catalog.local.warehouse", wh_path)
        )
    elif mode == "aws":
        builder = (
            builder
            .config("spark.sql.catalog.glue", "org.apache.iceberg.spark.SparkCatalog")
            .config("spark.sql.catalog.glue.catalog-impl",
                    "org.apache.iceberg.aws.glue.GlueCatalog")
            .config("spark.sql.catalog.glue.warehouse",
                    os.getenv("S3_WAREHOUSE", "s3://my-iceberg-lake-rohan/warehouse"))
            .config("spark.sql.catalog.glue.io-impl",
                    "org.apache.iceberg.aws.s3.S3FileIO")
        )
    else:
        raise ValueError(f"Unknown mode '{mode}'. Choose 'local' or 'aws'.")

    spark = builder.getOrCreate()
    spark.sparkContext.setLogLevel("ERROR")
    return spark
