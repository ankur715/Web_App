"""Single source of truth for the fictional SAKS Fifth Avenue retail catalog
and sales-row generator, shared by app.py (one-time seed) and the Airflow
pipeline (daily incremental refresh)."""

import random
from datetime import date

PRODUCTS = [
    ("NIKE_001", "Nike Air Max 90", "Shoes", "Nike", 129.99),
    ("NIKE_002", "Nike Air Max 95", "Shoes", "Nike", 139.99),
    ("NIKE_003", "Nike Blazer", "Shoes", "Nike", 109.99),
    ("ADIDAS_001", "Adidas Ultraboost", "Shoes", "Adidas", 179.99),
    ("ADIDAS_002", "Adidas Stan Smith", "Shoes", "Adidas", 89.99),
    ("GUCCI_001", "Gucci GG Marmont", "Bags", "Gucci", 1290.00),
    ("GUCCI_002", "Gucci Soho", "Bags", "Gucci", 1150.00),
    ("PRADA_001", "Prada Nylon Backpack", "Bags", "Prada", 1450.00),
    ("COACH_001", "Coach Signature Tote", "Bags", "Coach", 295.00),
    ("CHANEL_001", "Chanel Classic Flap", "Bags", "Chanel", 5800.00),
    ("LV_001", "Louis Vuitton Speedy", "Bags", "Louis Vuitton", 1450.00),
    ("ROLEX_001", "Rolex Submariner", "Watches", "Rolex", 9150.00),
    ("OMEGA_001", "Omega Seamaster", "Watches", "Omega", 5200.00),
]

STORES = [
    ("STORE_001", "SAKS Fifth Avenue - NYC", "New York", "NY", "10022"),
    ("STORE_002", "SAKS Fifth Avenue - LA", "Los Angeles", "CA", "90210"),
    ("STORE_003", "SAKS Fifth Avenue - Chicago", "Chicago", "IL", "60611"),
    ("STORE_004", "SAKS Fifth Avenue - Miami", "Miami", "FL", "33139"),
    ("STORE_005", "SAKS Fifth Avenue - Boston", "Boston", "MA", "02116"),
]

CUSTOMERS = [
    ("CUST_001", "John Smith", "john@email.com", "Gold", 5432.10),
    ("CUST_002", "Jane Doe", "jane@email.com", "Platinum", 12543.50),
    ("CUST_003", "Michael Brown", "michael@email.com", "Silver", 3210.75),
    ("CUST_004", "Sarah Johnson", "sarah@email.com", "Platinum", 18765.25),
    ("CUST_005", "David Lee", "david@email.com", "Gold", 7654.80),
    ("CUST_006", "Emily Davis", "emily@email.com", "Silver", 2100.40),
    ("CUST_007", "Chris Wilson", "chris@email.com", "Gold", 6890.15),
    ("CUST_008", "Amanda Clark", "amanda@email.com", "Platinum", 22310.00),
]


def generate_sales_rows(num_months: int = 6, rows_per_month: int = 18) -> list[tuple]:
    """Backfill generator: deterministic (fixed seed) rows spanning the last
    `num_months` months, used once by app.py to seed an empty database."""
    rng = random.Random(42)
    rows = []
    txn_num = 1
    today = date.today()

    for month_offset in range(num_months, -1, -1):
        year = today.year
        month = today.month - month_offset
        while month <= 0:
            month += 12
            year -= 1

        for _ in range(rows_per_month):
            day = rng.randint(1, 28)
            sales_date = date(year, month, day)
            rows.append(_make_row(rng, f"TXN_{txn_num:04d}", sales_date))
            txn_num += 1

    return rows


def generate_rows_for_date(target_date: date, count: int) -> list[tuple]:
    """Idempotent generator: deterministic rows for `target_date`, seeded and
    keyed by the date itself so re-running the same date always produces the
    same rows (same ids, same content) rather than piling on duplicates. Used
    by the Airflow pipeline for the daily refresh."""
    date_key = target_date.strftime("%Y%m%d")
    rng = random.Random(date_key)
    rows = []
    for i in range(count):
        txn_id = f"TXN_D{date_key}_{i:03d}"
        rows.append(_make_row(rng, txn_id, target_date))
    return rows


def _make_row(rng: random.Random, txn_id: str, sales_date: date) -> tuple:
    product = rng.choice(PRODUCTS)
    store = rng.choice(STORES)
    customer = rng.choice(CUSTOMERS)
    quantity = rng.randint(1, 4)
    unit_price = product[4]
    total_sales = round(quantity * unit_price, 2)
    return (
        txn_id,
        store[0],
        product[0],
        customer[0],
        quantity,
        unit_price,
        total_sales,
        sales_date.isoformat(),
        sales_date.strftime("%Y-%m"),
        sales_date.year,
    )
