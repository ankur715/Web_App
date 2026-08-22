# app.py - Retail Sales Analytics Chatbot (SQLite version, no BigQuery billing needed)
#
# A small FastAPI backend that:
#   1. Spins up a local SQLite database with dummy SAKS Fifth Avenue
#      retail sales / inventory data (created automatically on first run).
#   2. Exposes a /chat endpoint that turns a natural-language question
#      ("how much did we sell of Nike shoes last month?") into SQL using
#      the Gemini API, runs it against SQLite, and returns a plain-English
#      summary plus the raw data.

import json
import os
import random
import re
import sqlite3
from datetime import date

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from google import genai
from pydantic import BaseModel

load_dotenv()

app = FastAPI(title="Retail Sales Analytics Chatbot")

# CORS - open for local dev; lock this down before deploying anywhere real.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# LLM setup (Google Gemini via the current `google-genai` SDK)
# ---------------------------------------------------------------------------
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

genai_client = None
if GOOGLE_API_KEY:
    try:
        genai_client = genai.Client(api_key=GOOGLE_API_KEY)
        print(f"✓ Gemini client initialized (model={GEMINI_MODEL})")
    except Exception as e:  # pragma: no cover
        print(f"❌ Gemini client initialization error: {e}")
else:
    print("⚠️  GOOGLE_API_KEY not set - /chat will return an error until it's configured. "
          "Copy .env.example to .env and add your key.")

# ---------------------------------------------------------------------------
# SQLite database setup
# ---------------------------------------------------------------------------
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "retail_sales_analytics.db")

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


def _generate_sales_rows(num_months: int = 6, rows_per_month: int = 18):
    """Generate deterministic-but-varied dummy sales rows spanning the last
    `num_months` months (relative to today), so time-based questions like
    'last month' or 'this year' actually return data."""
    rng = random.Random(42)  # fixed seed -> same dummy data every run
    rows = []
    txn_num = 1
    today = date.today()

    for month_offset in range(num_months, -1, -1):
        # Roughly step back `month_offset` months from today
        year = today.year
        month = today.month - month_offset
        while month <= 0:
            month += 12
            year -= 1

        for _ in range(rows_per_month):
            day = rng.randint(1, 28)
            sales_date = date(year, month, day)
            product = rng.choice(PRODUCTS)
            store = rng.choice(STORES)
            customer = rng.choice(CUSTOMERS)
            quantity = rng.randint(1, 4)
            unit_price = product[4]
            total_sales = round(quantity * unit_price, 2)

            txn_id = f"TXN_{txn_num:04d}"
            rows.append((
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
            ))
            txn_num += 1

    return rows


def init_database():
    """Create tables and insert dummy data (only if empty)."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS retail_sales_products (
            product_id TEXT PRIMARY KEY,
            product_name TEXT,
            category TEXT,
            brand TEXT,
            unit_price REAL
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS retail_sales_stores (
            store_id TEXT PRIMARY KEY,
            store_name TEXT,
            city TEXT,
            state TEXT,
            zip_code TEXT
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS retail_sales_sales_data (
            transaction_id TEXT PRIMARY KEY,
            store_id TEXT,
            product_id TEXT,
            customer_id TEXT,
            quantity INTEGER,
            unit_price REAL,
            total_sales REAL,
            sales_date TEXT,
            sales_month TEXT,
            sales_year INTEGER
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS retail_sales_inventory (
            inventory_id TEXT PRIMARY KEY,
            store_id TEXT,
            product_id TEXT,
            quantity_on_hand INTEGER,
            reorder_level INTEGER
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS retail_sales_customers (
            customer_id TEXT PRIMARY KEY,
            customer_name TEXT,
            email TEXT,
            loyalty_status TEXT,
            lifetime_value REAL
        )
    ''')

    c.execute("SELECT COUNT(*) FROM retail_sales_products")
    if c.fetchone()[0] == 0:
        c.executemany("INSERT INTO retail_sales_products VALUES (?, ?, ?, ?, ?)", PRODUCTS)
        c.executemany("INSERT INTO retail_sales_stores VALUES (?, ?, ?, ?, ?)", STORES)
        c.executemany("INSERT INTO retail_sales_customers VALUES (?, ?, ?, ?, ?)", CUSTOMERS)
        c.executemany(
            "INSERT INTO retail_sales_sales_data VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            _generate_sales_rows(),
        )

        rng = random.Random(7)
        inventory_rows = []
        inv_num = 1
        for store in STORES:
            for product in rng.sample(PRODUCTS, k=6):
                inventory_rows.append((
                    f"INV_{inv_num:04d}",
                    store[0],
                    product[0],
                    rng.randint(5, 60),
                    rng.randint(5, 20),
                ))
                inv_num += 1
        c.executemany(
            "INSERT INTO retail_sales_inventory VALUES (?, ?, ?, ?, ?)", inventory_rows
        )

        conn.commit()
        print("✓ Database initialized with dummy data")
    else:
        print("✓ Database already has data")

    conn.close()


init_database()


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------
class ChatMessage(BaseModel):
    message: str


class ChatResponse(BaseModel):
    question: str
    sql_query: str
    query_result: dict
    summary: str
    data_points: list


# ---------------------------------------------------------------------------
# NL -> SQL -> summary pipeline
# ---------------------------------------------------------------------------
SCHEMA_DESCRIPTION = """
1. retail_sales_products (product_id, product_name, category, brand, unit_price)
2. retail_sales_sales_data (transaction_id, store_id, product_id, customer_id, quantity,
                      unit_price, total_sales, sales_date, sales_month, sales_year)
   - sales_date is 'YYYY-MM-DD', sales_month is 'YYYY-MM', sales_year is an integer.
3. retail_sales_inventory (inventory_id, store_id, product_id, quantity_on_hand, reorder_level)
4. retail_sales_stores (store_id, store_name, city, state, zip_code)
5. retail_sales_customers (customer_id, customer_name, email, loyalty_status, lifetime_value)
"""

TODAY_STR = date.today().isoformat()


def _require_llm():
    if genai_client is None:
        raise HTTPException(
            status_code=503,
            detail="GOOGLE_API_KEY is not configured on the server. "
                   "Add it to backend/.env and restart the app.",
        )


def generate_sql_from_query(user_question: str) -> str:
    """Use Gemini to convert a natural-language question into a SQLite query."""
    prompt = f"""You are a SQLite SQL expert. Convert the business question into a single
read-only SQLite SELECT query.

Today's date is {TODAY_STR}. Use this to resolve relative time references such as
"last month", "this year", or "last 30 days" against sales_date / sales_month / sales_year.

Available tables:
{SCHEMA_DESCRIPTION}

Rules:
- Only ever produce a SELECT statement (no INSERT/UPDATE/DELETE/DROP/ALTER/PRAGMA).
- Return ONLY the raw SQL, no markdown fences, no explanation.

User question: "{user_question}"
"""

    response = genai_client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
    sql_query = (response.text or "").strip()

    # Strip markdown fences if the model added them anyway.
    if sql_query.startswith("```"):
        sql_query = sql_query.strip("`")
        if sql_query.lower().startswith("sql"):
            sql_query = sql_query[3:]

    return sql_query.strip().rstrip(";")


def _is_safe_select(sql_query: str) -> bool:
    """Very small guard: only allow single, read-only SELECT statements."""
    normalized = sql_query.strip().lower()
    if not normalized.startswith("select"):
        return False
    forbidden = ["insert", "update", "delete", "drop", "alter", "attach", "pragma", ";"]
    return not any(word in normalized for word in forbidden)


def execute_sqlite_query(sql_query: str) -> dict:
    """Execute a validated read-only query against SQLite."""
    if not _is_safe_select(sql_query):
        return {
            "success": False,
            "error": "Generated query was rejected because it wasn't a safe read-only SELECT.",
            "rows": [],
        }

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute(sql_query)
        rows = [dict(row) for row in c.fetchall()]
        conn.close()
        return {"success": True, "rows": rows, "row_count": len(rows)}
    except Exception as e:
        return {"success": False, "error": str(e), "rows": []}


def generate_summary(question: str, sql_result: dict) -> str:
    """Use Gemini to summarize the query result in plain English."""
    if not sql_result["success"]:
        return f"I couldn't answer that: {sql_result['error']}"

    rows = sql_result["rows"]
    if not rows:
        return "No data found matching your question."

    data_text = json.dumps(rows[:50], indent=2, default=str)

    prompt = f"""You are a retail analytics assistant. Answer the user's question using only
the data below. Be specific with numbers (dollar amounts, quantities, names).

Question: "{question}"

Data:
{data_text}

Write a 2-3 sentence answer:
"""
    response = genai_client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
    return (response.text or "").strip()


def extract_data_points(data: dict) -> list:
    """Pull out a handful of key numeric values for quick display (e.g. charts)."""
    points = []
    for row in data.get("rows", []):
        for key, value in row.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                points.append({"label": key, "value": value})
    return points[:5]


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "database": "SQLite",
        "db_file": DB_PATH,
        "llm_configured": genai_client is not None,
        "model": GEMINI_MODEL,
    }


@app.post("/chat")
async def chat(msg: ChatMessage) -> ChatResponse:
    """Main chatbot endpoint: question in, SQL + data + summary out."""
    _require_llm()
    user_question = msg.message

    sql_query = generate_sql_from_query(user_question)
    query_result = execute_sqlite_query(sql_query)
    summary = generate_summary(user_question, query_result)
    data_points = extract_data_points(query_result)

    return ChatResponse(
        question=user_question,
        sql_query=sql_query,
        query_result=query_result,
        summary=summary,
        data_points=data_points,
    )


@app.get("/tables")
async def list_tables():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in c.fetchall()]
    conn.close()
    return {"database": "SQLite", "tables": tables}


@app.get("/schema/{table_name}")
async def get_table_schema(table_name: str):
    if not re.fullmatch(r"[A-Za-z0-9_]+", table_name):
        raise HTTPException(status_code=400, detail="Invalid table name")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(f"PRAGMA table_info({table_name})")
    columns = c.fetchall()
    conn.close()

    if not columns:
        raise HTTPException(status_code=404, detail=f"Table '{table_name}' not found")

    schema = [
        {"name": col[1], "type": col[2], "notnull": col[3], "default": col[4], "pk": col[5]}
        for col in columns
    ]
    return {"table": table_name, "schema": schema}


# Serve the chat UI itself (frontend/index.html) so phones on the same
# Wi-Fi (or the mobile app's WebView) can load it from this same backend,
# not just a desktop browser opening the file directly.
app.mount(
    "/",
    StaticFiles(
        directory=os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend"),
        html=True,
    ),
    name="frontend",
)


if __name__ == "__main__":
    import uvicorn

    print("\n" + "=" * 60)
    print("🚀 Retail Sales Analytics Chatbot - SQLite Version")
    print("=" * 60)
    print("\n📊 Backend running at: http://localhost:8000")
    print("💬 API docs at:        http://localhost:8000/docs")
    print(f"🗄️  Database:           {DB_PATH}")
    print("🖥️  Frontend:           open frontend/index.html in your browser")
    print("=" * 60 + "\n")

    # NOTE: reload=True requires passing the app as an import string ("app:app")
    # rather than the app object itself. For local dev with auto-reload, run:
    #   uvicorn app:app --reload
    # instead of `python app.py`.
    uvicorn.run(app, host="0.0.0.0", port=8000)

