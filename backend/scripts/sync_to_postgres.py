"""
Pulls data from Odoo via the connector and writes it into raw staging tables
in Postgres. Deliberately renames fields to simulate legacy/inconsistent naming
(the kind of mess a real 10-year-old ERP export would have) and blanks a few
fields at random — this raw messiness is exactly what Phase 3's Semantic
Mapping Agent is built to clean up.

Run from backend/ with the venv active:
    python scripts/sync_to_postgres.py
"""
import json
import random

from sqlalchemy import text

from app.connectors.odoo_connector import OdooConnector
from app.db.database import engine

random.seed(7)

# canonical_field -> legacy-style field name, applied when writing raw_json
PRODUCT_FIELD_MAP = {
    "name": "prod_nm",
    "default_code": "sku_cd",
    "list_price": "unit_cost_hist",
    "qty_available": "stk_qty",
    "categ_id": "cat_ref",
}
CUSTOMER_FIELD_MAP = {
    "name": "cust_full_nm",
    "email": "eml_addr",
    "phone": "tel_no",
    "city": "city_nm",
}
VENDOR_FIELD_MAP = {
    "name": "vendor_nm",
    "email": "contact_eml",
    "phone": "contact_tel",
    "city": "city_nm",
}

BLANK_PROBABILITY = 0.08  # chance any given field gets blanked out during sync

# these fields are how agents look products/customers up by name/SKU later —
# blanking them would make a record silently unreachable, which is a data
# quality problem worth demonstrating separately, not something we want
# happening at random during a live demo.
PROTECTED_FIELDS = {"sku_cd", "prod_nm", "cust_full_nm", "vendor_nm"}


def rename_and_mess(record, field_map):
    """Apply legacy field renaming and randomly blank a few fields."""
    messy = {}
    for key, value in record.items():
        new_key = field_map.get(key, key)
        if isinstance(value, list) and len(value) == 2:
            # Odoo many2one fields come back as [id, "display name"] — flatten
            value = value[1]
        if random.random() < BLANK_PROBABILITY and new_key != "id" and new_key not in PROTECTED_FIELDS:
            value = None
        messy[new_key] = value
    return messy


def log_sync(conn, entity, row_count, status, error=None):
    conn.execute(
        text("INSERT INTO sync_log (entity, row_count, status, error) VALUES (:e, :c, :s, :err)"),
        {"e": entity, "c": row_count, "s": status, "err": error},
    )


def synthetic_stock_for_product(product_id):
    """Deterministic pseudo-random stock level per product, so re-running sync
    gives consistent (but varied) numbers without depending on Odoo's real
    stock engine — reservations/moves/storable-type rules make that genuinely
    heavy machinery to fight for a demo dataset."""
    rng = random.Random(product_id * 7919)  # fixed seed per product, reproducible
    if rng.random() < 0.3:
        return rng.randint(0, 15)  # deliberately low, to trigger low-stock queries
    return rng.randint(20, 200)


def sync_entity(conn, odoo_fetch_fn, field_map, table_name, entity_name):
    try:
        records = odoo_fetch_fn()
        for record in records:
            if entity_name == "products":
                record["qty_available"] = synthetic_stock_for_product(record["id"])
            messy = rename_and_mess(record, field_map)
            conn.execute(
                text(f"INSERT INTO {table_name} (odoo_id, raw_json) VALUES (:oid, :raw)"),
                {"oid": record["id"], "raw": json.dumps(messy)},
            )
        log_sync(conn, entity_name, len(records), "success")
        print(f"  {entity_name}: synced {len(records)} rows")
        return len(records)
    except Exception as e:
        log_sync(conn, entity_name, 0, "error", str(e))
        print(f"  {entity_name}: FAILED — {e}")
        return 0


def sync_transactions(conn, odoo):
    try:
        orders = odoo.fetch_sale_orders()
        count = 0
        for order in orders:
            partner_id = order["partner_id"][0] if isinstance(order["partner_id"], list) else order["partner_id"]
            for line in order.get("lines", []):
                product_id = line["product_id"][0] if isinstance(line["product_id"], list) else line["product_id"]
                record = {
                    "order_id": order["id"],
                    "order_name": order["name"],
                    "partner_id": partner_id,
                    "date_order": order["date_order"],
                    "product_id": product_id,
                    "product_uom_qty": line["product_uom_qty"],
                    "price_unit": line["price_unit"],
                    "state": order["state"],
                }
                conn.execute(
                    text("INSERT INTO raw_sale_orders (odoo_id, raw_json) VALUES (:oid, :raw)"),
                    {"oid": order["id"], "raw": json.dumps(record)},
                )
                count += 1
        log_sync(conn, "sale_orders", count, "success")
        print(f"  sale_orders: synced {count} line-level rows from {len(orders)} orders")
        return count
    except Exception as e:
        log_sync(conn, "sale_orders", 0, "error", str(e))
        print(f"  sale_orders: FAILED — {e}")
        return 0


def main():
    print("Connecting to Odoo ...")
    odoo = OdooConnector()

    with engine.begin() as conn:
        print("\nClearing previous raw staging data (idempotent re-run) ...")
        for t in ["raw_products", "raw_customers", "raw_vendors", "raw_sale_orders"]:
            conn.execute(text(f"TRUNCATE TABLE {t} RESTART IDENTITY"))

        print("\nSyncing products ...")
        sync_entity(conn, odoo.fetch_products, PRODUCT_FIELD_MAP, "raw_products", "products")

        print("Syncing customers ...")
        sync_entity(conn, odoo.fetch_customers, CUSTOMER_FIELD_MAP, "raw_customers", "customers")

        print("Syncing vendors ...")
        sync_entity(conn, odoo.fetch_vendors, VENDOR_FIELD_MAP, "raw_vendors", "vendors")

        print("Syncing transactions (sale order lines) ...")
        sync_transactions(conn, odoo)

    print("\nDone. Raw staging tables populated with deliberately messy field names.")
    print("Spot-check a few rows against Odoo's UI, then move to Phase 3 (Semantic Mapping Agent).")


if __name__ == "__main__":
    main()
