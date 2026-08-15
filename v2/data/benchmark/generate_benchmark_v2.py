#!/usr/bin/env python3
"""Phase C — benchmark v2 generation (V2_PLAN.md §5).

Three testbeds over the v2 graph / raw data, ground truth derived directly from data
rows (never from an LLM), matching DATA_PIPELINE.md §5 semantics:

  T1 multi-hop (~880)  — the v1 template family (1/2/3-hop lookups + planted
      patterns P1/P2/P3/P5 + generic walks), re-generated on the v2 graph with more
      instances.
  T2 temporal  (~300)  — as-of status questions over the validFrom/validTo /
      previous_status / status_changed_on annotations (D3), plus earliest/latest
      order and complaint-order comparisons.
  T3 answerability (~200) — unanswerable questions (entity absent / relation
      absent / pattern absent) whose only correct output is "I don't know" (D4).

Every question carries (V2_PLAN §5.2):
  qid, template_id, hops, pattern, question, answer, answer_type, answer_ids,
  is_answerable, evidence_source_record_ids, query_entities, provenance_path, split.

Split (V2_PLAN §5.4): train/val/test 70/10/20 assigned at generation (seeded),
stored per question. verify_benchmark_v2.py independently recomputes every
answerable ground truth via SPARQL over the v2 graph and proves every unanswerable
question has no answer in the graph.

Output: v2/data/benchmark/benchmark.jsonl  (freezes once Phase F evaluation starts).

Usage:  uv run python v2/data/benchmark/generate_benchmark_v2.py
"""
from __future__ import annotations

import json
import random
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
RAW = HERE / "raw"
OUT_DIR = HERE / "benchmark"
OUT = OUT_DIR / "benchmark.jsonl"

SEED = 42
questions: list[dict] = []


def load(name: str) -> list[dict]:
    return [json.loads(line) for line in (RAW / name).open(encoding="utf-8")]


def add(template_id: str, hops: int, pattern: str, question: str, answer: str,
        answer_type: str, evidence: list[str], query_entities: list[str],
        answer_ids: list[str] | None = None, is_answerable: bool = True,
        provenance_path: str = "") -> None:
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
        "is_answerable": is_answerable,
        "provenance_path": provenance_path,
        "split": "",
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

    # ================================================================ T1 multi-hop
    def one(kind, entity, hops=1):
        template_id = f"1hop_{kind}"
        if kind == "order_status":
            o = order_by_id[entity]
            add(template_id, hops, "generic", f"What is the status of order {entity}?",
                o["status"], "status", [entity], [entity], provenance_path="Order→status")
        elif kind == "order_amount":
            o = order_by_id[entity]
            add(template_id, hops, "generic", f"What is the amount of order {entity}?",
                str(o["amount"]), "amount", [entity], [entity], provenance_path="Order→amount")
        elif kind == "product_price":
            p = prod_by_id[entity]
            add(template_id, hops, "generic", f"What is the price of product {entity} ({p['name']})?",
                str(p["price"]), "amount", [entity], [entity], provenance_path="Product→price")
        elif kind == "product_category":
            p = prod_by_id[entity]
            add(template_id, hops, "generic", f"What is the category of product {entity}?",
                p["category"], "category", [entity], [entity], provenance_path="Product→category")
        elif kind == "customer_region":
            c = cust_by_id[entity]
            add(template_id, hops, "generic", f"Which region is customer {entity} from?",
                c["region"], "region", [entity], [entity], provenance_path="Customer→region")
        elif kind == "customer_signup":
            c = cust_by_id[entity]
            add(template_id, hops, "generic", f"When did customer {entity} sign up?",
                c["signup_date"], "date", [entity], [entity], provenance_path="Customer→signup_date")
        elif kind == "payment_status":
            pay = pay_by_order[entity]
            add(template_id, hops, "generic", f"What is the payment status for order {entity}?",
                pay["status"], "status", [pay["payment_id"], entity], [entity],
                provenance_path="Order→Payment→status")
        elif kind == "payment_due":
            pay = pay_by_order[entity]
            add(template_id, hops, "generic", f"When is the payment for order {entity} due?",
                pay["due_date"], "date", [pay["payment_id"], entity], [entity],
                provenance_path="Order→Payment→due_date")
        elif kind == "complaint_category":
            c = comp_by_id[entity]
            add(template_id, hops, "generic", f"What is the category of complaint {entity}?",
                c["category"], "category", [entity], [entity], provenance_path="Complaint→category")
        elif kind == "complaint_filed":
            c = comp_by_id[entity]
            add(template_id, hops, "generic", f"When was complaint {entity} filed?",
                c["filed_date"], "date", [entity], [entity], provenance_path="Complaint→filed_date")
        elif kind == "complaint_about_order":
            c = comp_by_id[entity]
            add(template_id, hops, "generic", f"Which order is complaint {entity} about?",
                c["order_id"], "entity_id", [entity, c["order_id"]], [entity], [c["order_id"]],
                provenance_path="Complaint→Order")
        elif kind == "order_product":
            o = order_by_id[entity]
            add(template_id, hops, "generic", f"What product was ordered in order {entity}?",
                prod_by_id[o["product_id"]]["name"], "entity_name",
                [entity, o["product_id"]], [entity], [o["product_id"]],
                provenance_path="Order→Product")

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

    # Planted-pattern member walks (single-answer only — see v1 note on ambiguity).
    for cid in pat["P2"]["customers"]:
        qo = [o for o in orders if o["customer_id"] == cid and
              date(2025, 4, 1) <= date.fromisoformat(o["order_date"]) <= date(2025, 6, 30) and
              prod_by_id[o["product_id"]]["category"] == "Electronics"]
        if len(qo) != 1:
            continue
        pname = prod_by_id[qo[0]["product_id"]]["name"]
        add("p2_product_of_order", 2, "P2",
            f"Which Electronics product did customer {cid} order in Q2 2025?",
            pname, "entity_name", [qo[0]["order_id"], qo[0]["product_id"], cid], [cid],
            [qo[0]["product_id"]], provenance_path="Customer→Order→Product")
    for cid in pat["P3"]["customers"]:
        qc = [c for c in complaints if c["customer_id"] == cid and c["category"] == "billing" and
              order_by_id[c["order_id"]]["status"] == "completed" and
              date(2025, 7, 1) <= date.fromisoformat(order_by_id[c["order_id"]]["order_date"]) <= date(2025, 9, 30)]
        if len(qc) != 1:
            continue
        odate = order_by_id[qc[0]["order_id"]]["order_date"]
        add("p3_order_date_of_complaint", 2, "P3",
            f"What is the order date of the completed order that customer {cid}'s billing complaint is about?",
            odate, "date", [qc[0]["order_id"], qc[0]["complaint_id"], cid], [cid],
            provenance_path="Customer→Complaint→Order")
    for cid in pat["P1"]["customers"]:
        qc = [c for c in complaints if c["customer_id"] == cid and
              date(2025, 1, 1) <= date.fromisoformat(c["filed_date"]) <= date(2025, 3, 31)]
        if len(qc) != 1:
            continue
        pay = pay_by_order[qc[0]["order_id"]]
        add("p1_payment_due_of_complaint", 3, "P1",
            f"Customer {cid} filed a complaint in Q1 2025 about an order with an overdue payment "
            "due in Q1 2025. What is the due date of that payment?",
            pay["due_date"], "date", [pay["payment_id"], qc[0]["order_id"], qc[0]["complaint_id"], cid], [cid],
            provenance_path="Customer→Complaint→Order→Payment")
    for cid in pat["P5"]["customers"]:
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
            [order_by_id[qc[0]["order_id"]]["product_id"]],
            provenance_path="Customer→Complaint→Order→Product")

    # Aggregate pattern questions.
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
            "list:entity_id", agg_evidence(pat[pattern]), [],
            provenance_path="Customer")

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

    # Generic 2/3-hop walks.
    cust_with_orders = [c for c in customers if any(o["customer_id"] == c["customer_id"] for o in orders)]
    for cid in rng.sample([c["customer_id"] for c in cust_with_orders], 30):
        oid = rng.choice([o["order_id"] for o in orders if o["customer_id"] == cid])
        pname = prod_by_id[order_by_id[oid]["product_id"]]["name"]
        add("generic_product_of_customer_order", 2, "generic",
            f"What product did customer {cid} order in order {oid}?",
            pname, "entity_name", [oid, order_by_id[oid]["product_id"], cid], [cid, oid],
            [order_by_id[oid]["product_id"]], provenance_path="Customer→Order→Product")
    for comp in rng.sample(complaints, 30):
        pay = pay_by_order[comp["order_id"]]
        add("generic_complaint_author_and_payment", 3, "generic",
            f"Which customer filed complaint {comp['complaint_id']} and what is the payment status "
            f"for the order it concerns?",
            f"{comp['customer_id']}; {pay['status']}", "pair",
            [comp["complaint_id"], comp["customer_id"], comp["order_id"], pay["payment_id"]],
            [comp["complaint_id"]], provenance_path="Complaint→Customer, Complaint→Order→Payment")

    # ================================================================ T2 temporal
    def add_t2(template_id, question, answer, answer_type, evidence, query_entities,
               answer_ids=None, provenance_path=""):
        add(template_id, 2, "temporal", question, answer, answer_type, evidence,
            query_entities, answer_ids, provenance_path=provenance_path)

    # as-of order status: valid window [valid_from, valid_to); status changed on status_changed_on
    changed_orders = [o for o in orders if o.get("previous_status")]
    for o in rng.sample(changed_orders, 60):
        vf = date.fromisoformat(o["valid_from"])
        vt = date.fromisoformat(o["valid_to"])
        asof = (vf + timedelta(days=(vt - vf).days // 2)).isoformat()
        add_t2("t2_order_status_asof",
               f"Order {o['order_id']} changed status from {o['previous_status']} to {o['status']} on "
               f"{o['status_changed_on']}. What was the status of order {o['order_id']} on {asof}?",
               o["previous_status"], "status", [o["order_id"]], [o["order_id"]],
               provenance_path="Order→validFrom/validTo→previous_status")

    # as-of payment status
    changed_payments = [p for p in payments if p.get("previous_status")]
    for p in rng.sample(changed_payments, 60):
        vf = date.fromisoformat(p["valid_from"])
        vt = date.fromisoformat(p["valid_to"])
        asof = (vf + timedelta(days=(vt - vf).days // 2)).isoformat()
        add_t2("t2_payment_status_asof",
               f"The payment for order {p['order_id']} changed status from {p['previous_status']} to "
               f"{p['status']} on {p['status_changed_on']}. What was the payment status for order "
               f"{p['order_id']} on {asof}?",
               p["previous_status"], "status", [p["payment_id"], p["order_id"]], [p["order_id"]],
               provenance_path="Order→Payment→validFrom/validTo→previous_status")

    # status-change date (current status started on status_changed_on)
    for o in rng.sample(changed_orders, 40):
        add_t2("t2_order_status_changed_on",
               f"Order {o['order_id']} was previously {o['previous_status']}. On what date did it "
               f"change to {o['status']}?",
               o["status_changed_on"], "date", [o["order_id"]], [o["order_id"]],
               provenance_path="Order→statusChangedOn")
    for p in rng.sample(changed_payments, 40):
        add_t2("t2_payment_status_changed_on",
               f"The payment for order {p['order_id']} was previously {p['previous_status']}. On what "
               f"date did it change to {p['status']}?",
               p["status_changed_on"], "date", [p["payment_id"], p["order_id"]], [p["order_id"]],
               provenance_path="Order→Payment→statusChangedOn")

    # complaint before/after ordering
    comp_pairs = rng.sample(complaints, 60)
    for c in comp_pairs:
        other = comp_by_id[rng.choice([x["complaint_id"] for x in complaints
                                       if x["filed_date"] != c["filed_date"]])]
        earlier, later = sorted([c, other], key=lambda x: x["filed_date"])
        add_t2("t2_complaint_earlier",
               f"Which complaint was filed earlier: {earlier['complaint_id']} or {later['complaint_id']}?",
               earlier["complaint_id"], "entity_id",
               [earlier["complaint_id"], later["complaint_id"]],
               [earlier["complaint_id"], later["complaint_id"]], [earlier["complaint_id"]],
               provenance_path="Complaint→filed_date (compare)")

    # earliest / latest order per customer (multi-order customers only)
    order_dates = {}
    for o in orders:
        order_dates.setdefault(o["customer_id"], []).append((o["order_date"], o["order_id"]))
    multi = [c for c, v in order_dates.items() if len(v) >= 2]
    for cid in rng.sample(multi, 20):
        early = min(order_dates[cid])
        add_t2("t2_earliest_order",
               f"What is the earliest order placed by customer {cid}?",
               early[1], "entity_id", [early[1], cid], [cid], [early[1]],
               provenance_path="Customer→Order→order_date (min)")
    for cid in rng.sample(multi, 20):
        late = max(order_dates[cid])
        add_t2("t2_latest_order",
               f"What is the latest order placed by customer {cid}?",
               late[1], "entity_id", [late[1], cid], [cid], [late[1]],
               provenance_path="Customer→Order→order_date (max)")

    # ================================================================ T3 answerability
    def add_na(template_id, hops, question, evidence, query_entities, provenance_path=""):
        add(template_id, hops, "unanswerable", question, "I don't know", "unknown",
            evidence, query_entities, [], is_answerable=False, provenance_path=provenance_path)

    # entity absent — plausible but nonexistent ids
    for _ in range(20):
        add_na("t3_entity_absent_order", 1,
               f"What is the status of order o_{rng.randint(10000, 99999)}?", [], [],
               "Order→status (no such order)")
    for _ in range(20):
        add_na("t3_entity_absent_product", 1,
               f"What is the price of product p_{rng.randint(200, 999)}?", [], [],
               "Product→price (no such product)")
    for _ in range(20):
        add_na("t3_entity_absent_customer", 1,
               f"Which region is customer c_{rng.randint(5000, 9999)} from?", [], [],
               "Customer→region (no such customer)")
    for _ in range(20):
        add_na("t3_entity_absent_complaint", 1,
               f"What is the category of complaint comp_{rng.randint(10000, 99999)}?", [], [],
               "Complaint→category (no such complaint)")
    for _ in range(20):
        add_na("t3_entity_absent_payment", 1,
               f"What is the payment status for order o_{rng.randint(10000, 99999)}?", [], [],
               "Order→Payment→status (no such order)")

    # relation absent — the order exists but does not belong to that customer
    sample_pairs = 0
    while sample_pairs < 50:
        o = rng.choice(orders)
        other = rng.choice(customers)
        if other["customer_id"] != o["customer_id"]:
            add_na("t3_relation_absent_customer_order", 2,
                   f"What product did customer {other['customer_id']} order in order {o['order_id']}?",
                   [o["order_id"], o["product_id"]], [other["customer_id"], o["order_id"]],
                   "Customer→Order→Product (order not placed by that customer)")
            sample_pairs += 1

    # pattern absent — customer has no Q2-2025 Electronics order
    non_p2 = [c for c in customers if not any(
        date(2025, 4, 1) <= date.fromisoformat(o["order_date"]) <= date(2025, 6, 30) and
        prod_by_id[o["product_id"]]["category"] == "Electronics"
        for o in orders if o["customer_id"] == c["customer_id"])]
    for cid in [c["customer_id"] for c in rng.sample(non_p2, 50)]:
        add_na("t3_pattern_absent_electronics_q2", 2,
               f"Which Electronics product did customer {cid} order in Q2 2025?",
               [], [cid], "Customer→Order→Product (no Electronics order in Q2 2025)")

    # ================================================================ splits
    order_ids = list(range(len(questions)))
    rng.shuffle(order_ids)
    n_train = int(len(order_ids) * 0.7)
    n_val = int(len(order_ids) * 0.1)
    for rank, qi in enumerate(order_ids):
        split = "train" if rank < n_train else ("val" if rank < n_train + n_val else "test")
        questions[qi]["split"] = split

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        for q in questions:
            fh.write(json.dumps(q, ensure_ascii=False) + "\n")

    by_testbed = Counter("T3" if not q["is_answerable"] else
                         ("T2" if q["template_id"].startswith("t2") else "T1") for q in questions)
    by_split = Counter(q["split"] for q in questions)
    by_hop = Counter(q["hops"] for q in questions)
    by_tpl = Counter(q["template_id"] for q in questions)
    print(f"questions: {len(questions)}  testbeds: {dict(sorted(by_testbed.items()))}")
    print(f"by hops: {dict(sorted(by_hop.items()))}   by split: {dict(sorted(by_split.items()))}")
    print("by template:", dict(sorted(by_tpl.items())))
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
