#!/usr/bin/env python3
"""Phase D (D1) — hybrid-rule baseline on benchmark_v2 (V2_PLAN §6).

The v1 rule-based hybrid (regex entity linking + rule hop cascade + brute-force
10^h traversal + linear fusion + same LLM) re-pointed at benchmark_v2/graph_v2,
as the "hybrid-rule" baseline that hybrid-learned must beat. Same scoring
(EM / F1 / P@5) and same output shape as run_hybrid_learned.py.

Output: systems/hybrid/results_hybrid_rule_v2.json + learned_eval_rule.json
Usage:  uv run --with rdflib --with torch --with transformers \
        --with sentence-transformers python systems/hybrid/run_hybrid_rule_v2.py
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

from rdflib import Graph, Namespace, URIRef

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import (TOP_K, ANSWER_TEMPLATE, STRUCTURED_ANSWER_TEMPLATE,
                    load_corpus, load_llm, load_embeddings, embed_query)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
DATA = ROOT / "data"
CORPUS = DATA / "corpus"
GRAPH = DATA / "graph_v2" / "enterprise_brain_graph.ttl"
BENCH = DATA / "benchmark" / "benchmark_v2.jsonl"
OUT = HERE / "results_hybrid_rule_v2.json"
METRICS = HERE / "learned_eval_rule.json"

EB_NS = "https://github.com/divaspoudel0/enterprise-brain-knowledge-graph-retrieval/ontology#"
EB = Namespace(EB_NS)
ID_RE = re.compile(r"\b(c_\d+|o_\d{5}|p_\d{4}|pay_\d{5}|comp_\d{4})\b")

_g = None


def get_graph() -> Graph:
    global _g
    if _g is None:
        _g = Graph()
        _g.parse(GRAPH, format="turtle")
    return _g


def node(rid: str) -> URIRef:
    return URIRef(EB_NS + rid)


def extract_entities(question: str) -> list[str]:
    return sorted(set(ID_RE.findall(question)))


def hop_controller(question: str, entities: list[str]) -> int:
    """v1 rule-based hop estimate (mirrors run_hybrid.py)."""
    q = question.lower()
    n = len(entities)
    if re.search(r"what is the (status|amount|price|category|region|signup|due|filed) of", q):
        return 1
    if re.search(r"what is the payment (status|due date) for order", q):
        return 1
    if re.search(r"when is the payment for order .* due", q):
        return 1
    if re.search(r"when (did|was) .* (sign up|filed|placed|ordered)", q):
        return 1
    if re.search(r"which (product|order|customer|payment|complaint) (is|was) (about|for|by)", q):
        return 1
    if re.search(r"which order is complaint .* about", q):
        return 1
    if re.search(r"what product was ordered in order", q):
        return 1
    if re.search(r"filed a complaint .* overdue payment.* due", q):
        return 3
    if re.search(r"filed a complaint .* order .* (product|completed)", q):
        return 3 if "product" in q else 2
    if re.search(r"which .* product .* ordered", q):
        return 2
    if re.search(r"filed a complaint", q):
        return 2
    if re.search(r"changed status|before it changed|filed earlier|earliest order|latest order", q):
        return 2
    if "i don't know" in q:
        return 1
    if n > 1:
        return 2
    return 1


PROPS = [EB.placedOrder, EB.orderPlacedBy, EB.forProduct, EB.productOrderedIn,
         EB.hasPayment, EB.paymentForOrder, EB.filedComplaint, EB.complaintFiledBy,
         EB.aboutOrder, EB.orderComplainedAbout]


def traverse_from(entities: list[str], target_hops: int, g: Graph, k: int = TOP_K):
    """v1 brute-force traversal: enumerate all chains of every length <= hops."""
    results = []
    seen = set()
    for eid in entities:
        seen.add(eid)
        results.append({"record_id": eid, "provenance_path": "anchor", "graph_score": 1.0})

    queries = 0
    for depth in range(1, target_hops + 1):
        for chain in __import__("itertools").product(PROPS, repeat=depth):
            queries += 1
            start = node(entities[0])
            vars_ = " ".join(f"?v{i}" for i in range(1, depth + 1))
            where_parts = [f"{start.n3()} {chain[0].n3()} ?v1"]
            for i in range(1, depth):
                where_parts.append(f"?v{i} {chain[i].n3()} ?v{i+1}")
            where = " . ".join(where_parts)
            try:
                rows = list(g.query(f"SELECT ?v{depth} WHERE {{ {where} }} LIMIT {k * 2}"))
            except Exception:
                rows = []
            for row in rows:
                v = row[f"v{depth}"]
                rid = str(v)
                if not rid.startswith(EB_NS) or rid in seen:
                    continue
                seen.add(rid)
                results.append({
                    "record_id": rid[len(EB_NS):],
                    "provenance_path": "->".join(p.split("#")[-1] for p in chain),
                    "graph_score": 1.0,
                })
    return results, queries


def exact_match(pred: str, gold: str) -> bool:
    return pred.strip().lower() == gold.strip().lower()


def token_f1(pred: str, gold: str) -> float:
    p = set(pred.lower().split())
    q = set(gold.lower().split())
    if not p and not q:
        return 1.0
    if not p or not q:
        return 0.0
    inter = p & q
    if not inter:
        return 0.0
    prec = len(inter) / len(p)
    rec = len(inter) / len(q)
    return 2 * prec * rec / (prec + rec)


def load_v2_corpus() -> list[dict]:
    return [json.loads(line) for line in (CORPUS / "text_records_v2.jsonl").open(encoding="utf-8")]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    g = get_graph()
    questions = [json.loads(line) for line in BENCH.open(encoding="utf-8")]
    test = [q for q in questions if q["split"] == "test"]
    if args.limit:
        test = test[: args.limit]

    llm = load_llm()
    corpus = {r["record_id"]: r for r in load_v2_corpus()}

    results = []
    agg = defaultdict(lambda: {"n": 0, "em": 0, "f1": 0, "p5": 0, "paths": 0})
    total_queries = 0

    for qi, q in enumerate(test):
        qtext = q["question"]
        gold = q["answer"]
        gold_ids = q["answer_ids"]

        entities = extract_entities(qtext)
        hops = hop_controller(qtext, entities) if q["is_answerable"] else 1
        cands, queries = traverse_from(entities, hops, g)
        total_queries += queries

        ctx_parts = [corpus[c["record_id"]]["text"] for c in cands[:TOP_K]
                     if c["record_id"] in corpus]
        context = "\n".join(ctx_parts)
        prompt = STRUCTURED_ANSWER_TEMPLATE.format(context=context, question=qtext)
        out = llm(prompt, max_new_tokens=64)[0]["generated_text"]
        answer = out.rsplit("predicted_answer", 1)[-1].strip() if "predicted_answer" in out else out
        answer = answer.split("\nexplanation:")[0].strip().strip(":").strip()

        em = exact_match(answer, gold)
        f1 = token_f1(answer, gold)
        p5 = float(any(gg.lower() in answer.lower() for gg in (gold_ids or [])))

        group = "T3" if not q["is_answerable"] else ("T2" if q["template_id"].startswith("t2") else "T1")
        hop_key = f"hop{q['hops']}" if q["is_answerable"] else "na"
        for key in (group, hop_key, "all"):
            a = agg[key]
            a["n"] += 1; a["em"] += em; a["f1"] += f1; a["p5"] += p5
            a["paths"] += queries

        results.append({
            "qid": q["qid"], "template_id": q["template_id"], "group": group,
            "question": qtext, "gold": gold, "predicted": answer,
            "em": em, "f1": f1, "p5": p5,
            "linked_entities": entities, "hops_oracle": q["hops"], "hops_pred": hops,
            "paths_enumerated": queries,
        })
        if (qi + 1) % 25 == 0:
            print(f"  [{qi+1}/{len(test)}] done", flush=True)

    print("\n=== hybrid-rule v2 (benchmark_v2 test) ===")
    for key in sorted(agg):
        a = agg[key]
        if a["n"]:
            print(f"{key:>8}: n={a['n']:3d}  EM={a['em']/a['n']:.3f}  "
                  f"F1={a['f1']/a['n']:.3f}  P@5={a['p5']/a['n']:.3f}  paths/q={a['paths']/a['n']:.0f}")
    print(f"total SPARQL queries issued (brute force): {total_queries}")

    OUT.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    METRICS.write_text(json.dumps(
        {k: {"n": a["n"], "EM": a["em"] / a["n"] if a["n"] else 0,
             "F1": a["f1"] / a["n"] if a["n"] else 0,
             "P@5": a["p5"] / a["n"] if a["n"] else 0,
             "paths_per_q": a["paths"] / a["n"] if a["n"] else 0}
         for k, a in sorted(agg.items())} | {"total_queries": total_queries},
        indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT} and {METRICS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
