#!/usr/bin/env python3
"""S5 sanity pass — DATA_PIPELINE.md §5 ("does the stated ground truth actually
match a fresh independent graph query?").

For EVERY benchmark question (stronger than the specified 10% sample), re-derives
the answer with an independent SPARQL query against the S3 graph and compares it to
the stored answer. If a template is wrong, it fails on every question of that
template — fix the template, not the individual question.

Usage:  uv run --with rdflib python data/benchmark/verify_benchmark.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from rdflib import Graph, Namespace, URIRef

HERE = Path(__file__).resolve().parent.parent
TTL = HERE / "graph" / "enterprise_brain_graph.ttl"
BENCH = HERE / "benchmark" / "benchmark_v1.jsonl"

EB_NS = "https://github.com/divaspoudel0/enterprise-brain-knowledge-graph-retrieval/ontology#"
EB = Namespace(EB_NS)

failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    if cond:
        print(f"PASS  {msg}")
    else:
        print(f"FAIL  {msg}")
        failures.append(msg)


def node(rid: str) -> URIRef:
    return URIRef(EB_NS + rid)


def q1(g: Graph, sparql: str) -> list[str]:
    """Run a SELECT ?v query and return distinct sorted string values."""
    out = set()
    for row in g.query(sparql):
        v = row["v"]
        out.add(str(v))
    return sorted(out)


def graph_answer(g: Graph, q: dict) -> str:
    tpl = q["template_id"]
    qe = q["query_entities"]
    oid = next((e for e in qe if e.startswith("o_")), None)
    cid = next((e for e in qe if e.startswith("c_")), None)
    compid = next((e for e in qe if e.startswith("comp_")), None)

    def pref(pred: str, subj: str) -> str:
        return f"SELECT ?v {{ {node(subj).n3()} eb:{pred} ?v . }}"

    SIMPLE = {
        "1hop_order_status": lambda: pref("status", oid),
        "1hop_order_amount": lambda: pref("amount", oid),
        "1hop_product_price": lambda: pref("price", qe[0]),
        "1hop_product_category": lambda: pref("category", qe[0]),
        "1hop_customer_region": lambda: pref("region", qe[0]),
        "1hop_customer_signup": lambda: pref("signup_date", qe[0]),
        "1hop_complaint_category": lambda: pref("category", compid),
        "1hop_complaint_filed": lambda: pref("filed_date", compid),
        "1hop_payment_status": lambda: f"SELECT ?v {{ {node(oid).n3()} eb:hasPayment ?p . ?p eb:status ?v . }}",
        "1hop_payment_due": lambda: f"SELECT ?v {{ {node(oid).n3()} eb:hasPayment ?p . ?p eb:due_date ?v . }}",
        "1hop_complaint_about_order": lambda: f"SELECT ?v {{ {node(compid).n3()} eb:aboutOrder ?o . ?o eb:id ?v . }}",
        "1hop_order_product": lambda: f"SELECT ?v {{ {node(oid).n3()} eb:forProduct ?p . ?p eb:name ?v . }}",
        "p2_product_of_order": lambda: f"""SELECT ?v {{ {node(cid).n3()} eb:placedOrder ?o . ?o eb:forProduct ?p .
            ?p eb:category "Electronics" . ?o eb:order_date ?d .
            FILTER(STR(?d) >= "2025-04-01" && STR(?d) <= "2025-06-30") . ?p eb:name ?v . }}""",
        "p3_order_date_of_complaint": lambda: f"""SELECT ?v {{ {node(cid).n3()} eb:filedComplaint ?comp .
            ?comp eb:category "billing" . ?comp eb:aboutOrder ?o . ?o eb:status "completed" .
            ?o eb:order_date ?v . FILTER(STR(?v) >= "2025-07-01" && STR(?v) <= "2025-09-30") . }}""",
        "p1_payment_due_of_complaint": lambda: f"""SELECT ?v {{ {node(cid).n3()} eb:filedComplaint ?comp .
            ?comp eb:filed_date ?fd . FILTER(STR(?fd) >= "2025-01-01" && STR(?fd) <= "2025-03-31") .
            ?comp eb:aboutOrder ?o . ?o eb:hasPayment ?pay . ?pay eb:status "overdue" .
            ?pay eb:due_date ?v . FILTER(STR(?v) >= "2025-01-01" && STR(?v) <= "2025-03-31") . }}""",
        "p5_product_of_complaint": lambda: f"""SELECT ?v {{ {node(cid).n3()} eb:filedComplaint ?comp .
            ?comp eb:filed_date ?fd . FILTER(STR(?fd) >= "2025-10-01" && STR(?fd) <= "2025-12-31") .
            ?comp eb:aboutOrder ?o . ?o eb:forProduct ?p . ?p eb:category "Home & Kitchen" .
            ?p eb:name ?v . }}""",
        "generic_product_of_customer_order": lambda: (f"SELECT ?v {{ {node(cid).n3()} eb:placedOrder {node(oid).n3()} . "
                                                      f"{node(oid).n3()} eb:forProduct ?p . ?p eb:name ?v . }}"),
    }
    if tpl in SIMPLE:
        return ", ".join(q1(g, SIMPLE[tpl]()))

    if tpl == "generic_complaint_author_and_payment":
        sparql = (f"""SELECT ?cid ?st {{ {node(compid).n3()} eb:complaintFiledBy ?c . ?c eb:id ?cid .
            {node(compid).n3()} eb:aboutOrder ?o . ?o eb:hasPayment ?pay . ?pay eb:status ?st . }}""")
        rows = sorted((str(r["cid"]), str(r["st"])) for r in g.query(sparql))
        return "; ".join(f"{c}; {s}" for c, s in rows)

    agg = {
        "P1": (f"""SELECT ?v {{ ?c a eb:Customer . ?c eb:id ?v . ?c eb:filedComplaint ?comp .
            ?comp eb:filed_date ?fd . FILTER(STR(?fd) >= "2025-01-01" && STR(?fd) <= "2025-03-31") .
            ?comp eb:aboutOrder ?o . ?o eb:hasPayment ?pay . ?pay eb:status "overdue" .
            ?pay eb:due_date ?due . FILTER(STR(?due) >= "2025-01-01" && STR(?due) <= "2025-03-31") . }}"""),
        "P2": (f"""SELECT ?v {{ ?c a eb:Customer . ?c eb:id ?v . ?c eb:placedOrder ?o .
            ?o eb:forProduct ?p . ?p eb:category "Electronics" . ?o eb:order_date ?d .
            FILTER(STR(?d) >= "2025-04-01" && STR(?d) <= "2025-06-30") . }}"""),
        "P3": (f"""SELECT ?v {{ ?c a eb:Customer . ?c eb:id ?v . ?c eb:filedComplaint ?comp .
            ?comp eb:category "billing" . ?comp eb:aboutOrder ?o . ?o eb:status "completed" .
            ?o eb:order_date ?d . FILTER(STR(?d) >= "2025-07-01" && STR(?d) <= "2025-09-30") . }}"""),
        "P5": (f"""SELECT ?v {{ ?c a eb:Customer . ?c eb:id ?v . ?c eb:filedComplaint ?comp .
            ?comp eb:filed_date ?fd . FILTER(STR(?fd) >= "2025-10-01" && STR(?fd) <= "2025-12-31") .
            ?comp eb:aboutOrder ?o . ?o eb:forProduct ?p . ?p eb:category "Home & Kitchen" . }}"""),
    }
    if tpl.endswith("_aggregate"):
        return ", ".join(q1(g, agg[tpl[:2]]))

    raise ValueError(f"no SPARQL template for {tpl}")


def main() -> int:
    g = Graph()
    g.parse(TTL, format="turtle")
    questions = [json.loads(line) for line in BENCH.open(encoding="utf-8")]

    per_tpl = {}
    for q in questions:
        got = graph_answer(g, q)
        if got != q["answer"]:
            per_tpl.setdefault(q["template_id"], []).append((q["qid"], q["answer"], got))

    bad = sum(len(v) for v in per_tpl.values())
    for tpl, errs in sorted(per_tpl.items()):
        print(f"FAIL  template {tpl}: {len(errs)} mismatches (e.g. {errs[0]})")
        failures.append(tpl)
    check(bad == 0, f"every question's stored answer matches an independent SPARQL query ({len(questions)} checked)")

    if failures:
        return 1
    print(f"\nverify_benchmark OK: {len(questions)} questions, all ground truths independently "
          "re-derived from the graph")
    return 0


if __name__ == "__main__":
    sys.exit(main())
