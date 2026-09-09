"""
Query Agent — the first working end-to-end agent (Phase 4).

Supports exactly two question types, per the MVP plan:
  1. "which products are low on stock?"
  2. "top N selling products last month?"

Flow: question -> classify (keyword rules) -> SQL retrieval against canonical
tables -> pass retrieved rows to Gemini as context -> generate a natural-
language answer. The retrieved rows are always returned alongside the answer
as "source_records" — this is the explainability requirement, never optional.
"""
import os
import time

from dotenv import load_dotenv
from google import genai
from sqlalchemy import text

from app.db.database import engine

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

_client = None


def get_client():
    global _client
    if _client is None:
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


def classify_question(question: str) -> str:
    q = question.lower()
    if any(kw in q for kw in ["low stock", "low on stock", "running low", "reorder", "out of stock", "restock", "replenish"]):
        return "low_stock"
    if any(kw in q for kw in ["top sell", "best sell", "top product", "most sold", "selling"]):
        return "top_sellers"
    return "unknown"


def retrieve_low_stock(threshold=20, limit=10):
    with engine.connect() as conn:
        rows = conn.execute(
            text("""SELECT product_id, product_name, sku, category, stock_on_hand
                     FROM canonical_products
                     WHERE stock_on_hand IS NOT NULL AND stock_on_hand < :threshold
                     ORDER BY stock_on_hand ASC
                     LIMIT :limit"""),
            {"threshold": threshold, "limit": limit},
        ).mappings().all()
    return [dict(r) for r in rows]


def retrieve_top_sellers(limit=5):
    with engine.connect() as conn:
        rows = conn.execute(
            text("""SELECT p.product_id, p.product_name, p.sku,
                            SUM(t.quantity) AS total_units_sold,
                            SUM(t.total_amount) AS total_revenue
                     FROM canonical_transactions t
                     JOIN canonical_products p ON p.product_id = t.product_id
                     WHERE t.transaction_date >= (
                         SELECT MAX(transaction_date) FROM canonical_transactions
                     ) - INTERVAL '30 days'
                     GROUP BY p.product_id, p.product_name, p.sku
                     ORDER BY total_units_sold DESC
                     LIMIT :limit"""),
            {"limit": limit},
        ).mappings().all()
    return [dict(r) for r in rows]


def template_fallback_answer(question_type, records):
    """A clean, natural-sounding answer built without any LLM call — used when
    Gemini is rate-limited, so the demo never shows a raw data dump."""
    if question_type == "low_stock":
        items = "; ".join(
            f"{r['product_name']} (SKU {r['sku']}, {r['stock_on_hand']:.0f} units)" for r in records
        )
        return f"These products are currently low on stock: {items}."
    if question_type == "top_sellers":
        items = "; ".join(
            f"{r['product_name']} (SKU {r['sku']}, {r['total_units_sold']:.0f} units sold)" for r in records
        )
        return f"The top-selling products are: {items}."
    return "Here is the retrieved data for your question, formatted directly since a summary couldn't be generated right now."


def generate_answer(question, question_type, records):
    if not records:
        return "I couldn't find any matching records in the current data to answer that question."

    context_lines = []
    for r in records:
        context_lines.append(", ".join(f"{k}: {v}" for k, v in r.items()))
    context = "\n".join(context_lines)

    prompt = f"""You are an ERP data assistant. Answer the user's question using ONLY the
data provided below. Be concise (2-4 sentences), specific, and reference actual
product names/numbers from the data. Do not make up any information not present below.

Question: {question}

Data ({question_type}):
{context}

Answer:"""

    for attempt in range(2):
        try:
            client = get_client()
            response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
            return response.text.strip()
        except Exception as e:
            if "RESOURCE_EXHAUSTED" in str(e) and attempt == 0:
                time.sleep(15)  # brief backoff, then one retry — free tier quotas reset per minute
                continue
            return template_fallback_answer(question_type, records)


def answer_question(question: str):
    question_type = classify_question(question)

    if question_type == "low_stock":
        records = retrieve_low_stock()
    elif question_type == "top_sellers":
        records = retrieve_top_sellers()
    else:
        return {
            "question": question,
            "question_type": "unknown",
            "answer": "I can currently answer questions about low-stock products or top-selling products. "
                      "Try asking something like 'which products are low on stock?' or 'what are the top 5 selling products?'",
            "source_records": [],
        }

    answer = generate_answer(question, question_type, records)
    return {
        "question": question,
        "question_type": question_type,
        "answer": answer,
        "source_records": records,
    }
