"""
olist_medallion_dag.py (TaskFlow API version)
"""

from __future__ import annotations
from datetime import datetime, timedelta
from pathlib import Path

import yaml

from airflow import DAG
from airflow.decorators import task
from airflow.providers.standard.operators.empty import EmptyOperator
from airflow.task.trigger_rule import TriggerRule


def _load_airflow_cfg() -> dict:
    defaults = {
        "schedule": "@daily",
        "catchup": False,
        "max_active_runs": 1,
        "default_retries": 2,
        "retry_delay_minutes": 5,
        "email_on_failure": False,
        "email_on_retry": False,
    }
    cfg_path = Path(__file__).resolve().parents[1] / "src" / "config" / "settings.yaml"
    if not cfg_path.exists():
        return defaults

    with cfg_path.open("r", encoding="utf-8") as fh:
        loaded = yaml.safe_load(fh) or {}

    airflow_cfg = loaded.get("airflow", {})
    return {**defaults, **airflow_cfg}


AIRFLOW_CFG = _load_airflow_cfg()

DEFAULT_ARGS = {
    "owner": "data-engineering",
    "depends_on_past": False,
    "email_on_failure": AIRFLOW_CFG["email_on_failure"],
    "email_on_retry": AIRFLOW_CFG["email_on_retry"],
    "retries": AIRFLOW_CFG["default_retries"],
    "retry_delay": timedelta(minutes=AIRFLOW_CFG["retry_delay_minutes"]),
}

with DAG(
    dag_id="medallion_pipeline_taskflow",
    description="Olist Bronze → Silver → Gold with GX quality gates",
    default_args=DEFAULT_ARGS,
    start_date=datetime(2024, 1, 1),
    schedule=AIRFLOW_CFG["schedule"],
    catchup=AIRFLOW_CFG["catchup"],
    max_active_runs=AIRFLOW_CFG["max_active_runs"],
    tags=["olist", "iceberg", "medallion", "pyspark", "great-expectations"],
) as dag:

    start = EmptyOperator(task_id="start")

    @task(execution_timeout=timedelta(minutes=30))
    def bronze_ingestion():
        from src.ingestion.bronze_ingestion import run_bronze_ingestion
        from src.utils.spark_session import get_spark_session
        spark = get_spark_session(app_name="olist-bronze-dag")

        results = run_bronze_ingestion(spark=spark)
        failed = [t for t, ok in results.items() if not ok]
        if failed:
            raise RuntimeError(f"Bronze ingestion failed for: {failed}")

    @task(execution_timeout=timedelta(minutes=10))
    def gx_bronze_checks():
        from src.quality.gx_quality_checks import run_quality_checks
        from src.utils.spark_session import get_spark_session
        spark = get_spark_session(app_name="olist-gx-bronze")
        run_quality_checks(layer="bronze", spark=spark, fail_on_critical=True)

    @task(execution_timeout=timedelta(minutes=20))
    def silver_transform():
        from src.transform.silver_transform import run_silver_transform
        from src.utils.spark_session import get_spark_session
        spark = get_spark_session(app_name="olist-silver-dag")
        run_silver_transform(spark=spark)

    @task(execution_timeout=timedelta(minutes=10))
    def gx_silver_checks():
        from src.quality.gx_quality_checks import run_quality_checks
        from src.utils.spark_session import get_spark_session
        spark = get_spark_session(app_name="olist-gx-silver")
        run_quality_checks(layer="silver", spark=spark, fail_on_critical=True)

    @task(execution_timeout=timedelta(minutes=20))
    def gold_transform():
        from src.transform.gold_transform import run_gold_transform
        from src.utils.spark_session import get_spark_session
        spark = get_spark_session(app_name="olist-gold-dag")
        run_gold_transform(spark=spark)

    @task(execution_timeout=timedelta(minutes=10))
    def gx_gold_checks():
        from src.quality.gx_quality_checks import run_quality_checks
        from src.utils.spark_session import get_spark_session
        spark = get_spark_session(app_name="olist-gx-gold")
        run_quality_checks(layer="gold", spark=spark, fail_on_critical=True)

    end_success = EmptyOperator(task_id="pipeline_success")
    end_failure = EmptyOperator(
        task_id="pipeline_failure",
        trigger_rule=TriggerRule.ONE_FAILED
    )

    # TaskFlow chaining
    b = bronze_ingestion()
    gb = gx_bronze_checks()
    s = silver_transform()
    gs = gx_silver_checks()
    g = gold_transform()
    gg = gx_gold_checks()

    start >> b >> gb >> s >> gs >> g >> gg >> [end_success, end_failure]
