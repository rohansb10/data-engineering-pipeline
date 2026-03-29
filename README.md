# Airflow End-to-End Project

f12 to find any lib location

This repository contains sample Apache Airflow DAGs, including a full local end-to-end pipeline:

- `e2e_local_sales_pipeline`
- `complete_feature_demo_dag`
- `ecommerce_etl_dbt_pipeline`
- `first_simple_dag`

## Run

```bash
uv sync
uv run airflow standalone
```

Open the Airflow UI, then trigger `e2e_local_sales_pipeline`.

## What the E2E DAG does

1. Extracts sample sales data into `data/raw_sales.json`
2. Transforms and enriches data into `data/transformed_sales.csv`
3. Runs data quality checks (fails fast on bad records)
4. Loads aggregated output into `data/output.csv`
5. Prints a final run report in task logs

## dbt DAG note

`ecommerce_etl_dbt_pipeline` currently uses a project path specific to this machine:

`/home/rohan/projects/airflow/my_dbt_project`

If you move this repository, update that path in `dags/dbt.py`.

airflow
iceburg
gx
pyspark
dbt
aws
logging
pydantic
snowflake
postgres