"""
One-time fix: our synthetic products were created without inventory tracking
enabled, so Odoo refuses to create stock.quant records for them ("Quants
cannot be created for consumables or services"). This sets is_storable=True
(Odoo 17's field for enabling inventory tracking on a 'consu' type product)
on all of them.

Run from backend/ with the venv active:
    python -m scripts.fix_product_storable
"""
from app.connectors.odoo_connector import OdooConnector


def main():
    odoo = OdooConnector()
    product_ids = odoo.execute("product.product", "search", [])
    print(f"Found {len(product_ids)} products. Setting is_storable=True ...")

    try:
        odoo.execute("product.product", "write", product_ids, {"is_storable": True})
        print("Done via is_storable field.")
    except Exception as e:
        print(f"is_storable approach failed ({e}), trying type='product' instead ...")
        odoo.execute("product.product", "write", product_ids, {"type": "product"})
        print("Done via type field.")


if __name__ == "__main__":
    main()
