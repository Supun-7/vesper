"""
Sets realistic stock-on-hand quantities for all products via Odoo's
stock.quant model (the actual source of truth for on-hand inventory —
product.qty_available is just a computed sum of quants).

Distribution: ~30% of products get a low stock level (0-15 units, to
genuinely trigger "low stock" queries), the rest get a healthy 20-200 units.

Run from backend/ with the venv active:
    python -m scripts.seed_stock_levels
"""
import random

from app.connectors.odoo_connector import OdooConnector

random.seed(3)


def find_internal_location(odoo):
    locations = odoo.search_read(
        "stock.location",
        domain=[["usage", "=", "internal"]],
        fields=["id", "complete_name"],
        limit=5,
    )
    if not locations:
        raise RuntimeError("No internal stock location found — is the Inventory module installed?")
    # Prefer one that looks like the main warehouse stock location
    for loc in locations:
        if "stock" in loc["complete_name"].lower():
            return loc["id"]
    return locations[0]["id"]


def set_stock(odoo, product_id, location_id, quantity):
    existing = odoo.search_read(
        "stock.quant",
        domain=[["product_id", "=", product_id], ["location_id", "=", location_id]],
        fields=["id"],
    )
    if existing:
        odoo.execute("stock.quant", "write", [existing[0]["id"]], {"quantity": quantity})
    else:
        odoo.create("stock.quant", {
            "product_id": product_id,
            "location_id": location_id,
            "quantity": quantity,
        })


def main():
    odoo = OdooConnector()
    location_id = find_internal_location(odoo)
    print(f"Using internal location id={location_id}")

    products = odoo.search_read("product.product", fields=["id", "default_code"])
    print(f"Setting stock levels for {len(products)} products ...")

    low_stock_count = 0
    for p in products:
        if random.random() < 0.3:
            qty = random.randint(0, 15)
            low_stock_count += 1
        else:
            qty = random.randint(20, 200)
        set_stock(odoo, p["id"], location_id, qty)
        print(f"  {p.get('default_code', p['id'])}: {qty} units")

    print(f"\nDone. {low_stock_count} products set to low-stock range (0-15), "
          f"{len(products) - low_stock_count} set to healthy range (20-200).")
    print("Next: re-run scripts/sync_to_postgres.py and scripts/apply_mappings.py "
          "to refresh canonical_products with the new stock levels.")


if __name__ == "__main__":
    main()
