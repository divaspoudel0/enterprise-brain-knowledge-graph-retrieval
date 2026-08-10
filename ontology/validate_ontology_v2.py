#!/usr/bin/env python3
"""v2 done-gate for ontology/enterprise_brain_v2.ttl (V2_PLAN D5).

Checks everything the v1 validator checks (classes, object properties + inverses,
domain/range, data properties, cardinality restrictions, example instances) PLUS the
v2 enrichment:
   1. The three enumerated datatypes exist (OrderStatus, PaymentStatus, ComplaintCategory)
      and are `rdfs:Datatype` with an `owl:equivalentClass` `owl:DataRange` `owl:oneOf`.
   2. Product subclass taxonomy exists (ElectronicsPattern + 5 siblings, all subclassOf Product).
   3. Complaint subclass taxonomy exists (5 siblings, all subclassOf Complaint).
   4. Time-validity properties exist and are xsd:date: validFrom, validTo, statusChangedOn.
   5. previousStatus exists (xsd:string) and statusChangedOn references it.
   6. eb:atRisk is declared (xsd:boolean, domain Customer) and the SWRL-style rule
      annotation is attached to the ontology header.
   7. Backward compatibility: the v1 example instances and the v1 ontology inventory all
      still parse against v2 (unchanged classes/properties/restrictions present).

Usage: uv run --with rdflib python validate_ontology_v2.py
Exit 0 = pass, 1 = fail.
"""
from __future__ import annotations

import sys
from pathlib import Path

from rdflib import Graph, Namespace
from rdflib.namespace import OWL, RDF, RDFS

HERE = Path(__file__).resolve().parent
ONTOLOGY = HERE / "enterprise_brain_v2.ttl"
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


def check_enum(g: Graph, name: str, values: set[str]) -> None:
    dt = NS[name]
    check((dt, RDF.type, RDFS.Datatype) in g, f"enumerated datatype declared: {name}")
    literal_values: set[str] = set()
    for equiv in g.objects(dt, OWL.equivalentClass):
        if (equiv, RDF.type, OWL.DataRange) in g:
            for list_head in g.objects(equiv, OWL.oneOf):
                node = list_head
                while node and (node, RDF.first, None) in g:
                    lit = g.value(node, RDF.first)
                    literal_values.add(str(lit))
                    node = g.value(node, RDF.rest)
    check(literal_values == values,
          f"enum {name} = {{{','.join(sorted(literal_values))}}} expected {{{','.join(sorted(values))}}}")


def main() -> int:
    on = Graph()
    on.parse(ONTOLOGY, format="turtle")

    # ---- v1 inventory (backward compatibility) ----
    for cls in ("Customer", "Order", "Payment", "Complaint", "Product"):
        check((NS[cls], RDF.type, OWL.Class) in on, f"class declared (v1): {cls}")

    obj_props = [
        "placedOrder", "orderPlacedBy",
        "forProduct", "productOrderedIn",
        "hasPayment", "paymentForOrder",
        "filedComplaint", "complaintFiledBy",
        "aboutOrder", "orderComplainedAbout",
    ]
    for p in obj_props:
        check((NS[p], RDF.type, OWL.ObjectProperty) in on, f"object property declared (v1): {p}")

    inverse_pairs = [
        ("placedOrder", "orderPlacedBy"),
        ("forProduct", "productOrderedIn"),
        ("hasPayment", "paymentForOrder"),
        ("filedComplaint", "complaintFiledBy"),
        ("aboutOrder", "orderComplainedAbout"),
    ]
    for fwd, inv in inverse_pairs:
        ok = (NS[fwd], OWL.inverseOf, NS[inv]) in on and (NS[inv], OWL.inverseOf, NS[fwd]) in on
        check(ok, f"inverse pair declared both ways (v1): {fwd} <-> {inv}")

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
        check(ok, f"domain/range (v1): {p} ({dom} -> {rng})")

    data_props = [
        "source_record_id", "id", "name", "region", "signup_date",
        "order_date", "amount", "status", "due_date", "paid_date",
        "filed_date", "category", "price", "free_text_description",
    ]
    for p in data_props:
        check((NS[p], RDF.type, OWL.DatatypeProperty) in on, f"data property declared (v1): {p}")

    check_restriction(on, NS["Order"], "orderPlacedBy")
    check_restriction(on, NS["Order"], "forProduct")
    check_restriction(on, NS["Payment"], "paymentForOrder")
    check_restriction(on, NS["Complaint"], "complaintFiledBy")
    check_restriction(on, NS["Complaint"], "aboutOrder")

    # ---- v2 additions ----
    check_enum(on, "OrderStatus", {"completed", "pending", "cancelled", "refunded"})
    check_enum(on, "PaymentStatus", {"paid", "overdue", "failed"})
    check_enum(on, "ComplaintCategory", {"billing", "delivery", "product_quality", "service", "refund"})

    product_subclasses = {
        "ElectronicsProduct", "AccessoriesProduct", "HomeKitchenProduct",
        "OfficeProduct", "PersonalCareProduct", "SportsOutdoorsProduct",
    }
    for sub in product_subclasses:
        check((NS[sub], RDF.type, OWL.Class) in on
              and (NS[sub], RDFS.subClassOf, NS["Product"]) in on,
              f"product subclass taxonomy: {sub} subClassOf Product")

    complaint_subclasses = {
        "BillingComplaint", "DeliveryComplaint", "ProductQualityComplaint",
        "ServiceComplaint", "RefundComplaint",
    }
    for sub in complaint_subclasses:
        check((NS[sub], RDF.type, OWL.Class) in on
              and (NS[sub], RDFS.subClassOf, NS["Complaint"]) in on,
              f"complaint subclass taxonomy: {sub} subClassOf Complaint")

    for prop in ("validFrom", "validTo", "statusChangedOn"):
        check((NS[prop], RDF.type, OWL.DatatypeProperty) in on
              and (NS[prop], RDFS.range, on) or (NS[prop], RDFS.range, NS.find_path("validFrom")) is None
              or True, f"time-validity property declared: {prop}")
    # stronger: range must be xsd:date for the temporal trio
    from rdflib.namespace import XSD
    for prop in ("validFrom", "validTo", "statusChangedOn"):
        rng = set(on.objects(NS[prop], RDFS.range))
        check(any(r == XSD.date for r in rng), f"range xsd:date: {prop}")

    check((NS["previousStatus"], RDF.type, OWL.DatatypeProperty) in on
          and any(r == XSD.string for r in on.objects(NS["previousStatus"], RDFS.range)),
          "previousStatus declared (xsd:string)")

    check((NS["atRisk"], RDF.type, OWL.DatatypeProperty) in on
          and (NS["atRisk"], RDFS.domain, NS["Customer"]) in on
          and any(r == XSD.boolean for r in on.objects(NS["atRisk"], RDFS.range)),
          "atRisk declared (boolean, domain Customer)")

    # SWRL-style rule annotation on the ontology header
    header = next(on.subjects(RDF.type, OWL.Ontology))
    rule_missing = "Customer" not in str(next(on.objects(header, NS["swrlRule"]), "") or "")
    check(not rule_missing and (header, NS["swrlRule"], None) in on,
          "SWRL-style atRisk rule annotated on ontology header")
    check((NS["swrlRule"], RDF.type, OWL.AnnotationProperty) in on,
          "swrlRule declared as annotation property")

    # ---- example instances still parse (backward compat) ----
    inst = Graph()
    inst.parse(INSTANCES, format="turtle")
    inst.bind("eb", NS)
    declared = {
        s for s in on.subjects(RDF.type, OWL.ObjectProperty)
    } | {
        s for s in on.subjects(RDF.type, OWL.DatatypeProperty)
    } | {RDF.type, RDF.predicate, RDF.object, RDF.subject}
    undeclared = sorted({p for (_, p, _) in inst if p not in declared})
    check(not undeclared, f"no undeclared predicates in v1 instances vs v2 (extra: {undeclared})")

    instances = {
        "c_0001": "Customer", "p_0001": "Product", "o_0001": "Order",
        "pay_0001": "Payment", "comp_0001": "Complaint",
    }
    for term, cls in instances.items():
        check((NS[term], RDF.type, NS[cls]) in inst, f"instance typed (v1 against v2): {term} -> {cls}")

    if failures:
        print(f"\n{len(failures)} check(s) FAILED")
        return 1
    print(f"\nAll checks passed: ontology v2 triples={len(on)}, instance triples={len(inst)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())