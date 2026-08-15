#!/usr/bin/env python3
"""v2 graph population — mirrors v1/data/populate_graph.py for v2/data/raw/.

Loads v2/ontology/enterprise_brain_v2.ttl and populates RDF graph from v2/data/raw entity rows
with:
  - instance nodes with all v2 data properties (including temporal fields, at_risk)
  - object-property edges in BOTH directions (same as v1)
  - reified rdf:Statement provenance on every edge (eb:source_record_id)

Output: v2/data/graph/enterprise_brain_graph.ttl

Usage: uv run --with rdflib python v2/data/populate_graph_v2.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS, XSD

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
ONT = HERE.parent / "ontology" / "enterprise_brain_v2.ttl"
GRAPH_DIR = HERE / "graph"
OUT_TTL = GRAPH_DIR / "enterprise_brain_graph.ttl"

EB_NS = "https://github.com/divaspoudel0/enterprise-brain-knowledge-graph-retrieval/ontology#"
EB = Namespace(EB_NS)

# raw-v2 field name -> ontology property local name (ontology uses camelCase for v2 props)
FIELD_TO_PROP = {
    "valid_from": "validFrom",
    "valid_to": "validTo",
    "status_changed_on": "statusChangedOn",
    "previous_status": "previousStatus",
    "at_risk": "atRisk",
    "free_text_description": "free_text_description",
}

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
    return Literal(v, datatype=XSD.date) if v else None


def lit_dec(v) -> Literal:
    return Literal(str(v), datatype=XSD.decimal) if v is not None else None


def lit_bool(v: bool | None) -> Literal:
    return Literal(v, datatype=XSD.boolean) if v is not None else None


def main() -> int:
    g = Graph()
    g.bind("eb", EB)
    g.parse(ONT, format="turtle")

    products = load("products.jsonl")
    customers = load("customers.jsonl")
    orders = load("orders.jsonl")
    payments = load("payments.jsonl")
    complaints = load("complaints.jsonl")

    node_uris = {}  # record_id -> URIRef

    def add_node(entity_uri, entity_class, row, props):
        node = entity_uri
        g.add((node, RDF.type, entity_class))
        g.add((node, EB.source_record_id, Literal(row["source_id"])))
        g.add((node, EB.id, Literal(row["source_id"])))
        for prop_name, converter in props:
            val = row.get(prop_name)
            if val is None or val == "":
                continue
            pred = EB[FIELD_TO_PROP.get(prop_name, prop_name)]
            if prop_name == "amount" or prop_name == "price":
                lit = lit_dec(val)
            elif "date" in prop_name:
                lit = lit_date(val)
            elif prop_name == "at_risk":
                lit = lit_bool(val)
            else:
                lit = Literal(str(val))
            g.add((node, pred, lit))

    def edge(source, predicate, target, src_id):
        g.add((source, predicate, target))
        stmt = BNode()
        g.add((stmt, RDF.type, RDF.Statement))
        g.add((stmt, RDF.subject, source))
        g.add((stmt, RDF.predicate, predicate))
        g.add((stmt, RDF.object, target))
        g.add((stmt, EB.source_record_id, Literal(src_id)))

    # --- products ---
    for row in products:
        rid = row["product_id"]
        node_uris[rid] = URIRef(EB_NS + rid)
        add_node(node_uris[rid], EB.Product, {**row, "source_id": rid}, [
            ("name", None), ("category", None), ("price", None),
        ])

    # --- customers ---
    for row in customers:
        rid = row["customer_id"]
        node_uris[rid] = URIRef(EB_NS + rid)
        add_node(node_uris[rid], EB.Customer, {**row, "source_id": rid}, [
            ("name", None), ("region", None), ("signup_date", None), ("at_risk", None),
        ])

    # --- orders ---
    order_row = {}
    for row in orders:
        rid = row["order_id"]
        node_uris[rid] = URIRef(EB_NS + rid)
        add_node(node_uris[rid], EB.Order, {**row, "source_id": rid}, [
            ("order_date", None), ("amount", None), ("status", None),
            ("valid_from", None), ("valid_to", None),
            ("previous_status", None), ("status_changed_on", None),
        ])
        order_row[rid] = row

    # --- payments ---
    pay_by_order = {}
    for row in payments:
        rid = row["payment_id"]
        node_uris[rid] = URIRef(EB_NS + rid)
        add_node(node_uris[rid], EB.Payment, {**row, "source_id": rid}, [
            ("amount", None), ("status", None), ("due_date", None), ("paid_date", None),
            ("valid_from", None), ("valid_to", None),
            ("previous_status", None), ("status_changed_on", None),
        ])
        pay_by_order[row["order_id"]] = row

    # --- complaints ---
    complaint_row = {}
    for row in complaints:
        rid = row["complaint_id"]
        node_uris[rid] = URIRef(EB_NS + rid)
        add_node(node_uris[rid], EB.Complaint, {**row, "source_id": rid}, [
            ("filed_date", None), ("category", None), ("free_text_description", None),
        ])
        complaint_row[rid] = row

    # --- edges: orders ---
    for row in orders:
        oid = row["order_id"]
        cid = row["customer_id"]
        pid = row["product_id"]
        if cid in node_uris and oid in node_uris:
            edge(node_uris[cid], EB.placedOrder, node_uris[oid], row["source_id"] if "source_id" in row else oid)
            edge(node_uris[oid], EB.orderPlacedBy, node_uris[cid], row.get("source_id", oid))
        if oid in node_uris and pid in node_uris:
            edge(node_uris[oid], EB.forProduct, node_uris[pid], row.get("source_id", oid))
            edge(node_uris[pid], EB.productOrderedIn, node_uris[oid], row.get("source_id", oid))

    # --- edges: payments ---
    for row in payments:
        pid = row["payment_id"]
        oid = row["order_id"]
        if oid in node_uris and pid in node_uris:
            edge(node_uris[oid], EB.hasPayment, node_uris[pid], row.get("source_id", oid))
            edge(node_uris[pid], EB.paymentForOrder, node_uris[oid], row.get("source_id", oid))

    # --- edges: complaints ---
    for row in complaints:
        comp_id = row["complaint_id"]
        cid = row["customer_id"]
        oid = row["order_id"]
        if cid in node_uris and comp_id in node_uris:
            edge(node_uris[cid], EB.filedComplaint, node_uris[comp_id], row.get("source_id", cid))
            edge(node_uris[comp_id], EB.complaintFiledBy, node_uris[cid], row.get("source_id", comp_id))
        if comp_id in node_uris and oid in node_uris:
            edge(node_uris[comp_id], EB.aboutOrder, node_uris[oid], row.get("source_id", oid))
            edge(node_uris[oid], EB.orderComplainedAbout, node_uris[comp_id], row.get("source_id", oid))

    # --- serialize ---
    GRAPH_DIR.mkdir(parents=True, exist_ok=True)
    g.serialize(OUT_TTL, format="turtle")
    print(f"wrote {OUT_TTL} — {len(g)} triples")
    return 0


if __name__ == "__main__":
    sys.exit(main())