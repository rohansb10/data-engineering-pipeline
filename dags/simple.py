from __future__ import annotations

import logging
from datetime import timedelta
import pendulum

from airflow.decorators import dag, task, task_group, setup, teardown
from airflow.models.param import Param

default_args = {
    "owner": "data-engineering",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}

@dag(
    dag_id="prod_example_pipeline",
    description="Simple production-style airflow DAG",
    start_date=pendulum.datetime(2024, 1, 1, tz="UTC"),
    schedule="0 6 * * *",
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    tags=["production", "example", "data-pipeline"],
    params={
        "environment": Param("dev", type="string"),
    },
)
def production_example_dag():

    # Setup
    @setup
    def initialize_environment():
        logging.info("Setting up environment resources")

    # Extract
    @task(task_id="extract")
    def extract() -> list:
        logging.info("Extracting data from source system")
        return [1, 2, 3, 4, 5]

    # Transform
    @task(task_id="transform")
    def transform(data: list) -> list:
        logging.info("Transforming data")
        return [x * 10 for x in data]

    # Validate
    @task(task_id="validate")
    def validate(data: list) -> list:
        logging.info("Validating data")
        return [x for x in data if x > 0]

    # Branch decision (FIXED)
    @task.branch(task_id="decide_next_step")
    def decide_next_step(data):
        if len(data) > 0:
            return "load_task"   # ✅ must match actual task_id
        return "skip_task"

    # Load
    @task(task_id="load_task")
    def load(data: list):
        logging.info("Loading data to destination")
        for record in data:
            logging.info(f"Loaded value: {record}")

    # Skip
    @task(task_id="skip_task")
    def skip_load():
        logging.info("Skipping load because data is empty")

    # Teardown
    @teardown
    def cleanup():
        logging.info("Cleaning up temporary resources")

    # Task Group
    @task_group(group_id="etl_group")
    def etl_pipeline():
        raw = extract()
        transformed = transform(raw)
        validated = validate(transformed)
        return validated

    # DAG Flow
    start = initialize_environment()

    processed_data = etl_pipeline()

    decision = decide_next_step(processed_data)

    load_task = load(processed_data)
    skip_task = skip_load()

    end = cleanup()

    # Dependencies
    start >> processed_data >> decision
    decision >> [load_task, skip_task]
    [load_task, skip_task] >> end


dag = production_example_dag()