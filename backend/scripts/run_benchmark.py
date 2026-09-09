"""
Phase 8 — Benchmark testing.

Runs a fixed set of benchmark questions through the orchestrator directly
(no HTTP needed — imports route_question straight from the app), records
response time for each, and prints everything for manual correctness review.

Correctness itself can't be fully automated here since answers are natural
language — this script's job is to produce the raw evidence (question,
answer, source records, timing) that you then mark correct/incorrect against,
by eye, to get your final benchmark numbers for the report/demo.

Run from backend/ with the venv active:
    python -m scripts.run_benchmark
"""
import time
import json

from app.agents.orchestrator import route_question

BENCHMARK_QUESTIONS = [
    "which products are low on stock?",
    "what are the top 5 selling products?",
    "what are the best selling products this month?",
    "forecast demand for SEA-027 next month",
    "predict next month's demand for GRO-002",
    "which items need restocking?",
    "what is the top selling product?",
    "forecast demand for STE-001 next month",
]


def main():
    results = []
    print(f"Running {len(BENCHMARK_QUESTIONS)} benchmark questions ...\n")

    for i, question in enumerate(BENCHMARK_QUESTIONS, 1):
        start = time.time()
        response = route_question(question)
        elapsed = round(time.time() - start, 2)

        print(f"[{i}] Q: {question}")
        print(f"    routed_to: {response.get('routed_to')}")
        print(f"    answer: {response.get('answer')}")
        print(f"    source_records: {len(response.get('source_records', []))} returned")
        print(f"    response_time: {elapsed}s\n")

        results.append({
            "question": question,
            "routed_to": response.get("routed_to"),
            "answer": response.get("answer"),
            "source_record_count": len(response.get("source_records", [])),
            "response_time_seconds": elapsed,
        })

    avg_time = round(sum(r["response_time_seconds"] for r in results) / len(results), 2)
    print(f"--- Summary ---")
    print(f"Total questions: {len(results)}")
    print(f"Average response time: {avg_time}s")
    print(f"\nReview each answer above and mark correct/incorrect by hand for your final benchmark number.")

    with open("benchmark_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nFull results saved to benchmark_results.json")


if __name__ == "__main__":
    main()
