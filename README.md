# Airflow End-to-End Project

f12 to find any lib location 
## Run

```bash
uv sync
uv run airflow standalone
```
# 🛢️ Olist Medallion Pipeline

> A production-grade, end-to-end data engineering pipeline built on the **Medallion Architecture** (Bronze → Silver → Gold), powered by **Apache Spark**, **Apache Airflow**, **Apache Iceberg**, and **Great Expectations** — orchestrated locally with full data quality gates at every layer.

[![Python](https://img.shields.io/badge/python-3.12-blue?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![Airflow](https://img.shields.io/badge/Apache%20Airflow-3.1.7-017CEE?style=flat-square&logo=apacheairflow&logoColor=white)](https://airflow.apache.org)
[![PySpark](https://img.shields.io/badge/PySpark-4.1.1-orange?style=flat-square&logo=apachespark&logoColor=white)](https://spark.apache.org)
[![Iceberg](https://img.shields.io/badge/Apache%20Iceberg-1.10.1-3FBAD8?style=flat-square)](https://iceberg.apache.org)
[![Great Expectations](https://img.shields.io/badge/Great%20Expectations-1.15.1-FF5A5F?style=flat-square)](https://greatexpectations.io)
[![dbt](https://img.shields.io/badge/dbt-1.11.6-FF694B?style=flat-square&logo=dbt&logoColor=white)](https://getdbt.com)
[![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)

---

## 📋 Table of Contents

- [Overview](#-overview)
- [Architecture](#-architecture)
- [Project Structure](#-project-structure)
- [DAGs](#-dags)
- [Data Quality](#-data-quality-great-expectations)
- [Bronze Layer — Ingestion](#-bronze-layer--ingestion)
- [Silver Layer — Transformation](#-silver-layer--transformation)
- [Gold Layer — Aggregation](#-gold-layer--aggregation)
- [Configuration](#-configuration)
- [Getting Started](#-getting-started)
- [Running Tests](#-running-tests)
- [Known Issues & Fixes](#-known-issues--fixes)

---

## 🔍 Overview

This project implements a full **local Medallion Architecture** on the [Brazilian E-Commerce (Olist) dataset](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce), processing **~1.5M+ rows** across 9 source tables through Bronze, Silver, and Gold Iceberg layers — with **Great Expectations quality gates** that block the pipeline on any critical failure.

### What gets processed

| Source Table | Rows Ingested |
|---|---|
| `customers_dataset.csv` | 99,441 |
| `orders_dataset.csv` | 99,441 |
| `order_items_dataset.csv` | 112,650 |
| `order_payments_dataset.csv` | 103,886 |
| `order_reviews_dataset.csv` | 100,034 |
| `products_dataset.csv` | 32,951 |
| `sellers_dataset.csv` | 3,095 |
| `geolocation_dataset.csv` | 1,000,163 |
| `product_category_name_translation.csv` | 71 |

### Gold outputs produced

| Gold Table | Rows | Description |
|---|---|---|
| `gold_order_summary` | 99,441 | Per-order enriched fact table |
| `gold_revenue_by_order` | 98,666 | Revenue + freight per order |
| `gold_state_payment_agg` | 107 | KPIs grouped by state × payment type |

---

## 🏛️ Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                    DATA SOURCES (CSV)                            │
│  customers │ orders │ payments │ reviews │ items │ products ...  │
└──────────────────────────┬───────────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────────┐
│              🥉 BRONZE LAYER  (local.db.*)                       │
│         Raw CSV → Iceberg tables, partitioned, Snappy            │
│         Append-only, schema-on-read, no transformation           │
└──────────────────────────┬───────────────────────────────────────┘
                           │  ✅ GX Bronze Quality Gate
┌──────────────────────────▼───────────────────────────────────────┐
│              🥈 SILVER LAYER  (local.db.silver_*)                │
│   Deduplication │ Type casting │ Null drops │ Derived columns    │
│   delivery_days │ is_late │ review_category (good/neutral/bad)   │
└──────────────────────────┬───────────────────────────────────────┘
                           │  ✅ GX Silver Quality Gate
┌──────────────────────────▼───────────────────────────────────────┐
│              🥇 GOLD LAYER  (local.db.gold_*)                    │
│   Multi-table joins │ KPI aggregations │ BI/ML ready             │
│   gold_order_summary │ gold_revenue_by_order │ gold_state_agg    │
└──────────────────────────┬───────────────────────────────────────┘
                           │  ✅ GX Gold Quality Gate
                    Analytics / ML
```

### Airflow DAG Flow

```
start
  │
  ▼
bronze_ingestion        (timeout: 30 min)
  │
  ▼
gx_bronze_checks        ← halts pipeline on critical failure
  │
  ▼
silver_transform        (timeout: 20 min)
  │
  ▼
gx_silver_checks        ← halts pipeline on critical failure
  │
  ▼
gold_transform          (timeout: 20 min)
  │
  ▼
gx_gold_checks          ← halts pipeline on critical failure
  │
  ├──► pipeline_success
  └──► pipeline_failure  (trigger_rule: ONE_FAILED)
```

---

## 📁 Project Structure

```
olist-pipeline/
│
├── 📂 dags/
│   ├── olist_medallion_dag.py       # Main Medallion pipeline (TaskFlow API)
│   ├── taskflow_orders_pipeline.py  # Typed TaskFlow example with tax enrichment
│   ├── simple.py                    # Production-style DAG with task groups & branching
│   └── dbt.py                       # Postgres + dbt ETL pipeline
│
├── 📂 src/
│   ├── ingestion/
│   │   └── bronze_ingestion.py      # CSV → Iceberg Bronze writer (retry logic)
│   ├── transform/
│   │   ├── silver_transform.py      # Bronze → Silver cleansing & enrichment
│   │   └── gold_transform.py        # Silver → Gold joins & KPI aggregations
│   ├── quality/
│   │   └── gx_quality_checks.py     # Great Expectations layer runner
│   ├── utils/
│   │   ├── spark_session.py         # SparkSession factory (local + AWS modes)
│   │   └── logger.py                # Rotating file + console logger
│   ├── config/
│   │   └── settings.yaml            # Runtime config (Spark, Iceberg, paths)
│   └── test/
│       ├── test_bronze_ingestion.py
│       ├── test_gx_quality_checks.py
│       └── test_silver_transform.py
│
├── 📂 gx/
│   └── suites/
│       ├── bronze_orders_suite.yml
│       ├── bronze_customers_suite.yml
│       ├── silver_order_payments_suite.yml
│       └── gold_order_summary_suite.yml
│
├── 📂 logs/                         # Per-module rotating logs
├── pyproject.toml
├── setup.py
└── README.md
```

---

## 🔄 DAGs

### `medallion_pipeline_taskflow` ⭐ Main DAG

The primary end-to-end pipeline. Triggers daily, runs all three Medallion layers with GX quality gates between each. Uses the **TaskFlow API** throughout — tasks share data via XCom automatically.

```bash
airflow dags trigger medallion_pipeline_taskflow
```

**Tags:** `olist`, `iceberg`, `medallion`, `pyspark`, `great-expectations`  
**Schedule:** Daily | **Max active runs:** 1 | **Retries:** 2 with 5-min delay

---

### `taskflow_orders_pipeline`

A typed TaskFlow API demonstration showing extract → transform → validate → load → report with `TypedDict` contracts (`Order`, `EnrichedOrder`, `LoadSummary`) and Airflow Variable-based tax rate overrides per run.

---

### `prod_example_pipeline`

A production-style DAG demonstrating task groups, branching (`@task.branch`), and setup/teardown lifecycle tasks. Runs daily at **06:00 UTC**.

---

### `ecommerce_etl_dbt_pipeline`

Postgres + dbt pipeline that runs `dbt run --select testing_model` then `dbt run --select new`.

> ⚠️ **Note:** The dbt project path is hardcoded. Update it in `dags/dbt.py` if you move this repo:
> ```python
> bash_command="cd /your/path/to/my_dbt_project && dbt run --select testing_model"
> ```

---

## ✅ Data Quality (Great Expectations)

Quality gates run after every Medallion layer. Each suite is defined in YAML under `gx/suites/` and loaded at runtime — no code changes needed to update checks. A critical failure immediately halts the pipeline via `RuntimeError`.

### Suite Coverage

| Suite | Layer | Checks |
|---|---|---|
| `bronze_orders_suite.yml` | Bronze | Schema, nulls, uniqueness, `order_status` enum (8 values), row count |
| `bronze_customers_suite.yml` | Bronze | Schema, nulls, uniqueness, `customer_state` length=2, row count |
| `silver_order_payments_suite.yml` | Silver | Payment type enum, `payment_value` range, nulls, uniqueness |
| `gold_order_summary_suite.yml` | Gold | 19 checks: all columns, `review_category` enum, `is_late` flag, score/day/payment ranges |

### Latest validation results

```
✅ local.db.orders                  passed=12  failed=0  [CRITICAL]
✅ local.db.customers               passed=10  failed=0  [CRITICAL]
✅ local.db.silver_order_payments   passed=10  failed=0  [CRITICAL]
✅ local.db.gold_order_summary      passed=19  failed=0  [CRITICAL]
```

### Running checks manually

```bash
# Per-layer
python -m src.quality.gx_quality_checks --layer bronze
python -m src.quality.gx_quality_checks --layer silver
python -m src.quality.gx_quality_checks --layer gold
python -m src.quality.gx_quality_checks --layer all

# Report-only (no pipeline halt on failure)
python -m src.quality.gx_quality_checks --layer all --no-fail
```

---

## 🥉 Bronze Layer — Ingestion

Reads all 9 raw Olist CSVs and writes them to Iceberg tables under `local.db` with Snappy compression. All writes use `createOrReplace` — safe to re-run idempotently.

**Key behaviours:**
- `multiLine=true` on CSV reads handles embedded newlines in `order_reviews`
- Per-table retry logic (3 attempts by default)
- Returns `dict[table → bool]` — the Airflow task raises `RuntimeError` on any failure

```bash
python -m src.ingestion.bronze_ingestion
```

### Partitioning strategy

| Table | Partition Column |
|---|---|
| `customers` | `customer_state` |
| `geolocation` | `geolocation_state` |
| `orders` | `order_status` |
| `order_payments` | `payment_type` |
| `products` | `product_category_name` |
| `sellers` | `seller_state` |
| `order_items`, `order_reviews`, `product_category_translation` | *(none)* |

---

## 🥈 Silver Layer — Transformation

Cleans and enriches Bronze tables into Silver. Each table transformation runs independently — partial failures are collected and logged; the script exits non-zero at the end if any table failed.

### Transformations applied

| Silver Table | Key Operations |
|---|---|
| `silver_orders` | Cast timestamps, `dropDuplicates`, add `delivery_days` (datediff), add `is_late` (0/1) |
| `silver_customers` | Deduplicate on `customer_id`, drop nulls |
| `silver_order_reviews` | `try_cast` review_score → INT (fixes `CAST_INVALID_INPUT`), add `review_category` |
| `silver_order_payments` | Dedup, drop null `payment_value`, drop `payment_sequential` |
| `silver_order_items` | Dedup on `order_id`, drop nulls |
| `silver_products` | Left-join with `product_category_translation` for English names |

```bash
python -m src.transform.silver_transform
```

---

## 🥇 Gold Layer — Aggregation

Produces three business-ready Iceberg tables from Silver inputs.

### `gold_order_summary`

Per-order enriched fact table joining `silver_orders` ▷ `silver_customers` ▷ `silver_order_reviews` ▷ `silver_order_payments`. Includes `delivery_days`, `is_late`, `review_category`, `payment_type`, `payment_value`.

### `gold_revenue_by_order`

Aggregates `silver_order_items` to order level: `total_revenue`, `total_freight`, `gross_amount`.

### `gold_state_payment_agg`

KPI rollup by `customer_state × payment_type`: total orders, avg payment value, avg review score, avg delivery days, late delivery percentage.

```bash
python -m src.transform.gold_transform
```

---

## ⚙️ Configuration

All runtime settings live in `src/config/settings.yaml`.

```yaml
spark:
  app_name: olist-pipeline
  mode: local          # 'local' | 'aws'
  master: "local[*]"

paths:
  data_root:   /path/to/data
  warehouse:   /path/to/iceberg_warehouse
  iceberg_jar: /path/to/iceberg-spark-runtime.jar

iceberg:
  format: parquet
  compression: snappy
  max_records_per_file: 500000
  coalesce_partitions: 3
```

### Environment variable overrides

| Variable | Description |
|---|---|
| `ICEBERG_JAR` | Path to the Iceberg Spark runtime JAR |
| `ICEBERG_WAREHOUSE` | Local Iceberg warehouse root directory |
| `SPARK_SQL_SHUFFLE_PARTITIONS` | Spark shuffle partitions (default: `200`) |
| `LOG_DIR` | Log output directory |
| `LOG_LEVEL` | Logging level (default: `INFO`) |
| `S3_WAREHOUSE` | S3 warehouse path (AWS mode only) |

### Switching to AWS mode

The `SparkSession` factory supports AWS Glue catalog out of the box:

```python
from src.utils.spark_session import get_spark_session
spark = get_spark_session(app_name="olist-prod", mode="aws")
```

Set `S3_WAREHOUSE=s3://your-bucket/warehouse` and ensure AWS credentials are available via environment or instance profile.

---

## 🚀 Getting Started

### Prerequisites

- Python 3.12
- Java 11+ (required by Spark)
- [`uv`](https://github.com/astral-sh/uv) package manager

### 1. Clone & install

```bash
git clone https://github.com/your-username/olist-pipeline.git
cd olist-pipeline
uv sync
```

### 2. Download the Olist dataset

Download from [Kaggle](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) and place all CSV files in the `data/` directory (or update `data_root` in `settings.yaml`).

### 3. Start Airflow

```bash
uv run airflow standalone
```

Open `http://localhost:8080`, then trigger `medallion_pipeline_taskflow`.

### 4. Run pipeline stages manually

```bash
# Stage by stage
python -m src.ingestion.bronze_ingestion
python -m src.transform.silver_transform
python -m src.transform.gold_transform
python -m src.quality.gx_quality_checks --layer all
```

---

## 🧪 Running Tests

```bash
# All tests
uv run pytest src/test/ -v

# Individual test files
uv run pytest src/test/test_bronze_ingestion.py -v
uv run pytest src/test/test_silver_transform.py -v
uv run pytest src/test/test_gx_quality_checks.py -v
```

Tests use in-memory Spark DataFrames and mock Iceberg writes — no catalog or real data required.

### Test coverage

| Test File | What it covers |
|---|---|
| `test_bronze_ingestion.py` | Happy path, retry-on-failure, return dict shape |
| `test_silver_transform.py` | Null drops, `delivery_days` derivation, `review_category` mapping |
| `test_gx_quality_checks.py` | Suite loading & reuse, critical failure raises `RuntimeError`, `--no-fail` suppression |

---

## 🐛 Known Issues & Fixes

### `CAST_INVALID_INPUT` on `silver_order_reviews`

**Symptom:** Silver transform fails with `The value '2018-06-10 00:00:00' cannot be cast to BIGINT`.

**Cause:** Some rows in `order_reviews_dataset.csv` have timestamp strings in the `review_score` column instead of integers.

**Fix applied in `silver_transform.py`:**

```python
.withColumn(
    "review_score",
    expr("try_cast(trim(cast(review_score as string)) as int)"),
)
```

`try_cast` returns `NULL` for malformed inputs instead of raising — downstream `review_category` handles nulls gracefully as `"unknown"`.

---

### Silver/Gold tables not found on first run

**Symptom:** GX checks for Silver or Gold fail with `TABLE_OR_VIEW_NOT_FOUND`.

**Cause:** Quality checks ran before the transform tasks completed, or stages were executed out of order.

**Fix:** Always run in sequence: Bronze → GX Bronze → Silver → GX Silver → Gold → GX Gold. The Airflow DAG enforces this automatically via task dependencies.

---

### dbt path is machine-specific

**Symptom:** `ecommerce_etl_dbt_pipeline` fails immediately on any machine other than the original.

**Fix:** Update the path in `dags/dbt.py`:

```python
bash_command="cd /your/absolute/path/to/my_dbt_project && dbt run --select testing_model"
```

---

## 📦 Dependencies

Managed via `pyproject.toml`, installed with `uv sync`.

| Package | Version | Purpose |
|---|---|---|
| `apache-airflow` | 3.1.7 | Pipeline orchestration & scheduling |
| `pyspark` | 4.1.1 | Distributed data processing |
| `great-expectations` | 1.15.1 | Data quality validation |
| `dbt-core` | 1.11.6 | SQL transformation layer |
| `dbt-postgres` | 1.10.0 | dbt Postgres adapter |
| `pandas` | 2.3.3 | Local DataFrame utilities |
| `pytest` | 9.0.2 | Unit testing framework |

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

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