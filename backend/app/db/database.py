import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

APP_DB_URL = os.getenv("APP_DB_URL", "postgresql+psycopg2://believe:believe@localhost:5434/believe")

engine = create_engine(APP_DB_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


SCHEMA_SQL = """
-- RAW staging tables (loosely mirror Odoo)
CREATE TABLE IF NOT EXISTS raw_products (
    id SERIAL PRIMARY KEY,
    odoo_id INTEGER,
    raw_json JSONB,
    synced_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raw_customers (
    id SERIAL PRIMARY KEY,
    odoo_id INTEGER,
    raw_json JSONB,
    synced_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raw_vendors (
    id SERIAL PRIMARY KEY,
    odoo_id INTEGER,
    raw_json JSONB,
    synced_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raw_sale_orders (
    id SERIAL PRIMARY KEY,
    odoo_id INTEGER,
    raw_json JSONB,
    synced_at TIMESTAMP DEFAULT now()
);

-- CANONICAL / normalized tables
CREATE TABLE IF NOT EXISTS canonical_products (
    product_id INTEGER PRIMARY KEY,
    product_name TEXT,
    sku TEXT,
    category TEXT,
    unit_price NUMERIC,
    stock_on_hand NUMERIC,
    reorder_level NUMERIC
);

CREATE TABLE IF NOT EXISTS canonical_customers (
    customer_id INTEGER PRIMARY KEY,
    customer_name TEXT,
    email TEXT,
    phone TEXT,
    city TEXT
);

CREATE TABLE IF NOT EXISTS canonical_transactions (
    transaction_id INTEGER PRIMARY KEY,
    product_id INTEGER,
    customer_id INTEGER,
    quantity NUMERIC,
    unit_price NUMERIC,
    total_amount NUMERIC,
    transaction_date DATE
);

-- Semantic mapping agent output
CREATE TABLE IF NOT EXISTS field_mappings (
    id SERIAL PRIMARY KEY,
    entity TEXT,
    source_field TEXT,
    canonical_field TEXT,
    confidence NUMERIC,
    method TEXT,
    created_at TIMESTAMP DEFAULT now()
);

-- Sync run logging
CREATE TABLE IF NOT EXISTS sync_log (
    id SERIAL PRIMARY KEY,
    entity TEXT,
    row_count INTEGER,
    status TEXT,
    error TEXT,
    run_at TIMESTAMP DEFAULT now()
);
"""


def init_schema():
    with engine.begin() as conn:
        conn.execute(text(SCHEMA_SQL))
    print("Schema ensured.")


if __name__ == "__main__":
    init_schema()