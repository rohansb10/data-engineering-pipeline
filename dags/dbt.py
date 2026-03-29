from datetime import datetime, timedelta
from airflow.decorators import dag, task
from airflow.operators.bash import BashOperator

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

    # Task 1: Start
    @task
    def start_dbt():
        print("Starting dbt pipeline...")

    # Task 2: Run dbt testing_model
    dbt_run_testing = BashOperator(
        task_id="dbt_run_testing",
        bash_command="""
        cd /home/rohan/projects/airflow/my_dbt_project &&
        dbt run --select testing_model
        """,
    )

    # Task 3: Run dbt new model
    dbt_run_new = BashOperator(
        task_id="dbt_run_new",
        bash_command="""
        cd /home/rohan/projects/airflow/my_dbt_project &&
        dbt run --select new
        """,
    )

    # Task 4: End
    @task
    def end_pipeline():
        print("dbt pipeline completed successfully!")

    # -------------------------
    # Task Dependencies
    # -------------------------
    start_dbt() >> dbt_run_testing >> dbt_run_new >> end_pipeline()


# Instantiate the DAG
ecommerce_etl_dbt_pipeline()