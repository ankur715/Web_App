# Airflow pipeline (standalone, no Docker)

Orchestrates the daily refresh of the retail sales data that [`app.py`](../app.py)'s
chatbot reads from — see [`dags/retail_sales_pipeline.py`](dags/retail_sales_pipeline.py).

Runs as plain Apache Airflow via `airflow standalone` (SQLite metadata DB,
LocalExecutor) — no Docker, no Astro CLI. Kept in its own virtualenv,
separate from the FastAPI app's dependencies.

## Setup

```bash
cd airflow
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export AIRFLOW_HOME="$(pwd)/airflow_home"
airflow standalone
```

First run prints an admin password to the terminal (also saved to
`airflow_home/standalone_admin_password.txt`). Open http://localhost:8080,
log in, and unpause `retail_sales_pipeline`.

`AIRFLOW_HOME` keeps all of Airflow's logs/metadata/config inside
`airflow/airflow_home/` (gitignored) rather than `~/airflow`.

## What the pipeline does

1. `generate_daily_sales` — simulate today's new transactions (uses
   [`shared/retail_data.py`](../shared/retail_data.py), the same catalog/generator
   `app.py` seeds from, so there's one source of truth for the dummy data).
2. `load_to_sqlite` — insert those rows into `Web_App/retail_sales_analytics.db`.
3. `compute_daily_analytics` — pandas aggregation (revenue by store/day, top
   product) into a new `retail_sales_daily_summary` table. Runs via
   `PythonVirtualenvOperator` (`@task.virtualenv`) so pandas is installed into
   its own throwaway venv per run, never into Airflow's base environment.
4. `data_quality_checks` — rejects the run if any newly loaded row references
   an unknown store/product/customer, or `total_sales != quantity * unit_price`.

## Tests

```bash
pip install pytest
AIRFLOW_HOME="$(pwd)/airflow_home" pytest tests/
```
