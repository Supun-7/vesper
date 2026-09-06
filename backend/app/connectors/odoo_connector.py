"""
Odoo connector: wraps XML-RPC calls behind simple fetch_* functions.
This is the ERP-specific adapter — the same interface pattern that would be
implemented differently for SAP (RFC/OData) or Oracle (REST) later, without
changing any agent logic downstream.
"""
import os
import xmlrpc.client
from dotenv import load_dotenv

load_dotenv()

ODOO_URL = os.getenv("ODOO_URL", "http://localhost:8069")
ODOO_DB = os.getenv("ODOO_DB", "believe_demo")
ODOO_USERNAME = os.getenv("ODOO_USERNAME", "admin")
ODOO_PASSWORD = os.getenv("ODOO_PASSWORD", "admin")


class OdooConnector:
    def __init__(self):
        self.common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
        self.models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")
        self.uid = self.common.authenticate(ODOO_DB, ODOO_USERNAME, ODOO_PASSWORD, {})
        if not self.uid:
            raise RuntimeError("Odoo authentication failed — check .env credentials")

    # ---- generic helpers ----
    def execute(self, model, method, *args, **kwargs):
        return self.models.execute_kw(
            ODOO_DB, self.uid, ODOO_PASSWORD, model, method, list(args), kwargs
        )

    def create(self, model, values):
        return self.execute(model, "create", values)

    def search_read(self, model, domain=None, fields=None, limit=0):
        domain = domain or []
        kwargs = {"fields": fields} if fields else {}
        if limit:
            kwargs["limit"] = limit
        return self.execute(model, "search_read", domain, **kwargs)

    def action(self, model, method, ids):
        return self.execute(model, method, ids)

    # ---- entity-specific fetches used by the sync pipeline ----
    def fetch_products(self):
        return self.search_read(
            "product.product",
            fields=["id", "name", "default_code", "list_price", "qty_available", "categ_id"],
        )

    def fetch_customers(self):
        return self.search_read(
            "res.partner",
            domain=[["customer_rank", ">", 0]],
            fields=["id", "name", "email", "phone", "city"],
        )

    def fetch_vendors(self):
        return self.search_read(
            "res.partner",
            domain=[["supplier_rank", ">", 0]],
            fields=["id", "name", "email", "phone", "city"],
        )

    def fetch_sale_orders(self):
        orders = self.search_read(
            "sale.order",
            fields=["id", "name", "partner_id", "date_order", "amount_total", "state"],
        )
        # pull order lines separately and attach, since that's where product/qty live
        for order in orders:
            lines = self.search_read(
                "sale.order.line",
                domain=[["order_id", "=", order["id"]]],
                fields=["product_id", "product_uom_qty", "price_unit"],
            )
            order["lines"] = lines
        return orders
