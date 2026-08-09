#!/usr/bin/env python3
"""S6 — vector-only RAG baseline.

For every question in benchmark_v1.jsonl:
  1. embed the question (bge query prefix),
  2. top-k cosine retrieval over the committed vector index (TOP_K=5, common.py),
  3. inject the retrieved chunks into the shared answer template,
  4. generate the answer with Qwen2.5-7B-Instruct (greedy).

Stores a committed raw per-question trace (results_baseline_v1.json) — aggregates
are computed separately by systems/score_results.py (EVALUATION.md §2). Latency is
wall-clock per query on this hardware/session; the hybrid must run back-to-back in
the same session for comparability.

Usage:  uv run --with sentence-transformers --with torch --with transformers \
               python systems/baseline/run_baseline.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import (ANSWER_TEMPLATE, TOP_K, build_context, generate_answer,
                    load_benchmark, load_llm, retrieve, embed_query)

OUT = Path(__file__).resolve().parent / "results_baseline_v1.json"


def main() -> int:
    questions = load_benchmark()
    llm = load_llm()

    print(f"answering {len(questions)} questions (k={TOP_K}) ...", flush=True)
    results = []
    for i, q in enumerate(questions, 1):
        t0 = time.perf_counter()
        q_emb = embed_query(q["question"])
        t1 = time.perf_counter()
        chunks = retrieve(q_emb)
        t2 = time.perf_counter()
        prompt = ANSWER_TEMPLATE.format(context=build_context(chunks), question=q["question"])
        answer = generate_answer(llm, prompt)
        t3 = time.perf_counter()
        results.append({
            "qid": q["qid"], "question": q["question"], "hops": q["hops"],
            "template_id": q["template_id"], "pattern": q["pattern"],
            "ground_truth": q["answer"], "answer_type": q["answer_type"],
            "predicted_answer": answer,
            "retrieved_record_ids": [c["record_id"] for c in chunks],
            "retrieved_scores": [c["score"] for c in chunks],
            "retrieval_ms": round((t2 - t1) * 1000, 1),
            "generation_ms": round((t3 - t2) * 1000, 1),
            "embed_ms": round((t1 - t0) * 1000, 1),
        })
        if i % 50 == 0 or i == len(questions):
            print(f"  {i}/{len(questions)} done", flush=True)

    OUT.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    ok = sum(1 for r in results if r["predicted_answer"].strip() == r["ground_truth"].strip())
    total_ms = sum(r["generation_ms"] + r["retrieval_ms"] for r in results)
    print(f"exact-match {ok}/{len(results)} ({ok/len(results):.1%}); "
          f"avg per-q latency {total_ms/len(results)/1000:.2f}s")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
