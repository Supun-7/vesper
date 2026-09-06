"""
Wipes all synthetic data previously created by generate_synthetic_data.py,
so you can regenerate exactly once and get clean, unique SKUs.

Identifies script-created records by:
- products: default_code matching STE-/GRO-/SEA-/DEC- prefixes
- sale orders: any order referencing one of those products (deleted first,
  since Odoo won't let you delete a product that's used on a confirmed order)
- customers/vendors: all partners with customer_rank > 0 or supplier_rank > 0
  (safe for a fresh demo company with no other real contacts)

Run from backend/ with the venv active:
    python -m scripts.cleanup_synthetic_data
"""
from app.connectors.odoo_connector import OdooConnector


def main():
    odoo = OdooConnector()

    print("Finding script-generated products (SKU prefix STE/GRO/SEA/DEC) ...")
    product_ids = odoo.execute(
        "product.product", "search",
        [["default_code", "like", "%-0%"]],  # matches XXX-001 style codes broadly
    )
    # Narrow to our actual prefixes only, to be safe
    products = odoo.search_read("product.product", domain=[["id", "in", product_ids]], fields=["id", "default_code"])
    target_product_ids = [
        p["id"] for p in products
        if p.get("default_code") and p["default_code"][:3] in ("STE", "GRO", "SEA", "DEC")
    ]
    print(f"  found {len(target_product_ids)} products to remove")

    if target_product_ids:
        print("Finding sale orders referencing these products ...")
        line_order_ids = odoo.execute(
            "sale.order.line", "search",
            [["product_id", "in", target_product_ids]],
        )
        lines = odoo.search_read(
            "sale.order.line", domain=[["id", "in", line_order_ids]], fields=["order_id"]
        )
        order_ids = list({l["order_id"][0] for l in lines if l.get("order_id")})
        print(f"  found {len(order_ids)} sale orders to remove")

        if order_ids:
            print("Cancelling and deleting sale orders ...")
            try:
                odoo.action("sale.order", "action_cancel", order_ids)
            except Exception:
                pass  # some may already be cancellable-only in certain states
            odoo.execute("sale.order", "unlink", order_ids)

        print("Deleting products ...")
        odoo.execute("product.product", "unlink", target_product_ids)

    print("Deleting seeded customers and vendors (customer_rank>0 or supplier_rank>0) ...")
    partner_ids = odoo.execute(
        "res.partner", "search",
        ["|", ["customer_rank", ">", 0], ["supplier_rank", ">", 0]],
    )
    print(f"  found {len(partner_ids)} partners to remove")
    if partner_ids:
        odoo.execute("res.partner", "unlink", partner_ids)

    print("\nCleanup done. Odoo should now have zero script-generated records.")
    print("Run: python -m scripts.generate_synthetic_data")


if __name__ == "__main__":
    main()