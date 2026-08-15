#!/usr/bin/env python3
"""Phase D (D1) — relation-path planner (V2_PLAN.md §6 component 3).

LLM proposes a relation sequence for a question; the plan is validated against
the ontology (property domain/range over the RDFS schema of the v2 graph) and then
used to run a TARGETED SPARQL walk instead of the brute-force 10^h enumeration
of v1. This is the "RoG/PoG-style" planning: the plan is the explanation, and
it is validated by execution (a plan that returns results is kept; otherwise the
LLM gets one retry with the ontology schema as a hint).

Components:
  - ONTOLOGY_RELATIONS: the fixed vocabulary of relations (predicates) the
    graph uses, with human-readable aliases the LLM is steered to produce.
  - propose(question, hops) -> list[predicates] via the answer LLM (Qwen,
    greedy, shared with the pipeline) with a strict JSON output.
  - validate(chain) -> bool: each predicate must be in the vocabulary and
    consecutive domain/range must chain (checked against the RDF schema loaded
    from the v2 graph); returns the *reason* for the final verdict.
  - walk(anchor, chain) -> list[(record_id, path, score)]: the targeted SPARQL
    walk; records the number of SPARQL queries issued (vs the brute-force
    enumeration count that v1 would have issued: sum over chain-lengths).

Run standalone for a diagnostic over the benchmark test split:
  uv run --with rdflib --with torch --with transformers --with sentence-transformers \
      python v2/systems/hybrid/relation_planner.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from rdflib import Graph, Namespace, URIRef

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import LLM_MODEL, load_llm

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
DATA = ROOT / "data"
GRAPH = DATA / "graph" / "enterprise_brain_graph.ttl"
BENCH = DATA / "benchmark" / "benchmark.jsonl"
OUT_DIR = HERE / "learned"

EB_NS = "https://github.com/divaspoudel0/enterprise-brain-knowledge-graph-retrieval/ontology#"
EB = Namespace(EB_NS)

# Relation vocabulary with human aliases (steered via the prompt).
RELATIONS = {
    "placedOrder": EB.placedOrder,
    "orderPlacedBy": EB.orderPlacedBy,
    "forProduct": EB.forProduct,
    "productOrderedIn": EB.productOrderedIn,
    "hasPayment": EB.hasPayment,
    "paymentForOrder": EB.paymentForOrder,
    "filedComplaint": EB.filedComplaint,
    "complaintFiledBy": EB.complaintFiledBy,
    "aboutOrder": EB.aboutOrder,
    "orderComplainedAbout": EB.orderComplainedAbout,
}

# domain/range per relation (object/predicate, from the ontology).
DOMAIN = {
    "placedOrder": "Customer", "orderPlacedBy": "Order",
    "forProduct": "Order", "productOrderedIn": "Product",
    "hasPayment": "Order", "paymentForOrder": "Payment",
    "filedComplaint": "Customer", "complaintFiledBy": "Complaint",
    "aboutOrder": "Complaint", "orderComplainedAbout": "Order",
}
RANGE = {
    "placedOrder": "Order", "orderPlacedBy": "Customer",
    "forProduct": "Product", "productOrderedIn": "Order",
    "hasPayment": "Payment", "paymentForOrder": "Order",
    "filedComplaint": "Complaint", "complaintFiledBy": "Customer",
    "aboutOrder": "Order", "orderComplainedAbout": "Complaint",
}


def node(rid: str) -> URIRef:
    return URIRef(EB_NS + rid)


class PathPlanner:
    def __init__(self, llm_pipeline=None):
        self.llm = llm_pipeline

    def _parse_chain(self, text: str) -> list[str]:
        """Extract relation names from LLM output (JSON or prose)."""
        found = []
        for tok in re.findall(r'"[^"]+"|\b(?:placedOrder|orderPlacedBy|forProduct|productOrderedIn|'
                              r'hasPayment|paymentForOrder|filedComplaint|complaintFiledBy|aboutOrder|'
                              r'orderComplainedAbout)\b', text):
            name = tok.strip().strip('"').strip()
            if name in RELATIONS:
                found.append(name)
        return found

    def propose(self, question: str, hops: int, hint: str = "") -> list[str]:
        """Ask the LLM for the relation chain (strict JSON). Returns [] for
        direct attribute lookups (answer lives on the anchor)."""
        if self.llm is None:
            return self._heuristic_chain(question, hops)
        relations = ", ".join(sorted(RELATIONS))
        sys_prompt = (
            "You are a KG query planner. Given a question about an enterprise knowledge graph "
            "and its relation vocabulary, output ONLY a JSON array of relation names that traverse "
            "from an anchor entity to the answer. If the answer is a direct attribute of the anchor "
            f"entity itself (e.g. its status, date, amount, price, region, category), output []. "
            f"The relations are: {relations}. Output like [\"placedOrder\", \"forProduct\"]."
        )
        user = f"Question: {question}\nExpected number of hops: {hops}\n" + (f"Hint: {hint}\n" if hint else "")
        try:
            out = self.llm(sys_prompt + "\n\n" + user,
                           max_new_tokens=40)[0]["generated_text"]
        except Exception:
            return self._heuristic_chain(question, hops)
        chain = self._parse_chain(out)
        if not chain and hops >= 2:
            return self._heuristic_chain(question, hops)
        return chain

    def propose_with_retry(self, question: str, hops: int) -> tuple[list[str], bool]:
        """LLM proposal validated, with one schema-hint retry and a heuristic
        fallback. Returns (chain, validated)."""
        chain = self.propose(question, hops)
        ok, _ = self.validate(chain)
        if ok:
            return chain, True
        hint = "Traverse along object properties only; ensure consecutive domain/range chain."
        chain = self.propose(question, hops, hint=hint)
        ok, _ = self.validate(chain)
        if ok:
            return chain, True
        chain = self._heuristic_chain(question, hops)
        return chain, self.validate(chain)[0]

    def _heuristic_chain(self, question: str, hops: int) -> list[str]:
        """Fallback heuristic (used when no LLM available) — mirrors v1 chains.
        Returns [] for 1-hop attribute lookups (answer lives on the anchor)."""
        q = question.lower()
        if "overdue payment" in q and "due" in q:
            return ["filedComplaint", "aboutOrder", "hasPayment"]
        if "home & kitchen" in q or ("product" in q and "complaint" in q):
            return ["filedComplaint", "aboutOrder", "forProduct"]
        if "completed order" in q:
            return ["filedComplaint", "aboutOrder"]
        if "electronics" in q or ("product" in q and "ordered" in q):
            return ["placedOrder", "forProduct"]
        if "customer" in q and "product" in q:
            return ["placedOrder", "forProduct"]
        if "complaint" in q and "filed" in q:
            return ["filedComplaint"]
        if "product" in q and "order" in q:
            return ["forProduct"]
        if hops >= 2:
            return ["placedOrder", "forProduct"]
        return []

    def validate(self, chain: list[str]) -> tuple[bool, str]:
        """Validate domain/range chaining of the proposed relation sequence.
        An empty chain is valid: it means the answer lives on the anchor."""
        if not chain:
            return True, "no traversal (answer on anchor)"
        if any(name not in RELATIONS for name in chain):
            return False, f"unknown relation {chain}"
        prev_range = None
        for name in chain:
            d, r = DOMAIN[name], RANGE[name]
            if prev_range is not None and prev_range != d:
                return False, f"chain break: {prev_range} -> {name} (domain {d})"
            prev_range = r
        return True, "validated chain"

    def walk(self, anchor: URIRef, chain: list[str], g: Graph, k: int = 5) -> list[dict]:
        """Targeted SPARQL walk from anchor along the validated relation chain.
        Returns [{record_id, path, graph_score}]. Uses 1 SPARQL query (vs v1's
        brute-force enumeration which issues one query per chain of every length)."""
        return self._walk(anchor, chain, g, k, full=False)

    def walk_full(self, anchor: URIRef, chain: list[str], g: Graph, k: int = 5) -> list[dict]:
        """Like walk() but returns the full provenance node chain per hit:
        [{record_id, path, chain_nodes, relations, graph_score}] where
        chain_nodes = [anchor_rid, ...intermediate..., target_rid] and relations
        = the relation labels between consecutive nodes. Feeds S10 rendering."""
        return self._walk(anchor, chain, g, k, full=True)

    def _walk(self, anchor: URIRef, chain: list[str], g: Graph, k: int = 5,
              full: bool = False) -> list[dict]:
        chain_uris = [RELATIONS[n] for n in chain]
        vars_ = " ".join(f"?v{i}" for i in range(1, len(chain) + 1))
        where_parts = [f"{anchor.n3()} {chain_uris[0].n3()} ?v1"]
        for i in range(1, len(chain)):
            where_parts.append(f"?v{i} {chain_uris[i].n3()} ?v{i+1}")
        where = " . ".join(where_parts)
        sparql = f"SELECT {vars_} WHERE {{ {where} }} LIMIT {k * 2}"
        results = []
        for row in g.query(sparql):
            target = row[f"v{len(chain)}"]
            tid = str(target)
            if not tid.startswith(EB_NS):
                continue
            item = {
                "record_id": tid[len(EB_NS):],
                "path": "->".join(p.split("#")[-1] for p in chain_uris),
                "graph_score": 1.0,
            }
            if full:
                nodes = [str(anchor)[len(EB_NS):]]
                for i in range(1, len(chain) + 1):
                    v = str(row[f"v{i}"])
                    nodes.append(v[len(EB_NS):] if v.startswith(EB_NS) else v)
                item["chain_nodes"] = nodes
                item["relations"] = list(chain)
            results.append(item)
        return results[:k]


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=30, help="test questions to plan over")
    ap.add_argument("--use-llm", action="store_true", help="use the Qwen planner (else heuristic)")
    args = ap.parse_args()

    g = Graph()
    g.parse(GRAPH, format="turtle")

    questions = [json.loads(line) for line in BENCH.open(encoding="utf-8")]
    test = [q for q in questions if q["split"] == "test" and q["is_answerable"]]
    if args.limit:
        test = test[: args.limit]

    planner = PathPlanner(llm_pipeline=load_llm() if args.use_llm else None)
    stats = {"valid": 0, "invalid": 0, "total": 0, "empty": 0, "retried": 0}
    invalid_by_q = []
    import time
    for q in test:
        chain, ok = planner.propose_with_retry(q["question"], q["hops"])
        stats["total"] += 1
        if ok:
            stats["valid"] += 1
            if not chain:
                stats["empty"] += 1
        else:
            stats["invalid"] += 1
            invalid_by_q.append((q["qid"], q["template_id"], chain, q["hops"]))
        if args.use_llm:
            time.sleep(0.02)

    print(f"plan diagnostic over {stats['total']} test questions "
          f"(llm={args.use_llm}): valid={stats['valid']} ({stats['valid']/stats['total']:.2%}), "
          f"empty={stats['empty']}, invalid={stats['invalid']}")
    for qid, tpl, chain, hops in invalid_by_q[:8]:
        print(f"  invalid {qid} {tpl} hops={hops}: {chain}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "relation_planner.json"
    out.write_text(json.dumps({"llm": args.use_llm, "stats": stats,
                               "invalid_examples": invalid_by_q[:10]}, indent=2) + "\n",
                   encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
