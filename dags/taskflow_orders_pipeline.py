from __future__ import annotations

import logging
from typing import Any, TypedDict

import pendulum
from airflow.decorators import dag, task
from airflow.models import Variable

log = logging.getLogger(__name__)

TAX_RATE_DEFAULT = 1.10


# --------------------------------------------------------------------------- #
# Typed contracts — makes field-level bugs fail at import time, not runtime   #
# --------------------------------------------------------------------------- #

class Order(TypedDict):
    order_id: int
    customer: str
    amount: float


class EnrichedOrder(Order):
    amount_with_tax: float


class LoadSummary(TypedDict):
    total_orders: int
    total_revenue: float
    customers: list[str]


# --------------------------------------------------------------------------- #
# DAG                                                                          #
# --------------------------------------------------------------------------- #

@dag(
    dag_id="taskflow_orders_pipeline",
    description="Airflow 2.6+ TaskFlow API example: extract, transform, validate, load",
    schedule="@daily",
    start_date=pendulum.datetime(2024, 1, 1, tz="UTC"),
    catchup=False,
    default_args={"owner": "data-team", "retries": 1},
    tags=["taskflow", "airflow-2-6", "example"],
    params={"tax_rate": TAX_RATE_DEFAULT},  # overridable per-run via Airflow UI / trigger
)
def taskflow_orders_pipeline() -> None:

    @task(task_id="extract")
    def extract(**context: Any) -> list[Order]:
        """Pull raw orders from the source system.

        Replace the stub below with your actual source call
        (e.g. a database hook, an HTTP sensor result, or an S3 read).
        """
        execution_date: str = context["ds"]  # YYYY-MM-DD; use for idempotent fetches
        log.info("Extracting orders for execution_date=%s", execution_date)

        # --- stub: replace with real source ---
        rows: list[Order] = [
            {"order_id": 1, "customer": "Asha", "amount": 120.0},
            {"order_id": 2, "customer": "Liam", "amount": 80.5},
            {"order_id": 3, "customer": "Asha", "amount": 99.0},
        ]
        # --------------------------------------

        if not rows:
            raise ValueError(f"No orders found for {execution_date}")

        log.info("Extracted %d rows", len(rows))
        return rows

    @task(task_id="transform")
    def transform(rows: list[Order], **context: Any) -> list[EnrichedOrder]:
        """Apply tax enrichment.

        Tax rate is read from Airflow Variables first, then falls back to the
        DAG-level param so individual runs can override it without a code change.
        """
        tax_rate: float = float(
            Variable.get("orders_tax_rate", default_var=context["params"]["tax_rate"])
        )
        log.info("Applying tax_rate=%.4f to %d rows", tax_rate, len(rows))

        return [
            EnrichedOrder(
                **row,
                amount_with_tax=round(row["amount"] * tax_rate, 2),
            )
            for row in rows
        ]

    @task(task_id="validate")
    def validate(rows: list[EnrichedOrder]) -> list[EnrichedOrder]:
        """Fail-fast validation: collect ALL invalid rows before raising."""
        if not rows:
            raise ValueError("Validation failed: received empty dataset.")

        invalid: list[str] = [
            f"order_id={r['order_id']} amount_with_tax={r['amount_with_tax']}"
            for r in rows
            if r["amount_with_tax"] <= 0
        ]

        if invalid:
            raise ValueError(
                f"Validation failed — {len(invalid)} invalid record(s):\n"
                + "\n".join(invalid)
            )

        log.info("All %d rows passed validation", len(rows))
        return rows

    @task(task_id="load")
    def load(rows: list[EnrichedOrder], **context: Any) -> LoadSummary:
        """Aggregate and persist.

        In production, write to your warehouse here using execution_date
        as the partition key to guarantee idempotent reruns:

            warehouse.write(
                table="orders_daily",
                partition=context["ds"],
                data=rows,
                mode="overwrite",   # safe to re-run
            )
        """
        execution_date: str = context["ds"]

        summary = LoadSummary(
            total_orders=len(rows),
            total_revenue=round(sum(r["amount_with_tax"] for r in rows), 2),
            customers=sorted({r["customer"] for r in rows}),
        )

        log.info(
            "Load complete | date=%s orders=%d revenue=%.2f customers=%s",
            execution_date,
            summary["total_orders"],
            summary["total_revenue"],
            ",".join(summary["customers"]),
        )
        return summary

    @task(task_id="report")
    def report(summary: LoadSummary) -> None:
        """Emit the final pipeline summary to Airflow task logs."""
        log.info(
            "Pipeline complete | orders=%d revenue=%.2f customers=%s",
            summary["total_orders"],
            summary["total_revenue"],
            ",".join(summary["customers"]),
        )

    # ------------------------------------------------------------------ #
    # Wire the pipeline                                                    #
    # ------------------------------------------------------------------ #
    raw      = extract()
    enriched = transform(raw)
    valid    = validate(enriched)
    summary  = load(valid)
    report(summary)


taskflow_orders_pipeline()