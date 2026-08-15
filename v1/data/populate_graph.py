#!/usr/bin/env python3
"""S3 — populate the RDF knowledge graph from v1/data/raw (DATA_PIPELINE.md §2).

Loads the OWL ontology (ontology/enterprise_brain.ttl) and adds one instance
node per raw row plus object-property edges in BOTH directions of every declared
inverse pair, so multi-hop traversal works in either direction without inverse
property paths.

Provenance (DATA_PIPELINE.md §2): every node carries `eb:source_record_id`; every
directed edge additionally carries its source record via a reified rdf:Statement
annotated with `eb:source_record_id`. (Standard RDF 1.1 reification is used because
rdflib 7.6.0 has no RDF-star support — logged in DECISIONS.md.)

Output: data/graph/enterprise_brain_graph.ttl (committed).

Usage:  uv run --with rdflib python v1/data/populate_graph.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS, XSD

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
ONT = HERE.parent / "ontology" / "enterprise_brain.ttl"
GRAPH_DIR = HERE / "graph"
OUT_TTL = GRAPH_DIR / "enterprise_brain_graph.ttl"

EB_NS = "https://github.com/divaspoudel0/enterprise-brain-knowledge-graph-retrieval/ontology#"
EB = Namespace(EB_NS)

# class URI for each raw entity type
CLASS_OF = {
    "products": EB.Product,
    "customers": EB.Customer,
    "orders": EB.Order,
    "payments": EB.Payment,
    "complaints": EB.Complaint,
}


def load(name: str) -> list[dict]:
    return [json.loads(line) for line in (RAW / name).open(encoding="utf-8")]


def lit_date(v: str) -> Literal:
    return Literal(v, datatype=XSD.date)


def lit_dec(v) -> Literal:
    return Literal(str(v), datatype=XSD.decimal)


def main() -> int:
    g = Graph()
    g.bind("eb", EB)
    g.bind("rdf", RDF)
    g.bind("rdfs", RDFS)
    g.bind("owl", "http://www.w3.org/2002/07/owl#")
    g.bind("xsd", XSD)
    g.parse(ONT, format="turtle")

    products = load("products.jsonl")
    customers = load("customers.jsonl")
    orders = load("orders.jsonl")
    payments = load("payments.jsonl")
    complaints = load("complaints.jsonl")

    # ---- nodes ----
    def node(uri: str) -> URIRef:
        return URIRef(EB_NS + uri)

    def add_node(entity_uri: URIRef, row: dict, props: list[tuple[str, Literal]]) -> None:
        g.add((entity_uri, RDF.type, CLASS_OF[_name_of(row)]))
        g.add((entity_uri, EB.source_record_id, Literal(row["source_id"])))
        g.add((entity_uri, EB.id, Literal(row["source_id"])))
        for prop, val in props:
            g.add((entity_uri, prop, val))

    def _name_of(row: dict) -> str:
        src = row["source_id"]
        if src.startswith("p_"):
            return "products"
        if src.startswith("c_"):
            return "customers"
        if src.startswith("o_"):
            return "orders"
        if src.startswith("pay_"):
            return "payments"
        return "complaints"

    node_uris = {}  # source_id -> URIRef
    for row in products:
        u = node(row["product_id"])
        node_uris[row["product_id"]] = u
        add_node(u, {**row, "source_id": row["product_id"]}, [
            (EB.name, Literal(row["name"])),
            (EB.category, Literal(row["category"])),
            (EB.price, lit_dec(row["price"])),
        ])
    for row in customers:
        u = node(row["customer_id"])
        node_uris[row["customer_id"]] = u
        add_node(u, {**row, "source_id": row["customer_id"]}, [
            (EB.name, Literal(row["name"])),
            (EB.region, Literal(row["region"])),
            (EB.signup_date, lit_date(row["signup_date"])),
        ])
    for row in orders:
        u = node(row["order_id"])
        node_uris[row["order_id"]] = u
        add_node(u, {**row, "source_id": row["order_id"]}, [
            (EB.order_date, lit_date(row["order_date"])),
            (EB.amount, lit_dec(row["amount"])),
            (EB.status, Literal(row["status"])),
        ])
    for row in payments:
        u = node(row["payment_id"])
        node_uris[row["payment_id"]] = u
        props = [
            (EB.amount, lit_dec(row["amount"])),
            (EB.status, Literal(row["status"])),
            (EB.due_date, lit_date(row["due_date"])),
        ]
        if row.get("paid_date"):
            props.append((EB.paid_date, lit_date(row["paid_date"])))
        add_node(u, {**row, "source_id": row["payment_id"]}, props)
    for row in complaints:
        u = node(row["complaint_id"])
        node_uris[row["complaint_id"]] = u
        add_node(u, {**row, "source_id": row["complaint_id"]}, [
            (EB.filed_date, lit_date(row["filed_date"])),
            (EB.category, Literal(row["category"])),
            (EB.free_text_description, Literal(row["free_text_description"])),
        ])

    # ---- edges (both directions; reified provenance) ----
    # source of each edge is the row that defines the relationship
    order_row = {o["order_id"]: o for o in orders}
    complaint_row = {c["complaint_id"]: c for c in complaints}
    pay_by_order = {p["order_id"]: p for p in payments}

    def edge(s: URIRef, p: URIRef, o: URIRef, src_id: str) -> None:
        g.add((s, p, o))
        stmt = BNode()
        g.add((stmt, RDF.type, RDF.Statement))
        g.add((stmt, RDF.subject, s))
        g.add((stmt, RDF.predicate, p))
        g.add((stmt, RDF.object, o))
        g.add((stmt, EB.source_record_id, Literal(src_id)))

    for row in orders:
        c, o, p = node_uris[row["customer_id"]], node_uris[row["order_id"]], node_uris[row["product_id"]]
        pay = node_uris[pay_by_order[row["order_id"]]["payment_id"]]
        edge(c, EB.placedOrder, o, row["order_id"])
        edge(o, EB.orderPlacedBy, c, row["order_id"])
        edge(o, EB.forProduct, p, row["order_id"])
        edge(p, EB.productOrderedIn, o, row["order_id"])
        edge(o, EB.hasPayment, pay, row["order_id"])
        edge(pay, EB.paymentForOrder, o, row["order_id"])
    for row in complaints:
        c, comp, o = (node_uris[row["customer_id"]], node_uris[row["complaint_id"]],
                      node_uris[row["order_id"]])
        edge(c, EB.filedComplaint, comp, row["complaint_id"])
        edge(comp, EB.complaintFiledBy, c, row["complaint_id"])
        edge(comp, EB.aboutOrder, o, row["complaint_id"])
        edge(o, EB.orderComplainedAbout, comp, row["complaint_id"])

    GRAPH_DIR.mkdir(parents=True, exist_ok=True)
    OUT_TTL.write_bytes(g.serialize(format="turtle", encoding="utf-8"))

    print(f"nodes: {len(products)} products, {len(customers)} customers, {len(orders)} orders, "
          f"{len(payments)} payments, {len(complaints)} complaints")
    print(f"total triples (incl ontology + reification): {len(g)}")
    print(f"wrote {OUT_TTL}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
