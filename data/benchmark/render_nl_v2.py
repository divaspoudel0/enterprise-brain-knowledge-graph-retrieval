#!/usr/bin/env python3
"""Phase D (D1) — natural-language rendering of benchmark_v2 (V2_PLAN.md §6).

The v1/v2 benchmark questions embed exact IDs (c_0001, o_00001, p_0001 ...),
which is why v1's regex linker scores recall@1 = 100% — a measurement artefact,
not real-world utility. For the honest linker evaluation we render a parallel
natural-language question set `nl_v2.jsonl` in which entities that have a natural
surface form (product names, customer names, regions, categories) are mentioned
by that form instead of by ID, and record the ground-truth mention -> entity map
(`linked_entities`) plus which mentions a regex ID extractor could NOT have
found (`mentions_only`).

Orders/payments/complaints keep their IDs: in the real world you quote an order
or complaint reference number, so those references are realistic as-is.

Each nl record links back to its benchmark_v2 question via `qid` and carries
`split` so the learned linker trains on train / tunes on val / reports on test.

Usage:  uv run python data/benchmark/render_nl_v2.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
RAW = HERE / "raw_v2"
BENCH = HERE / "benchmark" / "benchmark_v2.jsonl"
OUT = HERE / "benchmark" / "nl_v2.jsonl"


def load(name: str) -> list[dict]:
    return [json.loads(line) for line in (RAW / name).open(encoding="utf-8")]


ID_RE = re.compile(r"\b(c_\d+|o_\d{5}|p_\d{4}|pay_\d{5}|comp_\d{4})\b")


def main() -> int:
    products = {p["product_id"]: p for p in load("products.jsonl")}
    customers = {c["customer_id"]: c for c in load("customers.jsonl")}

    out = []
    kept_ids = 0
    for q in [json.loads(line) for line in BENCH.open(encoding="utf-8")]:
        text = q["question"]
        linked: dict[str, str] = {}          # surface mention -> entity id
        mentions_only: list[str] = []        # mentions an ID regex cannot find

        # replace product mentions with names
        for pid in sorted(re.findall(r"p_\d{4}", text), key=len, reverse=True):
            if pid in products:
                name = products[pid]["name"]
                text = text.replace(pid, name)
                linked[name] = pid
                mentions_only.append(name)

        # replace customer IDs with names (real Nepali names, non-ASCII on purpose)
        for cid in sorted(re.findall(r"c_\d+", text), key=len, reverse=True):
            if cid in customers:
                name = customers[cid]["name"]
                # only swap when the customer is asked *about*, not when the id is the answer
                text = re.sub(rf"\bcustomer {re.escape(cid)}\b", f"customer {name}", text)
                linked[name] = cid
                mentions_only.append(name)
            else:
                kept_ids += 1

        remaining = sorted(set(ID_RE.findall(text)))
        rec = {k: v for k, v in q.items()}
        rec["question"] = text
        rec["linked_entities"] = linked
        rec["mentions_only"] = sorted(set(mentions_only))
        rec["remaining_ids"] = remaining
        out.append(rec)

    with open(OUT, "w", encoding="utf-8") as fh:
        for r in out:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    n_mention = sum(1 for r in out if r["mentions_only"])
    print(f"nl questions: {len(out)}; with natural-language mentions: {n_mention}")
    print(f"sample mention surfaces: {sorted({m for r in out for m in r['mentions_only']})[:6]}")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
