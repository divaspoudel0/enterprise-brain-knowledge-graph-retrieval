#!/usr/bin/env python3
"""S6 — vector-only RAG baseline.

For every question in benchmark_v1.jsonl:
  1. embed the question (bge query prefix),
  2. top-k cosine retrieval over the committed vector index (TOP_K=5, common.py),
  3. inject the retrieved chunks into the shared answer template,
  4. generate the answer with Qwen2.5-7B-Instruct (greedy).

With --structured, uses the structured answer prompt (predicted_answer / explanation)
and records both fields plus the raw generation.

Stores a committed raw per-question trace (results_baseline_v1.json) — aggregates
are computed separately by systems/score_results.py (EVALUATION.md §2). Latency is
wall-clock per query on this hardware/session; the hybrid must run back-to-back in
the same session for comparability.

Usage:  uv run --with sentence-transformers --with torch --with transformers \
               python systems/baseline/run_baseline.py [--structured]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import (ANSWER_TEMPLATE, STRUCTURED_ANSWER_TEMPLATE, TOP_K, build_context,
                    generate_answer, generate_structured_answer, load_benchmark, load_llm,
                    retrieve, embed_query)

OUT = Path(__file__).resolve().parent / "results_baseline_v1.json"
OUT_STRUCTURED = Path(__file__).resolve().parent / "results_baseline_structured.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--structured", action="store_true",
                        help="use the structured predicted_answer/explanation prompt")
    args = parser.parse_args()

    questions = load_benchmark()
    llm = load_llm()

    print(f"answering {len(questions)} questions (k={TOP_K}, structured={args.structured}) ...", flush=True)
    results = []
    for i, q in enumerate(questions, 1):
        t0 = time.perf_counter()
        q_emb = embed_query(q["question"])
        t1 = time.perf_counter()
        chunks = retrieve(q_emb)
        t2 = time.perf_counter()
        template = STRUCTURED_ANSWER_TEMPLATE if args.structured else ANSWER_TEMPLATE
        prompt = template.format(context=build_context(chunks), question=q["question"])
        if args.structured:
            gen = generate_structured_answer(llm, prompt)
            answer = gen["predicted_answer"]
        else:
            gen = None
            answer = generate_answer(llm, prompt)
        t3 = time.perf_counter()
        row = {
            "qid": q["qid"], "question": q["question"], "hops": q["hops"],
            "template_id": q["template_id"], "pattern": q["pattern"],
            "ground_truth": q["answer"], "answer_type": q["answer_type"],
            "predicted_answer": answer,
            "retrieved_record_ids": [c["record_id"] for c in chunks],
            "retrieved_scores": [c["score"] for c in chunks],
            "retrieval_ms": round((t2 - t1) * 1000, 1),
            "generation_ms": round((t3 - t2) * 1000, 1),
            "embed_ms": round((t1 - t0) * 1000, 1),
        }
        if gen is not None:
            row["explanation"] = gen["explanation"]
            row["raw_generation"] = gen["raw"]
        results.append(row)
        if i % 50 == 0 or i == len(questions):
            print(f"  {i}/{len(questions)} done", flush=True)

    out_path = OUT_STRUCTURED if args.structured else OUT
    out_path.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    ok = sum(1 for r in results if r["predicted_answer"].strip() == r["ground_truth"].strip())
    total_ms = sum(r["generation_ms"] + r["retrieval_ms"] for r in results)
    print(f"exact-match {ok}/{len(results)} ({ok/len(results):.1%}); "
          f"avg per-q latency {total_ms/len(results)/1000:.2f}s")
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
