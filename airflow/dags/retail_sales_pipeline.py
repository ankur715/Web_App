"""Retail sales analytics pipeline.

Owns the day-to-day refresh of the fictional SAKS Fifth Avenue retail
dataset that Web_App's chatbot (app.py) reads from, instead of that data
being a one-time static seed baked into the FastAPI app at startup.
"""

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from airflow.sdk import dag, task

# app.py and this DAG both need shared/retail_data.py; the dags folder isn't
# a package relative to the repo root, so add it to sys.path explicitly.
WEBAPP_ROOT = Path(__file__).resolve().parents[2]
if str(WEBAPP_ROOT) not in sys.path:
    sys.path.insert(0, str(WEBAPP_ROOT))

from shared.retail_data import CUSTOMERS, PRODUCTS, STORES, generate_rows_for_date  # noqa: E402

DB_PATH = str(WEBAPP_ROOT / "retail_sales_analytics.db")
ROWS_PER_DAY = 8


@dag(
    schedule="@daily",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    default_args={"owner": "ankur", "retries": 2},
    tags=["retail", "sales-analytics"],
)
def retail_sales_pipeline():
    @task
    def generate_daily_sales() -> list[list]:
        conn = sqlite3.connect(DB_PATH)
        next_txn_num = conn.execute("SELECT COUNT(*) FROM retail_sales_sales_data").fetchone()[0] + 1
        conn.close()

        rows = generate_rows_for_date(
            target_date=datetime.today().date(),
            count=ROWS_PER_DAY,
            start_txn_num=next_txn_num,
        )
        return [list(row) for row in rows]

    @task
    def load_to_sqlite(rows: list[list]) -> int:
        conn = sqlite3.connect(DB_PATH)
        conn.executemany(
            "INSERT OR IGNORE INTO retail_sales_sales_data VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
        conn.close()
        return len(rows)

    @task.virtualenv(requirements=["pandas"], system_site_packages=False)
    def compute_daily_analytics(db_path: str):
        # Isolated venv (pandas only) so pandas never touches Airflow's own environment.
        import sqlite3

        import pandas as pd

        conn = sqlite3.connect(db_path)
        df = pd.read_sql_query("SELECT * FROM retail_sales_sales_data", conn)

        summary = (
            df.groupby(["sales_date", "store_id"])["total_sales"]
            .sum()
            .reset_index()
            .rename(columns={"total_sales": "total_revenue"})
        )

        qty_by_group = (
            df.groupby(["sales_date", "store_id", "product_id"])["quantity"].sum().reset_index()
        )
        top_idx = qty_by_group.groupby(["sales_date", "store_id"])["quantity"].idxmax()
        top_products = qty_by_group.loc[top_idx, ["sales_date", "store_id", "product_id"]].rename(
            columns={"product_id": "top_product_id"}
        )
        summary = summary.merge(top_products, on=["sales_date", "store_id"], how="left")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS retail_sales_daily_summary (
                sales_date TEXT,
                store_id TEXT,
                total_revenue REAL,
                top_product_id TEXT,
                computed_at TEXT,
                PRIMARY KEY (sales_date, store_id)
            )
        """)
        computed_at = pd.Timestamp.now("UTC").isoformat()
        conn.executemany(
            "INSERT OR REPLACE INTO retail_sales_daily_summary VALUES (?, ?, ?, ?, ?)",
            [
                (r.sales_date, r.store_id, r.total_revenue, r.top_product_id, computed_at)
                for r in summary.itertuples(index=False)
            ],
        )
        conn.commit()
        conn.close()
        print(f"Wrote {len(summary)} daily summary rows.")

    @task
    def data_quality_checks(loaded_count: int):
        valid_stores = {s[0] for s in STORES}
        valid_products = {p[0] for p in PRODUCTS}
        valid_customers = {c[0] for c in CUSTOMERS}

        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM retail_sales_sales_data ORDER BY transaction_id DESC LIMIT ?",
            (loaded_count,),
        ).fetchall()
        conn.close()

        errors = []
        for row in rows:
            if row["store_id"] not in valid_stores:
                errors.append(f"{row['transaction_id']}: unknown store_id {row['store_id']}")
            if row["product_id"] not in valid_products:
                errors.append(f"{row['transaction_id']}: unknown product_id {row['product_id']}")
            if row["customer_id"] not in valid_customers:
                errors.append(f"{row['transaction_id']}: unknown customer_id {row['customer_id']}")
            expected_total = round(row["quantity"] * row["unit_price"], 2)
            if abs(row["total_sales"] - expected_total) > 0.01:
                errors.append(
                    f"{row['transaction_id']}: total_sales {row['total_sales']} != "
                    f"quantity*unit_price {expected_total}"
                )

        if errors:
            raise ValueError("Data quality checks failed:\n" + "\n".join(errors))
        print(f"Data quality checks passed for {len(rows)} rows.")

    rows = generate_daily_sales()
    loaded_count = load_to_sqlite(rows)
    analytics = compute_daily_analytics(DB_PATH)
    data_quality_checks(loaded_count)
    loaded_count >> analytics


retail_sales_pipeline()
