#!/usr/bin/env python3
"""Phase D (D2) — S8 groundedness eval on hybrid-learned answers.

Replays the hybrid-learned RETRIEVAL (linking → hop → plan-then-execute →
fusion) for every benchmark_v2 test question WITHOUT regenerating answers, saves
the exact evidence chunks the answer LLM saw, and scores the committed
results_hybrid_learned_v2.json answers with the S8 NLI scorer.

Evidence fidelity: linked entities and predicted hops come from the frozen D1
results file (not re-linked). Vector top-k is deterministic. The traversal
relation chain is planned by the SAME planner the D1 run used — an LLM planner
when `--llm-planner` is given (molab), otherwise the deterministic heuristic
planner (chains mirror the validated template chains; the LLM planner agreed
with the heuristics 40/40 on the validation sample). The evidence source is
recorded in the output.

Output: systems/hybrid/learned_eval_groundedness.json
        systems/hybrid/groundedness_details.json
Usage:  uv run --with rdflib --with torch --with transformers \
        --with sentence-transformers --with scikit-learn \
        python systems/hybrid/run_d2_groundedness.py [--llm-planner]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np

from rdflib import Graph, URIRef

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import TOP_K, embed_query
from hybrid.entity_linker import EntityLinker
from hybrid.relation_planner import PathPlanner, node
from hybrid.groundedness import score_answer

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
DATA = ROOT / "data"
CORPUS = DATA / "corpus"
GRAPH = DATA / "graph_v2" / "enterprise_brain_graph.ttl"
BENCH = DATA / "benchmark" / "benchmark_v2.jsonl"
RESULTS = HERE / "results_hybrid_learned_v2.json"
CONTEXTS = HERE / "learned_contexts_v2.json"
OUT_DETAILS = HERE / "groundedness_details.json"
OUT_METRICS = HERE / "learned_eval_groundedness.json"

ID_RE = re.compile(r"\b(c_\d+|o_\d{5}|p_\d{4}|pay_\d{5}|comp_\d{4})\b")

_g = None
_linker = None
_hop_model = None
_hop_scaler = None
_corpus_matrix = None
_corpus_meta = None
_corpus_map = None


def get_graph() -> Graph:
    global _g
    if _g is None:
        _g = Graph()
        _g.parse(GRAPH, format="turtle")
    return _g


def load_v2_corpus() -> list[dict]:
    return [json.loads(line) for line in (CORPUS / "text_records_v2.jsonl").open(encoding="utf-8")]


def v2_retrieve(query_emb, k: int = TOP_K) -> list[dict]:
    global _corpus_matrix, _corpus_meta, _corpus_map
    if _corpus_matrix is None:
        _corpus_matrix = np.load(CORPUS / "embeddings_v2.npy")
        _corpus_meta = json.loads((CORPUS / "embeddings_meta_v2.json").read_text(encoding="utf-8"))
        _corpus_map = {r["record_id"]: r for r in load_v2_corpus()}
    scores = _corpus_matrix @ query_emb
    order = np.argsort(-scores)[:k]
    out = []
    for idx in order:
        idx = int(idx)
        cid = _corpus_meta["chunk_ids"][idx]
        rid = _corpus_meta["chunk_to_record"][cid]
        out.append({"record_id": rid, "score": float(scores[idx]),
                    "text": _corpus_map[rid]["text"][:120]})
    return out


def traverse_learned(anchor_ids, hops, question, g, planner):
    """Plan-then-execute traversal (same as D1). Returns candidate records."""
    results = []
    seen = set()
    for eid in anchor_ids:
        if eid in seen:
            continue
        seen.add(eid)
        results.append({"record_id": eid, "graph_score": 1.0})
    for anchor in anchor_ids:
        chain, ok = planner.propose_with_retry(question, hops)
        if not ok or hops < 1 or not chain:
            continue
        for r in planner.walk(node(anchor), chain, g, k=TOP_K):
            if r["record_id"] in seen:
                continue
            seen.add(r["record_id"])
            results.append(r)
    return results


def build_context(q, stored) -> list[str]:
    qtext = q["question"]
    linked = stored["linked_entities"]
    if not linked:
        ids = set(ID_RE.findall(qtext))
        linked = sorted(ids) if ids else [c["record_id"] for c in _linker.link(qtext, k=5)]

    hops = stored["hops_pred"]

    g = get_graph()
    cands = traverse_learned(linked, hops, qtext, g, _planner)

    vec = v2_retrieve(embed_query(qtext), k=TOP_K)
    ctx_parts = []
    for c in cands[:TOP_K]:
        rec = _corpus_map.get(c["record_id"])
        if rec:
            ctx_parts.append(rec["text"])
    for v in vec[: TOP_K - len(ctx_parts)]:
        rec = _corpus_map.get(v["record_id"])
        if rec:
            ctx_parts.append(rec["text"])
    return ctx_parts[:TOP_K]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--llm-planner", action="store_true",
                    help="use the LLM relation planner (molab); default is the "
                         "deterministic heuristic planner")
    args = ap.parse_args()

    questions = [json.loads(line) for line in BENCH.open(encoding="utf-8")]
    test = [q for q in questions if q["split"] == "test"]
    if args.limit:
        test = test[: args.limit]

    results = json.load(open(RESULTS, encoding="utf-8"))
    results_by_qid = {r["qid"]: r for r in results}

    global _linker, _planner
    _linker = EntityLinker()
    _linker.load_index()
    if args.llm_planner:
        from common import load_llm
        _planner = PathPlanner(llm_pipeline=load_llm())
    else:
        _planner = PathPlanner(llm_pipeline=None)

    contexts = {}
    rows = []
    gs, abst = [], 0
    total = 0
    for q in test:
        qid = q["qid"]
        stored = results_by_qid.get(qid)
        if stored is None:
            continue
        pred = stored["predicted"]
        # evidence from the frozen D1 run: stored linked entities + predicted hops
        ctx = build_context(q, stored)
        contexts[qid] = ctx
        s = score_answer(pred, ctx)
        gs.append(s["groundedness"])
        abst += s["abstention"]
        rows.append({
            "qid": qid, "predicted": pred, "gold": q["answer"],
            "is_answerable": q["is_answerable"],
            "groundedness": s["groundedness"], "hallucination": s["hallucination"],
            "claims": s["claims"], "per_claim": s.get("per_claim"),
            "abstention": s["abstention"], "evidence_n": s["evidence_n"],
        })
        total += 1
        if total % 50 == 0:
            print(f"  [{total}/{len(test)}] scored", flush=True)

    n = total
    grounded_all = float(np.mean(gs))
    ans_rows = [r for r in rows if not r["abstention"]]
    grounded_ans = float(np.mean([r["groundedness"] for r in ans_rows])) if ans_rows else 0.0
    t3 = [r for r in rows if not r["is_answerable"]]
    t3_grounded = float(np.mean([r["groundedness"] for r in t3])) if t3 else 0.0
    t3_abstain = sum(1 for r in t3 if r["abstention"])
    t3_correct_abstain = sum(1 for r in t3 if r["abstention"] and r["predicted"].strip().lower() == "i don't know")

    metrics = {
        "model": "cross-encoder/nli-deberta-v3-base",
        "planner": "llm" if args.llm_planner else "heuristic",
        "n": n,
        "groundedness_all": grounded_all,
        "hallucination_all": 1.0 - grounded_all,
        "groundedness_answerable": grounded_ans,
        "hallucination_answerable": 1.0 - grounded_ans,
        "t3": {"n": len(t3), "groundedness": t3_grounded,
               "abstention_rate": t3_abstain / len(t3) if t3 else 0.0,
               "correct_abstention_rate": t3_correct_abstain / len(t3) if t3 else 0.0},
    }
    print("\n=== S8 groundedness (hybrid-learned, benchmark_v2 test) ===")
    print(f"groundedness (all): {grounded_all:.3f}  hallucination: {1.0-grounded_all:.3f}")
    print(f"groundedness (answerable only): {grounded_ans:.3f}  "
          f"hallucination: {1.0-grounded_ans:.3f}")
    print(f"T3 (n={len(t3)}): groundedness {t3_grounded:.3f}, abstention {metrics['t3']['abstention_rate']:.3f}, "
          f"correct \"I don't know\" {metrics['t3']['correct_abstention_rate']:.3f}")

    CONTEXTS.write_text(json.dumps(contexts, ensure_ascii=False) + "\n", encoding="utf-8")
    OUT_DETAILS.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    OUT_METRICS.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {CONTEXTS}, {OUT_DETAILS}, {OUT_METRICS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
