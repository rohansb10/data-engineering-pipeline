from datetime import datetime, timedelta
import os
from pathlib import Path

from airflow.decorators import dag, task
from airflow.operators.bash import BashOperator

DBT_PROJECT_DIR = os.getenv(
    "DBT_PROJECT_DIR",
    str(Path(__file__).resolve().parents[1] / "my_dbt_project"),
)

# -------------------------
# Default Arguments
# -------------------------
default_args = {
    "owner": "data-engineering",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}


# -------------------------
# DAG Definition (Decorator style)
# -------------------------
@dag(
    dag_id="ecommerce_etl_dbt_pipeline",
    default_args=default_args,
    description="End-to-end ETL pipeline with Postgres + dbt",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["etl", "dbt", "postgres"],
)
def ecommerce_etl_dbt_pipeline():
    @task
    def start_dbt():
        print("Starting dbt pipeline...")

    dbt_run_testing = BashOperator(
        task_id="dbt_run_testing",
        bash_command=f"set -euo pipefail && cd {DBT_PROJECT_DIR} && dbt run --select testing_model",
    )

    dbt_run_new = BashOperator(
        task_id="dbt_run_new",
        bash_command=f"set -euo pipefail && cd {DBT_PROJECT_DIR} && dbt run --select new",
    )

    @task
    def end_pipeline():
        print("dbt pipeline completed successfully!")

    start_dbt() >> dbt_run_testing >> dbt_run_new >> end_pipeline()


ecommerce_etl_dbt_pipeline()

