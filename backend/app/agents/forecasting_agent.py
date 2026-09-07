"""
Forecasting Agent (Phase 5) — independent of the Query Agent.

Deliberately simple: moving average over monthly sales history, no deep
learning, no unexplainable black-box output. A product is identified by
matching its SKU or name mentioned in the question text.
"""
from sqlalchemy import text

from app.db.database import engine


def load_products():
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT product_id, product_name, sku FROM canonical_products")
        ).mappings().all()
    return [dict(r) for r in rows]


def find_product_by_mention(question: str):
    """Very simple matcher: does this product's SKU or name appear in the question text?"""
    q_lower = question.lower()
    products = load_products()

    # prefer SKU matches (more precise) over name matches
    for p in products:
        if p.get("sku") and p["sku"].lower() in q_lower:
            return p
    for p in products:
        if p.get("product_name") and p["product_name"].lower() in q_lower:
            return p
    return None


def get_monthly_series(product_id):
    with engine.connect() as conn:
        rows = conn.execute(
            text("""SELECT date_trunc('month', transaction_date) AS month,
                            SUM(quantity) AS total_quantity
                     FROM canonical_transactions
                     WHERE product_id = :pid
                     GROUP BY month
                     ORDER BY month"""),
            {"pid": product_id},
        ).mappings().all()
    return [{"month": str(r["month"])[:7], "total_quantity": float(r["total_quantity"])} for r in rows]


def moving_average_forecast(monthly_series, window=3):
    """Average of the last `window` months (or fewer if not enough history)."""
    if not monthly_series:
        return None
    recent = monthly_series[-window:]
    values = [m["total_quantity"] for m in recent]
    return sum(values) / len(values), recent


def forecast_question(question: str):
    product = find_product_by_mention(question)
    if not product:
        return {
            "question": question,
            "agent": "forecasting",
            "answer": "I couldn't identify which product you mean — please mention a product name or SKU "
                      "(e.g. 'forecast demand for SEA-027 next month').",
            "source_records": [],
        }

    monthly_series = get_monthly_series(product["product_id"])
    if not monthly_series:
        return {
            "question": question,
            "agent": "forecasting",
            "answer": f"No transaction history found for {product['product_name']} ({product['sku']}), "
                      f"so a forecast can't be generated.",
            "source_records": [],
        }

    forecast_value, months_used = moving_average_forecast(monthly_series)

    answer = (
        f"Based on the last {len(months_used)} month(s) of sales data for "
        f"{product['product_name']} ({product['sku']}), the moving-average forecast for next month "
        f"is approximately {forecast_value:.0f} units."
    )

    return {
        "question": question,
        "agent": "forecasting",
        "product": product,
        "forecast_quantity": round(forecast_value, 1),
        "method": "moving_average",
        "answer": answer,
        "source_records": months_used,
    }
