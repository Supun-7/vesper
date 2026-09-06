"""
Semantic Mapping Agent.

Two-tier approach:
1. Rule-based: keyword substrings that obviously map to a canonical concept
   (fast, free, no LLM call needed — handles the "obvious" renamed fields).
2. LLM-assisted: for anything the rules don't confidently resolve, ask Gemini
   to suggest the canonical field + a confidence score, given the field name
   and a few real sample values.

This only needs to run ONCE PER UNIQUE FIELD NAME, not per row — a raw table
with 1,000 rows might only have 6 distinct field names to resolve.
"""
import json
import os

from dotenv import load_dotenv
from google import genai

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

_client = None


def get_client():
    global _client
    if _client is None:
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


# Canonical schema — the clean target fields per entity
CANONICAL_FIELDS = {
    "product": ["product_name", "sku", "category", "unit_price", "stock_on_hand"],
    "customer": ["customer_name", "email", "phone", "city"],
    "vendor": ["vendor_name", "email", "phone", "city"],
}

# Rule-based dictionary: keyword substring -> canonical field, per entity.
# These catch the "obvious" legacy abbreviations without needing an LLM call.
RULE_KEYWORDS = {
    "product": {"sku": "sku", "nm": "product_name", "cat": "category"},
    "customer": {"nm": "customer_name", "eml": "email", "tel": "phone", "city": "city"},
    "vendor": {"nm": "vendor_name", "eml": "email", "tel": "phone", "city": "city"},
}


def apply_rule(entity, field_name):
    """Try to resolve a field name via keyword rules. Returns canonical field or None."""
    keywords = RULE_KEYWORDS.get(entity, {})
    tokens = field_name.lower().split("_")
    for token in tokens:
        if token in keywords:
            return keywords[token]
    return None


def llm_suggest_mapping(entity, field_name, sample_values):
    """Ask Gemini to suggest the canonical field for an unmatched raw field."""
    options = CANONICAL_FIELDS.get(entity, [])
    samples = [v for v in sample_values if v is not None][:5]

    prompt = f"""You are a data mapping assistant for an ERP integration system.
Given a raw/legacy field name and sample values from a {entity} record, choose the
best matching canonical field from the allowed list, or "none" if nothing fits.

Raw field name: {field_name}
Sample values: {samples}
Allowed canonical fields: {options}

Respond with ONLY a JSON object, no markdown, no explanation:
{{"canonical_field": "<one of the allowed fields or 'none'>", "confidence": <float 0.0-1.0>}}
"""

    try:
        client = get_client()
        response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
        text = response.text.strip()
        # strip markdown fences if the model adds them anyway
        text = text.replace("```json", "").replace("```", "").strip()
        result = json.loads(text)
        return result.get("canonical_field"), float(result.get("confidence", 0))
    except Exception as e:
        print(f"    LLM mapping failed for '{field_name}': {e}")
        return None, 0.0


def resolve_field(entity, field_name, sample_values):
    """
    Returns (canonical_field, confidence, method) for a single raw field name.
    Tries rules first (fast path), falls back to LLM if no rule matches.
    """
    rule_result = apply_rule(entity, field_name)
    if rule_result:
        return rule_result, 1.0, "rule-based"

    llm_field, llm_confidence = llm_suggest_mapping(entity, field_name, sample_values)
    if llm_field and llm_field != "none" and llm_field in CANONICAL_FIELDS.get(entity, []):
        return llm_field, llm_confidence, "llm-suggested"

    return None, 0.0, "unmatched"
