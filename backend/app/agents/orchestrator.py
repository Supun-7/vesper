"""
Orchestrator (Phase 6) — single entry point that routes each question to the
correct agent. Keyword-based by design (not LLM-classified) for speed and
defensibility: it's easy to explain exactly why a question was routed a
certain way, with zero ambiguity and zero extra API cost.
"""
from app.agents.query_agent import answer_question
from app.agents.forecasting_agent import forecast_question

FORECAST_KEYWORDS = [
    "predict", "forecast", "next month", "next week", "expected demand",
    "will sell", "projection", "projected",
]


def classify_intent(question: str) -> str:
    q = question.lower()
    if any(kw in q for kw in FORECAST_KEYWORDS):
        return "forecasting"
    return "query"


def route_question(question: str):
    intent = classify_intent(question)

    if intent == "forecasting":
        result = forecast_question(question)
    else:
        result = answer_question(question)

    result["routed_to"] = intent
    return result
