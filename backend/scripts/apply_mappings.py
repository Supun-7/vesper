"""
Runs the Semantic Mapping Agent end-to-end:
1. For each raw table (products, customers, vendors), find the distinct set
   of field names present in raw_json.
2. Resolve each field name to a canonical field exactly once (rule-based
   first, Gemini fallback second) — not once per row.
3. Store every resolution in field_mappings (source field, canonical field,
   confidence, method).
4. Apply the resolved mapping to transform all raw rows into the canonical_*
   tables.
5. Transactions are handled directly (their fields aren't deliberately
   messy — see sync_to_postgres.py) rather than through the mapping agent.

Run from backend/ with the venv active:
    python -m scripts.apply_mappings
"""
import json

from sqlalchemy import text

from app.agents.mapping_agent import resolve_field, CANONICAL_FIELDS
from app.db.database import engine


def load_raw(conn, table_name):
    rows = conn.execute(text(f"SELECT odoo_id, raw_json FROM {table_name}")).fetchall()
    return [(r[0], r[1]) for r in rows]


def build_field_mapping(conn, entity, table_name):
    """Resolve every distinct field name found in this raw table, log to field_mappings."""
    rows = load_raw(conn, table_name)

    # collect sample values per field, across all rows, for the LLM prompt
    field_samples = {}
    for _, raw_json in rows:
        record = raw_json if isinstance(raw_json, dict) else json.loads(raw_json)
        for key, value in record.items():
            if key == "id":
                continue
            field_samples.setdefault(key, []).append(value)

    mapping = {}  # source_field -> canonical_field
    print(f"  resolving {len(field_samples)} distinct fields for '{entity}' ...")
    for field_name, values in field_samples.items():
        canonical_field, confidence, method = resolve_field(entity, field_name, values)
        mapping[field_name] = canonical_field
        conn.execute(
            text("""INSERT INTO field_mappings (entity, source_field, canonical_field, confidence, method)
                     VALUES (:e, :s, :c, :conf, :m)"""),
            {"e": entity, "s": field_name, "c": canonical_field, "conf": confidence, "m": method},
        )
        status = canonical_field if canonical_field else "UNMATCHED"
        print(f"    {field_name:20s} -> {status:20s} (confidence={confidence:.2f}, method={method})")

    return mapping, rows


def transform_products(conn):
    mapping, rows = build_field_mapping(conn, "product", "raw_products")
    inserted = 0
    for odoo_id, raw_json in rows:
        record = raw_json if isinstance(raw_json, dict) else json.loads(raw_json)
        canonical = {mapping.get(k): v for k, v in record.items() if k != "id" and mapping.get(k)}
        conn.execute(
            text("""INSERT INTO canonical_products (product_id, product_name, sku, category, unit_price, stock_on_hand)
                     VALUES (:pid, :name, :sku, :cat, :price, :stock)
                     ON CONFLICT (product_id) DO UPDATE SET
                        product_name = EXCLUDED.product_name,
                        sku = EXCLUDED.sku,
                        category = EXCLUDED.category,
                        unit_price = EXCLUDED.unit_price,
                        stock_on_hand = EXCLUDED.stock_on_hand"""),
            {
                "pid": odoo_id,
                "name": canonical.get("product_name"),
                "sku": canonical.get("sku"),
                "cat": canonical.get("category"),
                "price": canonical.get("unit_price"),
                "stock": canonical.get("stock_on_hand"),
            },
        )
        inserted += 1
    print(f"  canonical_products: upserted {inserted} rows")


def transform_customers(conn):
    mapping, rows = build_field_mapping(conn, "customer", "raw_customers")
    inserted = 0
    for odoo_id, raw_json in rows:
        record = raw_json if isinstance(raw_json, dict) else json.loads(raw_json)
        canonical = {mapping.get(k): v for k, v in record.items() if k != "id" and mapping.get(k)}
        conn.execute(
            text("""INSERT INTO canonical_customers (customer_id, customer_name, email, phone, city)
                     VALUES (:cid, :name, :email, :phone, :city)
                     ON CONFLICT (customer_id) DO UPDATE SET
                        customer_name = EXCLUDED.customer_name,
                        email = EXCLUDED.email,
                        phone = EXCLUDED.phone,
                        city = EXCLUDED.city"""),
            {
                "cid": odoo_id,
                "name": canonical.get("customer_name"),
                "email": canonical.get("email"),
                "phone": canonical.get("phone"),
                "city": canonical.get("city"),
            },
        )
        inserted += 1
    print(f"  canonical_customers: upserted {inserted} rows")


def transform_vendors(conn):
    # vendors aren't queried by the agents in this MVP, but we still run them
    # through the mapping agent for the field_mappings evidence/checkpoint.
    mapping, rows = build_field_mapping(conn, "vendor", "raw_vendors")
    print(f"  vendors: mapping resolved for {len(rows)} rows (not loaded into a dedicated canonical table in this MVP)")


def transform_transactions(conn):
    # Transaction fields are NOT deliberately messy (see sync_to_postgres.py),
    # so we map them directly rather than through the LLM-assisted agent.
    rows = conn.execute(text("SELECT odoo_id, raw_json FROM raw_sale_orders")).fetchall()
    inserted = 0
    for i, (odoo_id, raw_json) in enumerate(rows):
        record = raw_json if isinstance(raw_json, dict) else json.loads(raw_json)
        if record.get("state") != "sale":
            continue  # skip anything not confirmed
        conn.execute(
            text("""INSERT INTO canonical_transactions
                     (transaction_id, product_id, customer_id, quantity, unit_price, total_amount, transaction_date)
                     VALUES (:tid, :pid, :cid, :qty, :price, :total, :date)
                     ON CONFLICT (transaction_id) DO UPDATE SET
                        product_id = EXCLUDED.product_id,
                        customer_id = EXCLUDED.customer_id,
                        quantity = EXCLUDED.quantity,
                        unit_price = EXCLUDED.unit_price,
                        total_amount = EXCLUDED.total_amount,
                        transaction_date = EXCLUDED.transaction_date"""),
            {
                "tid": i + 1,  # synthetic line-level transaction id
                "pid": record.get("product_id"),
                "cid": record.get("partner_id"),
                "qty": record.get("product_uom_qty"),
                "price": record.get("price_unit"),
                "total": (record.get("product_uom_qty") or 0) * (record.get("price_unit") or 0),
                "date": (record.get("date_order") or "").split(" ")[0] or None,
            },
        )
        inserted += 1
    print(f"  canonical_transactions: upserted {inserted} rows")


def main():
    with engine.begin() as conn:
        print("Clearing previous mapping + canonical results (idempotent re-run) ...")
        conn.execute(text("TRUNCATE TABLE field_mappings RESTART IDENTITY"))
        conn.execute(text("TRUNCATE TABLE canonical_products, canonical_customers, canonical_transactions"))

        print("\nMapping + transforming products ...")
        transform_products(conn)

        print("\nMapping + transforming customers ...")
        transform_customers(conn)

        print("\nMapping vendors (evidence only) ...")
        transform_vendors(conn)

        print("\nTransforming transactions (direct mapping, not LLM-assisted) ...")
        transform_transactions(conn)

    print("\nDone. Check the field_mappings table for the full rule-vs-LLM breakdown.")


if __name__ == "__main__":
    main()
