"""
Generates a synthetic-but-realistic dataset directly inside Odoo via its API.

Design choices (kept deliberately small for the MVP timeline):
- ~30 products across 4 demand-pattern types: steady, growing, seasonal, declining
- ~10 customers (with 2 intentional duplicates), ~8 vendors
- ~100 transactions (sale orders) over the last 6 months, quantities driven by
  demand = base + trend*month + seasonality + noise  (numpy)
- Pattern type is encoded in each product's SKU prefix (STE/GRO/SEA/DEC) so the
  Forecasting Agent's output can later be sanity-checked against a known pattern.

Run from backend/ with the venv active:
    python scripts/generate_synthetic_data.py
"""
import random
from datetime import date, timedelta

import numpy as np
from faker import Faker

from app.connectors.odoo_connector import OdooConnector

fake = Faker()
random.seed(42)
np.random.seed(42)

NUM_PRODUCTS = 30
NUM_CUSTOMERS = 10
NUM_VENDORS = 8
NUM_DUPLICATE_CUSTOMERS = 2
TARGET_TRANSACTIONS = 100
MONTHS_BACK = 6

PATTERNS = ["steady", "growing", "seasonal", "declining"]
PATTERN_PREFIX = {"steady": "STE", "growing": "GRO", "seasonal": "SEA", "declining": "DEC"}

CATEGORIES = ["Beverages", "Snacks", "Household", "Personal Care", "Stationery"]


def demand_for_month(pattern, month_index, base=50):
    """month_index: 0..MONTHS_BACK-1 (0 = oldest month)"""
    noise = np.random.normal(0, 4)
    if pattern == "steady":
        return max(1, round(base + noise))
    if pattern == "growing":
        return max(1, round(base + 4 * month_index + noise))
    if pattern == "seasonal":
        return max(1, round(base + 15 * np.sin(2 * np.pi * month_index / 12) + noise))
    if pattern == "declining":
        return max(1, round(base - 4 * month_index + noise))
    return max(1, round(base + noise))


def create_products(odoo):
    products = []
    for i in range(NUM_PRODUCTS):
        pattern = PATTERNS[i % len(PATTERNS)]
        prefix = PATTERN_PREFIX[pattern]
        name = f"{fake.word().capitalize()} {random.choice(['Pack', 'Bottle', 'Box', 'Set'])}"
        sku = f"{prefix}-{i+1:03d}"
        price = round(random.uniform(150, 5000), 2)  # LKR-ish price range
        product_id = odoo.create("product.product", {
            "name": name,
            "default_code": sku,
            "list_price": price,
            "type": "consu",
            "is_storable": True,
        })
        products.append({"id": product_id, "sku": sku, "pattern": pattern, "name": name, "price": price})
        print(f"  product: {sku} ({pattern}) -> id={product_id}")
    return products


def create_customers(odoo):
    customers = []
    for i in range(NUM_CUSTOMERS):
        name = fake.company()
        partner_id = odoo.create("res.partner", {
            "name": name,
            "email": fake.company_email(),
            "phone": fake.phone_number(),
            "city": random.choice(["Colombo", "Kandy", "Galle", "Jaffna", "Nuwara Eliya"]),
            "customer_rank": 1,
        })
        customers.append({"id": partner_id, "name": name})
        print(f"  customer: {name} -> id={partner_id}")

    # deliberate duplicates: same name, slightly different email/phone, blank city
    for _ in range(NUM_DUPLICATE_CUSTOMERS):
        original = random.choice(customers)
        dup_id = odoo.create("res.partner", {
            "name": original["name"],
            "email": fake.company_email(),
            "phone": "",  # deliberately blank
            "customer_rank": 1,
        })
        print(f"  duplicate customer: {original['name']} -> id={dup_id}")
        customers.append({"id": dup_id, "name": original["name"]})

    return customers


def create_vendors(odoo):
    vendors = []
    for i in range(NUM_VENDORS):
        name = fake.company() + " Supplies"
        partner_id = odoo.create("res.partner", {
            "name": name,
            "email": fake.company_email(),
            "phone": fake.phone_number(),
            "city": random.choice(["Colombo", "Kandy", "Galle"]),
            "supplier_rank": 1,
        })
        vendors.append({"id": partner_id, "name": name})
        print(f"  vendor: {name} -> id={partner_id}")
    return vendors


def create_transactions(odoo, products, customers):
    today = date.today()
    # build all (product, month) combos, sample down to TARGET_TRANSACTIONS
    combos = [(p, m) for p in products for m in range(MONTHS_BACK)]
    random.shuffle(combos)
    combos = combos[:TARGET_TRANSACTIONS]

    count = 0
    for product, month_index in combos:
        qty = demand_for_month(product["pattern"], month_index)
        months_ago = MONTHS_BACK - month_index
        order_date = today - timedelta(days=months_ago * 30 + random.randint(0, 27))
        customer = random.choice(customers)

        order_id = odoo.create("sale.order", {
            "partner_id": customer["id"],
            "date_order": order_date.strftime("%Y-%m-%d %H:%M:%S"),
            "order_line": [(0, 0, {
                "product_id": product["id"],
                "product_uom_qty": qty,
                "price_unit": product["price"],
            })],
        })
        # confirm the order so it's a real "sale", not just a quote
        odoo.action("sale.order", "action_confirm", [order_id])
        count += 1
        if count % 20 == 0:
            print(f"  ...{count} transactions created")

    print(f"  total transactions created: {count}")


def main():
    print("Connecting to Odoo ...")
    odoo = OdooConnector()

    print(f"\nCreating {NUM_PRODUCTS} products across patterns {PATTERNS} ...")
    products = create_products(odoo)

    print(f"\nCreating {NUM_CUSTOMERS} customers (+{NUM_DUPLICATE_CUSTOMERS} duplicates) ...")
    customers = create_customers(odoo)

    print(f"\nCreating {NUM_VENDORS} vendors ...")
    create_vendors(odoo)

    print(f"\nCreating ~{TARGET_TRANSACTIONS} transactions over the last {MONTHS_BACK} months ...")
    create_transactions(odoo, products, customers)

    print("\nDone. Synthetic dataset is live in Odoo.")
    print("Next: run scripts/sync_to_postgres.py to pull it into raw staging tables.")


if __name__ == "__main__":
    main()
