"""
Week 1 checkpoint: confirm we can hit Odoo's API and pull data.
Run from the backend/ folder with the venv active:
    python scripts/hello_world_odoo.py
"""
import os
import xmlrpc.client
from dotenv import load_dotenv

load_dotenv()

ODOO_URL = os.getenv("ODOO_URL", "http://localhost:8069")
ODOO_DB = os.getenv("ODOO_DB", "believe_demo")
ODOO_USERNAME = os.getenv("ODOO_USERNAME", "admin")
ODOO_PASSWORD = os.getenv("ODOO_PASSWORD", "admin")


def main():
    print(f"Connecting to Odoo at {ODOO_URL}, db={ODOO_DB} ...")

    common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
    version_info = common.version()
    print("Odoo server version info:", version_info)

    uid = common.authenticate(ODOO_DB, ODOO_USERNAME, ODOO_PASSWORD, {})
    if not uid:
        print("AUTH FAILED. Check ODOO_DB / ODOO_USERNAME / ODOO_PASSWORD in .env")
        return
    print(f"Authenticated. uid={uid}")

    models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")

    # Count products
    product_count = models.execute_kw(
        ODOO_DB, uid, ODOO_PASSWORD,
        "product.product", "search_count", [[]]
    )
    print(f"product.product count: {product_count}")

    # Pull up to 3 products, just id + name, as the checkpoint
    product_ids = models.execute_kw(
        ODOO_DB, uid, ODOO_PASSWORD,
        "product.product", "search", [[]], {"limit": 3}
    )
    products = models.execute_kw(
        ODOO_DB, uid, ODOO_PASSWORD,
        "product.product", "read", [product_ids], {"fields": ["id", "name", "list_price"]}
    )
    print("Sample products:", products)

    print("\nCHECKPOINT PASSED: Odoo API is reachable from Python." if uid else "CHECKPOINT FAILED")


if __name__ == "__main__":
    main()
