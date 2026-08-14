#!/usr/bin/env python3
"""Phase D (D2) — S10 query interface (V2_PLAN §7.2).

Local interface (CLI, optional Gradio) over the hybrid-learned pipeline.
For a natural-language question it returns:

  - the predicted answer,
  - the retrieved evidence chunks,
  - the graph provenance path rendered as entity --relation--> entity
    (e.g. c_0001 --placedOrder--> o_00005 --forProduct--> p_0003),
  - for hybrid-learned: the generated relation plan as the explanation.

CLI:
  python systems/hybrid/query_interface.py "What is the status of order o_00001?"
  python systems/hybrid/query_interface.py --gradio --host 0.0.0.0 --port 7860

The interface reuses the exact D1 components: learned entity linker, learned hop
controller, LLM relation-path planner, targeted SPARQL walk, linear fusion, and
the same structured answer prompt. The explanation is the validated relation
plan (empty plan = answer on the anchor).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from rdflib import Graph

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import (TOP_K, STRUCTURED_ANSWER_TEMPLATE, embed_query, load_llm,
                    parse_structured_output)
from hybrid.entity_linker import EntityLinker
from hybrid.hop_controller import entity_features
from hybrid.relation_planner import PathPlanner, node

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
DATA = ROOT / "data"
CORPUS = DATA / "corpus"
GRAPH = DATA / "graph_v2" / "enterprise_brain_graph.ttl"

ID_RE = re.compile(r"\b(c_\d+|o_\d{5}|p_\d{4}|pay_\d{5}|comp_\d{4})\b")

_g = None
_linker = None
_planner = None
_llm = None
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


def _corpus():
    global _corpus_map
    if _corpus_map is None:
        _corpus_map = {r["record_id"]: r for r in load_v2_corpus()}
    return _corpus_map


def v2_retrieve(query_emb, k: int = TOP_K) -> list[dict]:
    global _corpus_matrix, _corpus_meta
    if _corpus_matrix is None:
        _corpus_matrix = __import__("numpy").load(CORPUS / "embeddings_v2.npy")
        _corpus_meta = json.loads((CORPUS / "embeddings_meta_v2.json").read_text(encoding="utf-8"))
    scores = _corpus_matrix @ query_emb
    order = __import__("numpy").argsort(-scores)[:k]
    corpus = _corpus()
    out = []
    for idx in order:
        idx = int(idx)
        cid = _corpus_meta["chunk_ids"][idx]
        rid = _corpus_meta["chunk_to_record"][cid]
        out.append({"record_id": rid, "score": float(scores[idx]),
                    "text": corpus[rid]["text"][:120]})
    return out


def learned_hop(question: str, emb: list[float]) -> int:
    global _hop_model, _hop_scaler
    if _hop_model is None:
        import joblib
        base = HERE / "learned" / "hop_controller_assets"
        _hop_model = joblib.load(base / "model.joblib")
        _hop_scaler = joblib.load(base / "scaler.joblib")
    feats = entity_features(question)
    X = _hop_scaler.transform([emb + feats])
    return int(_hop_model.predict(X)[0])


def load_components():
    global _linker, _planner, _llm
    if _linker is None:
        _llm = load_llm()
        _linker = EntityLinker()
        _linker.load_index()
        _planner = PathPlanner(llm_pipeline=_llm)


def answer(question: str, top_k: int = TOP_K) -> dict:
    """Run the full hybrid-learned pipeline for one question."""
    load_components()
    g = get_graph()
    corpus = _corpus()

    ids = set(ID_RE.findall(question))
    linked = sorted(ids) if ids else [c["record_id"] for c in _linker.link(question, k=5)]

    hops = learned_hop(question, embed_query(question).tolist())

    candidates = []
    seen = set()
    for eid in linked:
        if eid in seen:
            continue
        seen.add(eid)
        candidates.append({"record_id": eid, "path": "anchor",
                           "chain_nodes": [eid], "relations": [], "graph_score": 1.0})

    plan, plan_valid = [], True
    for anchor in linked:
        chain, ok = _planner.propose_with_retry(question, hops)
        plan, plan_valid = chain, ok
        if not ok or hops < 1 or not chain:
            continue
        for r in _planner.walk_full(node(anchor), chain, g, k=top_k):
            if r["record_id"] in seen:
                continue
            seen.add(r["record_id"])
            candidates.append(r)

    vec = v2_retrieve(embed_query(question), k=top_k)
    ctx_parts = []
    for c in candidates[:top_k]:
        rec = corpus.get(c["record_id"])
        if rec:
            ctx_parts.append(rec["text"])
    for v in vec[: top_k - len(ctx_parts)]:
        rec = corpus.get(v["record_id"])
        if rec:
            ctx_parts.append(rec["text"])
    context = "\n".join(ctx_parts[:top_k])

    prompt = STRUCTURED_ANSWER_TEMPLATE.format(context=context, question=question)
    out = _llm(prompt, max_new_tokens=64)[0]["generated_text"]
    pred, explanation = parse_structured_output(out)

    provenance = []
    for c in candidates:
        if not c["relations"]:
            continue
        chain_nodes = c.get("chain_nodes", [])
        rel = c["relations"]
        path_str = chain_nodes[0]
        for i in range(1, len(chain_nodes)):
            rel_label = rel[i - 1] if i - 1 < len(rel) else "?"
            path_str += f" --{rel_label}--> {chain_nodes[i]}"
        provenance.append({"target": c["record_id"], "path": path_str,
                           "nodes": chain_nodes, "relations": rel})

    # reconstruct (record_id -> text) for the evidence chunks the LLM saw
    seen_ctx = set()
    evidence = []
    for c in candidates[:top_k]:
        rec = corpus.get(c["record_id"])
        if rec and c["record_id"] not in seen_ctx:
            seen_ctx.add(c["record_id"])
            evidence.append({"record_id": c["record_id"], "text": rec["text"][:120]})
    for v in vec[: top_k]:
        if v["record_id"] not in seen_ctx:
            seen_ctx.add(v["record_id"])
            evidence.append({"record_id": v["record_id"], "text": v["text"]})

    return {
        "question": question,
        "predicted_answer": pred,
        "explanation_plan": plan if plan_valid else None,
        "plan_valid": plan_valid,
        "hops": hops,
        "linked_entities": linked,
        "evidence_chunks": evidence,
        "provenance_paths": provenance,
    }


def _render(res: dict) -> str:
    lines = [
        f"Question: {res['question']}",
        f"Answer:   {res['predicted_answer']}",
        f"Plan:     {res['explanation_plan'] if res['explanation_plan'] is not None else '(answer on anchor)'}"
        f"{'' if res['plan_valid'] else '  [invalid, heuristic fallback]'}",
        f"Hops:     {res['hops']}   Linked: {', '.join(res['linked_entities'])}",
        "",
        "Graph provenance path(s):",
    ]
    if res["provenance_paths"]:
        for p in res["provenance_paths"]:
            lines.append(f"  {p['path']}")
    else:
        lines.append("  (none — answer read from the anchor/vector evidence)")
    lines += ["", "Top evidence chunks:"]
    for i, e in enumerate(res["evidence_chunks"][:5], 1):
        lines.append(f"  [{i}] {e['record_id']}: {e['text']}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("question", nargs="?", help="the question to answer")
    ap.add_argument("--gradio", action="store_true", help="launch the Gradio UI")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=7860)
    ap.add_argument("--share", action="store_true")
    args = ap.parse_args()

    if args.gradio:
        try:
            import gradio as gr
        except ImportError:
            print("gradio not installed — run: uv run --with gradio ... --gradio")
            return 1

        def qa(q: str) -> str:
            try:
                return _render(answer(q))
            except Exception as e:  # surface errors in the UI
                return f"error: {e}"

        load_components()  # warm up before serving
        ui = gr.Interface(fn=qa, inputs=gr.Textbox(lines=3, label="Question"),
                          outputs=gr.Markdown(), title="Enterprise-brain KG QA (hybrid-learned)",
                          description="Answer + evidence chunks + graph provenance path + plan-as-explanation")
        ui.launch(server_name=args.host, server_port=args.port, share=args.share, show_error=True)
        return 0

    if not args.question:
        ap.error("provide a question (or use --gradio)")
    print(_render(answer(args.question)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
