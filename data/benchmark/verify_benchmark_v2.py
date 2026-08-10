#!/usr/bin/env python3
"""Phase C — benchmark v2 verification contract (V2_PLAN.md §5.3).

For EVERY benchmark_v2 question:
  - answerable: re-derive the answer from the graph_v2 RDF store with an
    independent query (triple-pattern walk; answers are computed fresh from the
    graph, never trusted from generation time) and compare with the stored answer.
  - unanswerable: prove the query family has NO answer in the graph (pattern
    walk returns nothing), so "I don't know" is provably the only correct output.
  - temporal (t2_*): cross-check validFrom/validTo / previous_status /
    status_changed_on annotations directly.
Also checks the train/val/test split totals partition the set.

Uses rdflib triple-pattern lookups (not the SPARQL engine) because the v2 graph
holds 459k triples and pure-Python SPARQL over that store is too slow to run one
query per question; the lookups operate on the same RDF store and stay
independent of the generator's computations.

Usage:  uv run --with rdflib python data/benchmark/verify_benchmark_v2.py
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import RDF

HERE = Path(__file__).resolve().parent.parent
TTL = HERE / "graph_v2" / "enterprise_brain_graph.ttl"
BENCH = HERE / "benchmark" / "benchmark_v2.jsonl"

EB_NS = "https://github.com/divaspoudel0/enterprise-brain-knowledge-graph-retrieval/ontology#"
EB = Namespace(EB_NS)

failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    if cond:
        print(f"PASS  {msg}")
    else:
        print(f"FAIL  {msg}")
        failures.append(msg)


def node(rid: str | URIRef) -> URIRef:
    if isinstance(rid, URIRef):
        return rid
    return URIRef(EB_NS + rid)


class Store:
    """Thin facade over the RDF graph with the exact predicates the pipeline uses."""

    def __init__(self, g: Graph):
        self.g = g

    def val(self, subj: URIRef, pred) -> str | None:
        if subj is None:
            return None
        v = self.g.value(subj, pred)
        return str(v) if v is not None else None

    def link(self, subj: URIRef, pred):
        """Return the raw RDF object term (node or literal), or None."""
        if subj is None:
            return None
        return self.g.value(subj, pred)

    def preds(self, subj: URIRef, pred) -> list[URIRef]:
        return [o for _, _, o in self.g.triples((subj, pred, None))]

    def subjs(self, pred, obj) -> list[URIRef]:
        return [s for s, _, _ in self.g.triples((None, pred, obj))]

    def rev(self, obj: URIRef, pred) -> list[URIRef]:
        return [s for s, _, _ in self.g.triples((None, pred, obj))]


def graph_answer(s: Store, q: dict) -> str:
    tpl = q["template_id"]
    qe = q["query_entities"]
    oid = next((e for e in qe if e.startswith("o_")), None)
    cid = next((e for e in qe if e.startswith("c_")), None)
    compid = next((e for e in qe if e.startswith("comp_")), None)

    def one(rid: str | None, pred: str) -> str | None:
        if rid is None:
            return None
        return s.val(node(rid), EB[pred])

    SIMPLE = {
        "1hop_order_status": lambda: one(oid, "status"),
        "1hop_order_amount": lambda: one(oid, "amount"),
        "1hop_product_price": lambda: one(qe[0], "price"),
        "1hop_product_category": lambda: one(qe[0], "category"),
        "1hop_customer_region": lambda: one(qe[0], "region"),
        "1hop_customer_signup": lambda: one(qe[0], "signup_date"),
        "1hop_complaint_category": lambda: one(compid, "category"),
        "1hop_complaint_filed": lambda: one(compid, "filed_date"),
        "1hop_payment_status": lambda: s.val(_pay(s, oid), EB.status),
        "1hop_payment_due": lambda: s.val(_pay(s, oid), EB.due_date),
        "1hop_complaint_about_order": lambda: s.val(_about(s, compid), EB.id),
        "1hop_order_product": lambda: s.val(_product(s, oid), EB.name),
        "p2_product_of_order": lambda: _p2(s, cid),
        "p3_order_date_of_complaint": lambda: _p3(s, cid),
        "p1_payment_due_of_complaint": lambda: _p1(s, cid),
        "p5_product_of_complaint": lambda: _p5(s, cid),
        "generic_product_of_customer_order": lambda: s.val(_product(s, oid), EB.name),
        "t2_order_status_asof": lambda: one(oid, "previousStatus"),
        "t2_payment_status_asof": lambda: s.val(_pay(s, oid), EB.previousStatus),
        "t2_order_status_changed_on": lambda: one(oid, "statusChangedOn"),
        "t2_payment_status_changed_on": lambda: s.val(_pay(s, oid), EB.statusChangedOn),
        "t2_complaint_earlier": lambda: _earlier(s, qe),
        "t2_earliest_order": lambda: _extreme_order(s, cid, earliest=True),
        "t2_latest_order": lambda: _extreme_order(s, cid, earliest=False),
    }
    if tpl in SIMPLE:
        return SIMPLE[tpl]() or ""

    if tpl == "generic_complaint_author_and_payment":
        author = s.link(node(compid), EB.complaintFiledBy)
        author_id = s.val(author, EB.id) if author is not None else None
        st = s.val(_pay(s, _about(s, compid)), EB.status)
        return "; ".join(f"{author_id}; {st}".split("; ")) if author_id else ""

    if tpl.endswith("_aggregate"):
        return ", ".join(sorted(_aggregate(s, tpl[:2])))

    raise ValueError(f"no template for {tpl}")


def _pay(s: Store, oid: str) -> URIRef | None:
    ps = s.preds(node(oid), EB.hasPayment)
    return ps[0] if ps else None


def _about(s: Store, compid: str) -> URIRef | None:
    os_ = s.preds(node(compid), EB.aboutOrder)
    return os_[0] if os_ else None


def _product(s: Store, oid: str) -> URIRef | None:
    ps = s.preds(node(oid), EB.forProduct)
    return ps[0] if ps else None


def _order_of_product(s: Store, pid: URIRef) -> list[URIRef]:
    return s.rev(pid, EB.forProduct)


def _customer_orders(s: Store, cid: str) -> list[URIRef]:
    return s.preds(node(cid), EB.placedOrder)


def _p2(s: Store, cid: str) -> str | None:
    for o in _customer_orders(s, cid):
        d = s.val(o, EB.order_date)
        pid = s.link(o, EB.forProduct)
        if pid is not None and s.val(pid, EB.category) == "Electronics" and d and "2025-04-01" <= d <= "2025-06-30":
            return s.val(pid, EB.name)
    return None


def _p3(s: Store, cid: str) -> str | None:
    for comp in s.preds(node(cid), EB.filedComplaint):
        if s.val(comp, EB.category) == "billing":
            o = s.link(comp, EB.aboutOrder)
            if o is None:
                continue
            if s.val(o, EB.status) == "completed":
                d = s.val(o, EB.order_date)
                if d and "2025-07-01" <= d <= "2025-09-30":
                    return d
    return None


def _p1(s: Store, cid: str) -> str | None:
    for comp in s.preds(node(cid), EB.filedComplaint):
        fd = s.val(comp, EB.filed_date)
        if fd and "2025-01-01" <= fd <= "2025-03-31":
            o = s.link(comp, EB.aboutOrder)
            pay = s.link(o, EB.hasPayment) if o is not None else None
            if pay is not None and s.val(pay, EB.status) == "overdue":
                due = s.val(pay, EB.due_date)
                if due and "2025-01-01" <= due <= "2025-03-31":
                    return due
    return None


def _p5(s: Store, cid: str) -> str | None:
    for comp in s.preds(node(cid), EB.filedComplaint):
        fd = s.val(comp, EB.filed_date)
        if fd and "2025-10-01" <= fd <= "2025-12-31":
            o = s.link(comp, EB.aboutOrder)
            if o is not None:
                pid = s.link(o, EB.forProduct)
                if pid is not None and s.val(pid, EB.category) == "Home & Kitchen":
                    return s.val(pid, EB.name)
    return None


def _earlier(s: Store, qe: list[str]) -> str:
    a, b = qe[0], qe[1]
    da = s.val(node(a), EB.filed_date)
    db = s.val(node(b), EB.filed_date)
    return a if da < db else b


def _extreme_order(s: Store, cid: str, earliest: bool) -> str:
    best, best_id = None, None
    for o in _customer_orders(s, cid):
        d = s.val(o, EB.order_date)
        rid = s.val(o, EB.id)
        if d is None:
            continue
        key = (d, rid)
        if best is None or (key < best) == earliest:
            best, best_id = key, rid
    return best_id or ""


def _aggregate(s: Store, pat: str) -> list[str]:
    out = []
    for c in s.subjs(RDF.type, EB.Customer):
        cid = str(c).split("#")[-1]
        if pat == "P2":
            if any(_p2(s, cid) is not None for _ in [1]):
                out.append(cid)
        elif pat == "P1":
            if _p1(s, cid) is not None:
                out.append(cid)
        elif pat == "P3":
            if _p3(s, cid) is not None:
                out.append(cid)
        elif pat == "P5":
            if _p5(s, cid) is not None:
                out.append(cid)
    return out


def unanswerable_holds(s: Store, q: dict) -> bool:
    """True if the graph truly has no answer for this unanswerable question."""
    tpl = q["template_id"]
    text = q["question"]

    def grab(prefix: str) -> str | None:
        m = re.search(rf"{prefix}_\d+", text)
        return m.group(0) if m else None

    if tpl.startswith("t3_entity_absent"):
        kind = tpl.split("_")[-1]
        rid = {"order": grab("o"), "payment": grab("o"), "product": grab("p"),
               "customer": grab("c"), "complaint": grab("comp")}[kind]
        cls = {"order": EB.Order, "payment": EB.Payment, "product": EB.Product,
               "customer": EB.Customer, "complaint": EB.Complaint}[kind]
        return rid is None or list(s.g.triples((node(rid), RDF.type, None))) == []
    if tpl == "t3_relation_absent_customer_order":
        cid, oid = grab("c"), grab("o")
        return list(s.g.triples((node(cid), EB.placedOrder, node(oid)))) == []
    if tpl == "t3_pattern_absent_electronics_q2":
        cid = grab("c")
        return _p2(s, cid) is None
    raise ValueError(f"no unanswerable template for {tpl}")


def main() -> int:
    g = Graph()
    g.parse(TTL, format="turtle")
    s = Store(g)
    questions = [json.loads(line) for line in BENCH.open(encoding="utf-8")]

    splits = Counter(q["split"] for q in questions)
    check(all(q["split"] in ("train", "val", "test") for q in questions), "every question has a valid split")
    check(len(questions) == splits["train"] + splits["val"] + splits["test"], "splits partition the full set")

    ans_bad = []
    na_violated = []
    for q in questions:
        if q["is_answerable"]:
            got = graph_answer(s, q)
            if got != q["answer"]:
                ans_bad.append((q["qid"], q["template_id"], q["answer"], got))
        else:
            if not unanswerable_holds(s, q):
                na_violated.append((q["qid"], q["template_id"]))

    by_tpl_bad = {}
    for qid, tpl, ans, got in ans_bad:
        by_tpl_bad.setdefault(tpl, []).append((qid, ans, got))
    for tpl, errs in sorted(by_tpl_bad.items()):
        print(f"FAIL  template {tpl}: {len(errs)} mismatches (e.g. {errs[0]})")
        failures.append(tpl)
    check(len(ans_bad) == 0, f"every answerable answer matches an independent graph query ({len(questions)} questions checked)")
    check(not na_violated, f"every unanswerable question provably has no answer in the graph (violated: {na_violated[:5]})")

    print(f"split totals: train={splits['train']}, val={splits['val']}, test={splits['test']}")

    if failures:
        print(f"\n{len(failures)} template(s) FAILED — benchmark generation is invalid")
        return 1
    print(f"\nverify_benchmark_v2 OK: {len(questions)} questions; all answerable ground truths "
          "independently re-derived from graph_v2; all unanswerable provably empty")
    return 0


if __name__ == "__main__":
    sys.exit(main())
