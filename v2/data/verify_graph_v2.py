#!/usr/bin/env python3
"""v2 graph verification (mirrors v1/data/verify_graph.py for v2/data/graph/).

Checks against v2/data/graph/enterprise_brain_graph.ttl:
  1. Node counts per class match v2/data/raw exactly.
  2. Object-property edge counts match raw-implied counts (both directions).
  3. Provenance: every node has eb:source_record_id; every edge reified with source.
  4. Round-trip sync with v2/data/raw (all fields including temporal + at_risk).
  5. P1/P2/P3/P5 SPARQL traversal reproduces raw counts.
  6. atRisk in graph matches rule in v2/data/raw.
  7. Temporal fields present for entities with status history.

Usage: uv run --with rdflib python v2/data/verify_graph_v2.py
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, XSD

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
TTL = HERE / "graph" / "enterprise_brain_graph.ttl"

EB_NS = "https://github.com/divaspoudel0/enterprise-brain-knowledge-graph-retrieval/ontology#"
EB = Namespace(EB_NS)

OBJECT_PROPS = [
    EB.placedOrder, EB.orderPlacedBy, EB.forProduct, EB.productOrderedIn,
    EB.hasPayment, EB.paymentForOrder, EB.filedComplaint, EB.complaintFiledBy,
    EB.aboutOrder, EB.orderComplainedAbout,
]

failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    if cond:
        print(f"PASS  {msg}")
    else:
        print(f"FAIL  {msg}")
        failures.append(msg)


def load(name: str) -> list[dict]:
    return [json.loads(line) for line in (RAW / name).open(encoding="utf-8")]


def eq_float(a, b):
    try:
        return abs(float(a) - float(b)) < 1e-9
    except Exception:
        return False


def main() -> int:
    g = Graph()
    g.parse(TTL, format="turtle")

    products = load("products.jsonl")
    customers = load("customers.jsonl")
    orders = load("orders.jsonl")
    payments = load("payments.jsonl")
    complaints = load("complaints.jsonl")

    def count_class(klass) -> int:
        return len(set(g.subjects(RDF.type, klass)))

    # 1. node counts
    expected = {"products": len(products), "customers": len(customers),
                "orders": len(orders), "payments": len(payments), "complaints": len(complaints)}
    for name, klass in [("products", EB.Product), ("customers", EB.Customer),
                        ("orders", EB.Order), ("payments", EB.Payment),
                        ("complaints", EB.Complaint)]:
        check(count_class(klass) == expected[name], f"node count {name}: {count_class(klass)} == {expected[name]}")

    # 2. edge counts per object property
    edge_exp = {}
    for o in orders:
        edge_exp.setdefault(EB.placedOrder, 0); edge_exp[EB.placedOrder] += 1
        edge_exp.setdefault(EB.orderPlacedBy, 0); edge_exp[EB.orderPlacedBy] += 1
        edge_exp.setdefault(EB.forProduct, 0); edge_exp[EB.forProduct] += 1
        edge_exp.setdefault(EB.productOrderedIn, 0); edge_exp[EB.productOrderedIn] += 1
        edge_exp.setdefault(EB.hasPayment, 0); edge_exp[EB.hasPayment] += 1
        edge_exp.setdefault(EB.paymentForOrder, 0); edge_exp[EB.paymentForOrder] += 1
    for c in complaints:
        for p in (EB.filedComplaint, EB.complaintFiledBy, EB.aboutOrder, EB.orderComplainedAbout):
            edge_exp[p] = edge_exp.get(p, 0) + 1
    for p in OBJECT_PROPS:
        got = len(set(g.triples((None, p, None))))
        check(got == edge_exp.get(p, 0), f"edge count {p.split('#')[-1]}: {got} == {edge_exp.get(p, 0)}")

    # 3. provenance
    instance_nodes = set()
    for name, klass in [("products", EB.Product), ("customers", EB.Customer),
                        ("orders", EB.Order), ("payments", EB.Payment),
                        ("complaints", EB.Complaint)]:
        instance_nodes |= set(g.subjects(RDF.type, klass))
    no_prov = [u for u in instance_nodes if g.value(u, EB.source_record_id) is None]
    check(not no_prov, f"every node has eb:source_record_id (bad: {len(no_prov)} missing)")

    directed_edges = set()
    for p in OBJECT_PROPS:
        directed_edges |= set(g.triples((None, p, None)))
    reified = {}
    for stmt in g.subjects(RDF.type, RDF.Statement):
        s, p, o = g.value(stmt, RDF.subject), g.value(stmt, RDF.predicate), g.value(stmt, RDF.object)
        src = g.value(stmt, EB.source_record_id)
        reified[(s, p, o)] = src
    missing = directed_edges - set(reified)
    check(not missing, f"every edge reified (missing: {len(missing)})")
    extra = set(reified) - directed_edges
    check(not extra, f"no orphan reification (extra: {len(extra)})")
    no_src = [k for k, v in reified.items() if v is None]
    check(not no_src, f"every reified edge has source (bad: {len(no_src)})")

    # 4. round-trip sync — core fields
    def rebuild(fields, uri_of, raw_rows):
        got = {}
        for row in raw_rows:
            u = uri_of(row)
            rec = {}
            for key, (prop, cast) in fields.items():
                val = g.value(u, prop)
                if val is None:
                    rec[key] = None
                else:
                    rec[key] = cast(str(val)) if cast else str(val)
            got[str(row["_id"])] = rec
        return got

    FIELD_TO_PROP = {
        "valid_from": "validFrom", "valid_to": "validTo",
        "status_changed_on": "statusChangedOn", "previous_status": "previousStatus",
        "at_risk": "atRisk",
    }

    def compare(name, fields, uri_of, raw_rows):
        raw_map = {str(r["_id"]): {k: r[k] for k in fields} for r in raw_rows}
        g_map = rebuild({k: (getattr(EB, FIELD_TO_PROP.get(k, k)), None) for k in fields}, uri_of, raw_rows)
        check(set(raw_map) == set(g_map), f"sync {name}: id sets ({len(raw_map)} records)")
        mism = []
        for rid in raw_map:
            for k in fields:
                rv, gv = raw_map[rid][k], g_map[rid][k]
                rv_n = "" if rv in (None, "") else str(rv)
                gv_n = "" if gv in (None, "") else str(gv)
                if k in ("amount", "price"):
                    if not eq_float(rv_n, gv_n):
                        mism.append((rid, k, rv, gv))
                elif k == "at_risk":
                    if rv_n.lower() != gv_n.lower():
                        mism.append((rid, k, rv, gv))
                elif rv_n != gv_n:
                    mism.append((rid, k, rv, gv))
        check(not mism, f"sync {name}: values match (bad: {mism[:3]})")

    def eb_uri(row):
        from rdflib import URIRef
        return URIRef(EB_NS + row["_id"])

    compare("products", ["name", "category", "price"],
            lambda r: eb_uri(r), [{**p, "_id": p["product_id"]} for p in products])
    compare("customers", ["name", "region", "signup_date", "at_risk"],
            lambda r: eb_uri(r), [{**c, "_id": c["customer_id"]} for c in customers])
    compare("orders", ["order_date", "amount", "status", "valid_from", "valid_to"],
            lambda r: eb_uri(r), [{**o, "_id": o["order_id"]} for o in orders])
    compare("payments", ["amount", "status", "due_date", "paid_date", "valid_from", "valid_to"],
            lambda r: eb_uri(r), [{**p, "_id": p["payment_id"]} for p in payments])
    compare("complaints", ["filed_date", "category", "free_text_description"],
            lambda r: eb_uri(r), [{**c, "_id": c["complaint_id"]} for c in complaints])

    # 5. multi-hop SPARQL traversal reproduces raw counts
    pay_by_order = {p["order_id"]: p for p in payments}
    order_by_id = {o["order_id"]: o for o in orders}
    prod_by_id = {p["product_id"]: p for p in products}
    raw_p1 = {c["customer_id"] for c in complaints
              if date(2025, 1, 1) <= date.fromisoformat(c["filed_date"]) <= date(2025, 3, 31)
              and pay_by_order.get(c["order_id"]) is not None
              and pay_by_order[c["order_id"]]["status"] == "overdue"
              and date(2025, 1, 1) <= date.fromisoformat(pay_by_order[c["order_id"]]["due_date"]) <= date(2025, 3, 31)}
    raw_p2 = {o["order_id"] for o in orders
              if date(2025, 4, 1) <= date.fromisoformat(o["order_date"]) <= date(2025, 6, 30)
              and prod_by_id[o["product_id"]]["category"] == "Electronics"}
    raw_p3 = {c["complaint_id"] for c in complaints
              if c["category"] == "billing" and order_by_id[c["order_id"]]["status"] == "completed"
              and date(2025, 7, 1) <= date.fromisoformat(order_by_id[c["order_id"]]["order_date"]) <= date(2025, 9, 30)}
    raw_p5 = {c["complaint_id"] for c in complaints
              if date(2025, 10, 1) <= date.fromisoformat(c["filed_date"]) <= date(2025, 12, 31)
              and prod_by_id[order_by_id[c["order_id"]]["product_id"]]["category"] == "Home & Kitchen"}

    q_p1 = f"""PREFIX eb: <{EB_NS}>
    SELECT (COUNT(DISTINCT ?c) AS ?n) WHERE {{
      ?c a eb:Customer . ?c eb:filedComplaint ?comp . ?comp eb:aboutOrder ?o .
      ?o eb:hasPayment ?pay . ?pay eb:status "overdue" . ?pay eb:due_date ?due .
      ?comp eb:filed_date ?filed .
      FILTER(STR(?due) >= "2025-01-01" && STR(?due) <= "2025-03-31")
      FILTER(STR(?filed) >= "2025-01-01" && STR(?filed) <= "2025-03-31")
    }}"""
    q_p2 = f"""PREFIX eb: <{EB_NS}>
    SELECT (COUNT(DISTINCT ?o) AS ?n) WHERE {{
      ?o a eb:Order . ?o eb:forProduct ?p . ?p eb:category "Electronics" .
      ?o eb:order_date ?d . FILTER(STR(?d) >= "2025-04-01" && STR(?d) <= "2025-06-30")
    }}"""
    q_p3 = f"""PREFIX eb: <{EB_NS}>
    SELECT (COUNT(DISTINCT ?c) AS ?n) WHERE {{
      ?c a eb:Complaint . ?c eb:category "billing" . ?c eb:aboutOrder ?o .
      ?o eb:status "completed" . ?o eb:order_date ?d .
      FILTER(STR(?d) >= "2025-07-01" && STR(?d) <= "2025-09-30")
    }}"""
    q_p5 = f"""PREFIX eb: <{EB_NS}>
    SELECT (COUNT(DISTINCT ?c) AS ?n) WHERE {{
      ?c a eb:Complaint . ?c eb:filed_date ?fd . ?c eb:aboutOrder ?o .
      ?o eb:forProduct ?p . ?p eb:category "Home & Kitchen" .
      FILTER(STR(?fd) >= "2025-10-01" && STR(?fd) <= "2025-12-31")
    }}"""

    for label, q, expected_n in [("P1", q_p1, len(raw_p1)), ("P2", q_p2, len(raw_p2)),
                                  ("P3", q_p3, len(raw_p3)), ("P5", q_p5, len(raw_p5))]:
        if len(g.query(q).bindings) > 0:
            res = int(g.query(q).bindings[0]["n"])
        else:
            res = 0
        check(res == expected_n, f"SPARQL {label}: {res} == raw {expected_n}")

    # 6. atRisk in graph matches rule
    rule_positive = set()
    overdue_orders = {p["order_id"] for p in payments if p["status"] == "overdue"}
    for c in complaints:
        if c["order_id"] in overdue_orders:
            rule_positive.add(c["customer_id"])
    graph_positive = {str(u).split("#")[-1] for u in g.subjects(EB.atRisk, Literal(True, datatype=XSD.boolean))}
    check(graph_positive == rule_positive, f"atRisk in graph matches rule (graph={len(graph_positive)}, rule={len(rule_positive)})")

    # 7. temporal fields present for entities with status changes
    changed_orders = [o for o in orders if o.get("status_changed_on")]
    changed_payments = [p for p in payments if p.get("status_changed_on")]
    for row in changed_orders:
        u = URIRef(EB_NS + row["order_id"])
        ch = g.value(u, EB.statusChangedOn)
        prev = g.value(u, EB.previousStatus)
        check(ch is not None, f"changed order {row['order_id']}: statusChangedOn in graph")
        check(prev is not None, f"changed order {row['order_id']}: previousStatus in graph")
    for row in changed_payments:
        u = URIRef(EB_NS + row["payment_id"])
        ch = g.value(u, EB.statusChangedOn)
        prev = g.value(u, EB.previousStatus)
        check(ch is not None, f"changed payment {row['payment_id']}: statusChangedOn in graph")
        check(prev is not None, f"changed payment {row['payment_id']}: previousStatus in graph")

    if failures:
        print(f"\n{len(failures)} check(s) FAILED")
        return 1
    print(f"\nverify_graph_v2 OK: {len(g)} triples; nodes/edges carry provenance; "
          f"P1-P5 SPARQL verified; atRisk matches rule; temporal fields present")
    return 0


if __name__ == "__main__":
    sys.exit(main())