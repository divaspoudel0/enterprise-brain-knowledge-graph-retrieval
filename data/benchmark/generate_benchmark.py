#!/usr/bin/env python3
"""S5 — benchmark generation (DATA_PIPELINE.md §5).

Generates benchmark QA pairs with ground truth derived directly from the data rows
(which the S3 graph mirrors 1:1 — verify_graph.py proved the round-trip), never from
an LLM's answer. 1-hop questions are direct lookups; 2/3-hop questions are
template-based relation-sequence walks anchored on the KNOWN PLANTED PATTERNS (the
guaranteed positives from planted_patterns.json) plus generic walks.

Every question records, for evaluation (S9) and the hybrid system (S7):
  qid, template_id, hops, pattern, question, answer, answer_type, answer_ids,
  evidence_source_record_ids, query_entities.

Sampling is seeded (random.Random(42)) so the benchmark is stable. Output:
  data/benchmark/benchmark_v1.jsonl  (frozen — never regenerate once S9 has started)

Usage:  uv run python data/benchmark/generate_benchmark.py
"""
from __future__ import annotations

import json
import random
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
RAW = HERE / "raw"
OUT_DIR = HERE / "benchmark"
OUT = OUT_DIR / "benchmark_v1.jsonl"

SEED = 42
Q = "Q"
questions = []


def load(name: str) -> list[dict]:
    return [json.loads(line) for line in (RAW / name).open(encoding="utf-8")]


def add(template_id: str, hops: int, pattern: str, question: str, answer: str,
        answer_type: str, evidence: list[str], query_entities: list[str], answer_ids: list[str] | None = None) -> None:
    questions.append({
        "qid": f"Q{len(questions) + 1:04d}",
        "template_id": template_id,
        "hops": hops,
        "pattern": pattern,
        "question": question,
        "answer": answer,
        "answer_type": answer_type,
        "answer_ids": answer_ids or [],
        "evidence_source_record_ids": sorted(set(evidence)),
        "query_entities": sorted(set(query_entities)),
    })


def main() -> int:
    products = load("products.jsonl")
    customers = load("customers.jsonl")
    orders = load("orders.jsonl")
    payments = load("payments.jsonl")
    complaints = load("complaints.jsonl")
    manifest = json.loads((RAW / "planted_patterns.json").read_text(encoding="utf-8"))
    pat = manifest["patterns"]

    prod_by_id = {p["product_id"]: p for p in products}
    cust_by_id = {c["customer_id"]: c for c in customers}
    order_by_id = {o["order_id"]: o for o in orders}
    pay_by_order = {p["order_id"]: p for p in payments}
    comp_by_id = {c["complaint_id"]: c for c in complaints}

    rng = random.Random(SEED)

    # ---------------- 1-hop: direct lookups ----------------
    def one(kind, entity, hops=1):
        template_id = f"1hop_{kind}"
        if kind == "order_status":
            o = order_by_id[entity]
            add(template_id, hops, "generic", f"What is the status of order {entity}?",
                o["status"], "status", [entity], [entity])
        elif kind == "order_amount":
            o = order_by_id[entity]
            add(template_id, hops, "generic", f"What is the amount of order {entity}?",
                str(o["amount"]), "amount", [entity], [entity])
        elif kind == "product_price":
            p = prod_by_id[entity]
            add(template_id, hops, "generic", f"What is the price of product {entity} ({p['name']})?",
                str(p["price"]), "amount", [entity], [entity])
        elif kind == "product_category":
            p = prod_by_id[entity]
            add(template_id, hops, "generic", f"What is the category of product {entity}?",
                p["category"], "category", [entity], [entity])
        elif kind == "customer_region":
            c = cust_by_id[entity]
            add(template_id, hops, "generic", f"Which region is customer {entity} from?",
                c["region"], "region", [entity], [entity])
        elif kind == "customer_signup":
            c = cust_by_id[entity]
            add(template_id, hops, "generic", f"When did customer {entity} sign up?",
                c["signup_date"], "date", [entity], [entity])
        elif kind == "payment_status":
            pay = pay_by_order[entity]
            add(template_id, hops, "generic", f"What is the payment status for order {entity}?",
                pay["status"], "status", [pay["payment_id"], entity], [entity])
        elif kind == "payment_due":
            pay = pay_by_order[entity]
            add(template_id, hops, "generic", f"When is the payment for order {entity} due?",
                pay["due_date"], "date", [pay["payment_id"], entity], [entity])
        elif kind == "complaint_category":
            c = comp_by_id[entity]
            add(template_id, hops, "generic", f"What is the category of complaint {entity}?",
                c["category"], "category", [entity], [entity])
        elif kind == "complaint_filed":
            c = comp_by_id[entity]
            add(template_id, hops, "generic", f"When was complaint {entity} filed?",
                c["filed_date"], "date", [entity], [entity])
        elif kind == "complaint_about_order":
            c = comp_by_id[entity]
            add(template_id, hops, "generic", f"Which order is complaint {entity} about?",
                c["order_id"], "entity_id", [entity, c["order_id"]], [entity], [c["order_id"]])
        elif kind == "order_product":
            o = order_by_id[entity]
            add(template_id, hops, "generic", f"What product was ordered in order {entity}?",
                prod_by_id[o["product_id"]]["name"], "entity_name",
                [entity, o["product_id"]], [entity], [o["product_id"]])

    for kind in ["order_status", "order_amount", "product_price", "product_category",
                 "customer_region", "customer_signup", "payment_status", "payment_due",
                 "complaint_category", "complaint_filed", "complaint_about_order", "order_product"]:
        pool = (list(order_by_id) if kind.startswith("order") and "complaint" not in kind
                else list(prod_by_id) if kind.startswith("product")
                else list(cust_by_id) if kind.startswith("customer")
                else list(comp_by_id) if kind.startswith("complaint")
                else list(pay_by_order))
        for entity in rng.sample(pool, 30):
            one(kind, entity)

    # ---------------- 2/3-hop: planted-pattern member walks ----------------
    # Single-answer templates: a member whose pattern matches MORE than once would
    # make the question ambiguous, so those members are excluded (they still appear
    # in the aggregate question, which answers with the full set).
    for cid in pat["P2"]["customers"]:  # 2-hop: c -placed-> o -for-> p (Electronics, Q2 2025)
        qo = [o for o in orders if o["customer_id"] == cid and
              date(2025, 4, 1) <= date.fromisoformat(o["order_date"]) <= date(2025, 6, 30) and
              prod_by_id[o["product_id"]]["category"] == "Electronics"]
        if len(qo) != 1:
            continue
        pname = prod_by_id[qo[0]["product_id"]]["name"]
        add("p2_product_of_order", 2, "P2",
            f"Which Electronics product did customer {cid} order in Q2 2025?",
            pname, "entity_name", [qo[0]["order_id"], qo[0]["product_id"], cid], [cid],
            [qo[0]["product_id"]])
    for cid in pat["P3"]["customers"]:  # 2-hop: c -filed-> comp -about-> o (billing, completed, Q3)
        qc = [c for c in complaints if c["customer_id"] == cid and c["category"] == "billing" and
              order_by_id[c["order_id"]]["status"] == "completed" and
              date(2025, 7, 1) <= date.fromisoformat(order_by_id[c["order_id"]]["order_date"]) <= date(2025, 9, 30)]
        if len(qc) != 1:
            continue
        odate = order_by_id[qc[0]["order_id"]]["order_date"]
        add("p3_order_date_of_complaint", 2, "P3",
            f"What is the order date of the completed order that customer {cid}'s billing complaint is about?",
            odate, "date", [qc[0]["order_id"], qc[0]["complaint_id"], cid], [cid])
    for cid in pat["P1"]["customers"]:  # 3-hop: c -filed-> comp -about-> o -has-> pay (overdue, Q1)
        qc = [c for c in complaints if c["customer_id"] == cid and
              date(2025, 1, 1) <= date.fromisoformat(c["filed_date"]) <= date(2025, 3, 31)]
        if len(qc) != 1:
            continue
        pay = pay_by_order[qc[0]["order_id"]]
        add("p1_payment_due_of_complaint", 3, "P1",
            f"Customer {cid} filed a complaint in Q1 2025 about an order with an overdue payment "
            "due in Q1 2025. What is the due date of that payment?",
            pay["due_date"], "date", [pay["payment_id"], qc[0]["order_id"], qc[0]["complaint_id"], cid], [cid])
    for cid in pat["P5"]["customers"]:  # 3-hop: c -filed-> comp -about-> o -for-> p (Home & Kitchen, Q4)
        qc = [c for c in complaints if c["customer_id"] == cid and
              date(2025, 10, 1) <= date.fromisoformat(c["filed_date"]) <= date(2025, 12, 31)]
        if len(qc) != 1:
            continue
        pname = prod_by_id[order_by_id[qc[0]["order_id"]]["product_id"]]["name"]
        add("p5_product_of_complaint", 3, "P5",
            f"Which Home & Kitchen product did customer {cid} order in the order they filed a "
            "complaint about in Q4 2025?",
            pname, "entity_name", [qc[0]["order_id"], order_by_id[qc[0]["order_id"]]["product_id"],
                                   qc[0]["complaint_id"], cid], [cid],
            [order_by_id[qc[0]["order_id"]]["product_id"]])

    # ---------------- aggregate pattern questions ----------------
    def agg_evidence(members) -> list[str]:
        ev = []
        for o in orders:
            if o["customer_id"] in members.get("customers", []):
                ev += [o["order_id"], o["product_id"], pay_by_order[o["order_id"]]["payment_id"]]
        for comp in complaints:
            if comp["customer_id"] in members.get("customers", []):
                ev.append(comp["complaint_id"])
        return sorted(set(ev))

    def agg(pattern, hops, question, base, pred):
        ids = sorted({x["customer_id"] for x in base if pred(x)})
        add(f"{pattern}_aggregate", hops, pattern, question, ", ".join(ids),
            "list:entity_id", agg_evidence(pat[pattern]), [])

    agg("P1", 3,
        "Which customers filed a complaint in Q1 2025 about an order with an overdue payment due in Q1 2025?",
        complaints,
        lambda c: (date(2025, 1, 1) <= date.fromisoformat(c["filed_date"]) <= date(2025, 3, 31)
                   and pay_by_order[c["order_id"]]["status"] == "overdue"
                   and date(2025, 1, 1) <= date.fromisoformat(pay_by_order[c["order_id"]]["due_date"]) <= date(2025, 3, 31)))
    agg("P2", 2,
        "Which customers placed an order for an Electronics product in Q2 2025?",
        customers,
        lambda c: any(date(2025, 4, 1) <= date.fromisoformat(o["order_date"]) <= date(2025, 6, 30)
                      and prod_by_id[o["product_id"]]["category"] == "Electronics"
                      for o in orders if o["customer_id"] == c["customer_id"]))
    agg("P3", 2,
        "Which customers filed a billing complaint about a completed order placed in Q3 2025?",
        complaints,
        lambda c: (c["category"] == "billing" and order_by_id[c["order_id"]]["status"] == "completed"
                   and date(2025, 7, 1) <= date.fromisoformat(order_by_id[c["order_id"]]["order_date"]) <= date(2025, 9, 30)))
    agg("P5", 3,
        "Which customers filed a complaint in Q4 2025 about an order for a Home & Kitchen product?",
        complaints,
        lambda c: (date(2025, 10, 1) <= date.fromisoformat(c["filed_date"]) <= date(2025, 12, 31)
                   and prod_by_id[order_by_id[c["order_id"]]["product_id"]]["category"] == "Home & Kitchen"))

    # ---------------- generic 2-hop / 3-hop walks ----------------
    cust_with_orders = [c for c in customers if any(o["customer_id"] == c["customer_id"] for o in orders)]
    for cid in rng.sample([c["customer_id"] for c in cust_with_orders], 30):
        oid = rng.choice([o["order_id"] for o in orders if o["customer_id"] == cid])
        pname = prod_by_id[order_by_id[oid]["product_id"]]["name"]
        add("generic_product_of_customer_order", 2, "generic",
            f"What product did customer {cid} order in order {oid}?",
            pname, "entity_name", [oid, order_by_id[oid]["product_id"], cid], [cid, oid],
            [order_by_id[oid]["product_id"]])
    for comp in rng.sample(complaints, 20):
        pay = pay_by_order[comp["order_id"]]
        add("generic_complaint_author_and_payment", 3, "generic",
            f"Which customer filed complaint {comp['complaint_id']} and what is the payment status "
            f"for the order it concerns?",
            f"{comp['customer_id']}; {pay['status']}", "pair",
            [comp["complaint_id"], comp["customer_id"], comp["order_id"], pay["payment_id"]],
            [comp["complaint_id"]])

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        for q in questions:
            fh.write(json.dumps(q, ensure_ascii=False) + "\n")

    from collections import Counter
    by_hop = Counter(q["hops"] for q in questions)
    by_tpl = Counter(q["template_id"] for q in questions)
    print(f"questions: {len(questions)}  by hops: {dict(sorted(by_hop.items()))}")
    print("by template:", dict(sorted(by_tpl.items())))
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
