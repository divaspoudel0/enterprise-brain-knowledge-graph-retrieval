#!/usr/bin/env python3
"""S1 done-gate: verify v1/ontology/enterprise_brain.ttl encodes the full
DATA_PIPELINE.md section 1.1 inventory and that the example instances are
well-formed against it.

Checks (fails loudly, exit code 1, on any):
  1. All five entity classes are declared (Customer, Order, Payment,
     Complaint, Product).
  2. All ten object properties are declared and each of the five relationship
     pairs has owl:inverseOf declared on both sides.
  3. Declared domains/ranges of every object property match the schema.
  4. All fourteen data properties are declared.
  5. Cardinality-1 restrictions exist where the schema requires them
     (Order: placedBy/forProduct; Payment: forOrder; Complaint: filedBy/about).
  6. Example instances: every predicate used is declared in the ontology, each
     instance is typed, every instance carries source_record_id, and the
     planted 2-hop path Customer->Complaint->Order->Payment is present.

Usage: uv run --with rdflib python v1/ontology/validate_ontology.py
Exit 0 = pass, 1 = fail.
"""
from __future__ import annotations

import sys
from pathlib import Path

from rdflib import Graph, Literal, Namespace
from rdflib.namespace import OWL, RDF, RDFS

HERE = Path(__file__).resolve().parent
ONTOLOGY = HERE / "enterprise_brain.ttl"
INSTANCES = HERE / "example_instances.ttl"

NS = Namespace("https://github.com/divaspoudel0/enterprise-brain-knowledge-graph-retrieval/ontology#")

failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    if cond:
        print(f"PASS  {msg}")
    else:
        print(f"FAIL  {msg}")
        failures.append(msg)


def check_restriction(g: Graph, cls, prop: str) -> None:
    prop_iri = NS[prop]
    found = False
    for rest in g.objects(cls, RDFS.subClassOf):
        if (rest, RDF.type, OWL.Restriction) in g and (rest, OWL.onProperty, prop_iri) in g:
            for card in g.objects(rest, OWL.cardinality):
                if int(card) == 1:
                    found = True
    check(found, f"restriction: {cls.split('#')[-1]} has exactly-1 {prop}")


def main() -> int:
    on = Graph()
    on.parse(ONTOLOGY, format="turtle")

    for cls in ("Customer", "Order", "Payment", "Complaint", "Product"):
        check((NS[cls], RDF.type, OWL.Class) in on, f"class declared: {cls}")

    obj_props = [
        "placedOrder", "orderPlacedBy",
        "forProduct", "productOrderedIn",
        "hasPayment", "paymentForOrder",
        "filedComplaint", "complaintFiledBy",
        "aboutOrder", "orderComplainedAbout",
    ]
    for p in obj_props:
        check((NS[p], RDF.type, OWL.ObjectProperty) in on, f"object property declared: {p}")

    inverse_pairs = [
        ("placedOrder", "orderPlacedBy"),
        ("forProduct", "productOrderedIn"),
        ("hasPayment", "paymentForOrder"),
        ("filedComplaint", "complaintFiledBy"),
        ("aboutOrder", "orderComplainedAbout"),
    ]
    for fwd, inv in inverse_pairs:
        ok = (NS[fwd], OWL.inverseOf, NS[inv]) in on and (NS[inv], OWL.inverseOf, NS[fwd]) in on
        check(ok, f"inverse pair declared both ways: {fwd} <-> {inv}")

    domain_range = {
        "placedOrder": ("Customer", "Order"),
        "orderPlacedBy": ("Order", "Customer"),
        "forProduct": ("Order", "Product"),
        "productOrderedIn": ("Product", "Order"),
        "hasPayment": ("Order", "Payment"),
        "paymentForOrder": ("Payment", "Order"),
        "filedComplaint": ("Customer", "Complaint"),
        "complaintFiledBy": ("Complaint", "Customer"),
        "aboutOrder": ("Complaint", "Order"),
        "orderComplainedAbout": ("Order", "Complaint"),
    }
    for p, (dom, rng) in domain_range.items():
        ok = (NS[p], RDFS.domain, NS[dom]) in on and (NS[p], RDFS.range, NS[rng]) in on
        check(ok, f"domain/range: {p} ({dom} -> {rng})")

    data_props = [
        "source_record_id", "id", "name", "region", "signup_date",
        "order_date", "amount", "status", "due_date", "paid_date",
        "filed_date", "category", "price", "free_text_description",
    ]
    for p in data_props:
        check((NS[p], RDF.type, OWL.DatatypeProperty) in on, f"data property declared: {p}")

    check_restriction(on, NS["Order"], "orderPlacedBy")
    check_restriction(on, NS["Order"], "forProduct")
    check_restriction(on, NS["Payment"], "paymentForOrder")
    check_restriction(on, NS["Complaint"], "complaintFiledBy")
    check_restriction(on, NS["Complaint"], "aboutOrder")

    inst = Graph()
    inst.parse(INSTANCES, format="turtle")
    inst.bind("eb", NS)

    declared = {
        s for s in on.subjects(RDF.type, OWL.ObjectProperty)
    } | {
        s for s in on.subjects(RDF.type, OWL.DatatypeProperty)
    } | {RDF.type, RDF.predicate, RDF.object, RDF.subject}

    undeclared = sorted({p for (_, p, _) in inst if p not in declared})
    check(not undeclared, f"no undeclared predicates in instances (extra: {undeclared})")

    instances = {
        "c_0001": "Customer", "p_0001": "Product", "o_0001": "Order",
        "pay_0001": "Payment", "comp_0001": "Complaint",
    }
    for term, cls in instances.items():
        check((NS[term], RDF.type, NS[cls]) in inst, f"instance typed: {term} -> {cls}")
        check((NS[term], NS["source_record_id"], None) in inst, f"instance has source_record_id: {term}")

    path_checks = [
        ("2-hop: customer filed complaint", "c_0001", "filedComplaint", "comp_0001"),
        ("2-hop: complaint about order", "comp_0001", "aboutOrder", "o_0001"),
        ("2-hop: order has payment", "o_0001", "hasPayment", "pay_0001"),
        ("1-hop: order placed by customer", "o_0001", "orderPlacedBy", "c_0001"),
        ("1-hop: order for product", "o_0001", "forProduct", "p_0001"),
    ]
    for label, s, p, o in path_checks:
        check((NS[s], NS[p], NS[o]) in inst, f"path present: {label}")

    if failures:
        print(f"\n{len(failures)} check(s) FAILED")
        return 1
    print(f"\nAll checks passed: ontology triples={len(on)}, instance triples={len(inst)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
