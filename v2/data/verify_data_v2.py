#!/usr/bin/env python3
"""v2 data verification (V2_PLAN D5, DATA_PIPELINE §1.3).

Mirrors every data/verify_data.py check against data/raw/ (v2 tree), plus the v2 additions:
  1-6. Same referential integrity, uniqueness, required-fields, consistency,
       planted-pattern predicate + count checks as v1.
  7. atRisk derivation matches the SWRL rule: customer at_risk == true iff that
     customer filed a complaint about an order whose payment is overdue.
  8. Status-history temporal consistency on orders/payments:
       valid_from <= valid_to; status_changed_on within [valid_from, valid_to];
       previous_status stays in the correct enumerated set; changed entries carry
       both previous_status and status_changed_on.
  9. Enumerations hold: order status in {completed,pending,cancelled,refunded},
     payment status in {paid,overdue,failed}, complaint category in the 5 values.

Usage: uv run python v2/data/verify_data_v2.py
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"

ORDER_STATES = {"completed", "pending", "cancelled", "refunded"}
PAYMENT_STATES = {"paid", "overdue", "failed"}
CATEGORIES = {"billing", "delivery", "product_quality", "service", "refund"}

failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    if cond:
        print(f"PASS  {msg}")
    else:
        print(f"FAIL  {msg}")
        failures.append(msg)


def load(name: str) -> list[dict]:
    return [json.loads(line) for line in (RAW / name).open(encoding="utf-8")]


def main() -> int:
    products = load("products.jsonl")
    customers = load("customers.jsonl")
    orders = load("orders.jsonl")
    payments = load("payments.jsonl")
    complaints = load("complaints.jsonl")

    prod_by_id = {p["product_id"]: p for p in products}
    cust_by_id = {c["customer_id"]: c for c in customers}
    order_by_id = {o["order_id"]: o for o in orders}
    pay_by_order = {p["order_id"]: p for p in payments}

    # 1. referential integrity
    check(all(o["customer_id"] in cust_by_id for o in orders), "FK: orders -> customers")
    check(all(o["product_id"] in prod_by_id for o in orders), "FK: orders -> products")
    check(all(p["order_id"] in order_by_id for p in payments), "FK: payments -> orders")
    check(all(c["order_id"] in order_by_id for c in complaints), "FK: complaints -> orders")
    check(all(c["customer_id"] in cust_by_id for c in complaints), "FK: complaints -> customers")

    # 2. uniqueness
    for name, rows in [("products", products), ("customers", customers),
                       ("orders", orders), ("payments", payments), ("complaints", complaints)]:
        key = "payment_id" if name == "payments" else f"{name[:-1]}_id"
        ids = [r[key] for r in rows]
        check(len(ids) == len(set(ids)), f"unique ids: {name} ({len(ids)})")

    # 3. required fields (free_text + paid_date exempt pre-enrichment)
    required = {
        "products": ["product_id", "name", "category", "price"],
        "customers": ["customer_id", "name", "region", "signup_date", "at_risk"],
        "orders": ["order_id", "customer_id", "product_id", "order_date", "amount", "status",
                   "valid_from", "valid_to"],
        "payments": ["payment_id", "order_id", "amount", "status", "due_date",
                     "valid_from", "valid_to"],
        "complaints": ["complaint_id", "customer_id", "order_id", "filed_date", "category", "reason"],
    }
    table = {"products": products, "customers": customers, "orders": orders,
             "payments": payments, "complaints": complaints}
    for name, fields in required.items():
        bad = [r[fields[0]] for r in table[name] if any(r.get(f) in (None, "") for f in fields)]
        check(not bad, f"required fields present: {name} (bad: {bad[:3]})")

    # 9. enumerations hold at data level
    check(all(o["status"] in ORDER_STATES for o in orders), "order status in OrderStatus enum")
    check(all(p["status"] in PAYMENT_STATES for p in payments), "payment status in PaymentStatus enum")
    check(all(c["category"] in CATEGORIES for c in complaints), "complaint category in ComplaintCategory enum")
    check(all(p["category"] in ("Electronics", "Accessories", "Home & Kitchen", "Office",
                                "Personal Care", "Sports & Outdoors") for p in products),
          "product category in the six v2 taxonomy categories")

    # 6. consistency
    check(len(pay_by_order) == len(payments), "one payment per order")
    amt_mismatch = [o["order_id"] for o in orders if o["order_id"] in pay_by_order
                    and abs(pay_by_order[o["order_id"]]["amount"] - o["amount"]) > 1e-9]
    check(not amt_mismatch, f"payment amount == order amount (bad: {amt_mismatch[:3]})")
    early = [c["complaint_id"] for c in complaints
             if date.fromisoformat(c["filed_date"]) < date.fromisoformat(order_by_id[c["order_id"]]["order_date"])]
    check(not early, f"complaint filed on/after order date (bad: {early[:3]})")
    bad_paid = [p["payment_id"] for p in payments
                if p["status"] == "paid" and not p.get("paid_date")]
    check(not bad_paid, f"paid payments have paid_date (bad: {bad_paid[:3]})")

    # 8. status-history temporal consistency
    def check_status_history(rows, states: set, label: str) -> None:
        bad_order_date = []
        bad_changed_window = []
        bad_missing_pair = []
        bad_prev_enum = []
        for r in rows:
            has_changed = "status_changed_on" in r
            has_prev = "previous_status" in r
            if has_changed != has_prev:
                bad_missing_pair.append(r.get("payment_id") or r.get("order_id"))
            if has_changed:
                vf = date.fromisoformat(r["valid_from"])
                vt = date.fromisoformat(r["valid_to"])
                ch = date.fromisoformat(r["status_changed_on"])
                if not (vf <= ch <= vt):
                    bad_changed_window.append(r.get("payment_id") or r.get("order_id"))
            if has_prev and r["previous_status"] not in states:
                bad_prev_enum.append(r.get("payment_id") or r.get("order_id"))
            if "valid_from" in r and "valid_to" in r:
                vf = date.fromisoformat(r["valid_from"])
                vt = date.fromisoformat(r["valid_to"])
                if vf > vt:
                    bad_order_date.append(r.get("payment_id") or r.get("order_id"))
        check(not bad_missing_pair, f"{label}: status_changed_on and previous_status co-occur (bad: {bad_missing_pair[:3]})")
        check(not bad_changed_window, f"{label}: status_changed_on inside [valid_from, valid_to] (bad: {bad_changed_window[:3]})")
        check(not bad_prev_enum, f"{label}: previous_status in enum (bad: {bad_prev_enum[:3]})")
        check(not bad_order_date, f"{label}: valid_from <= valid_to (bad: {bad_order_date[:3]})")

    check_status_history(orders, ORDER_STATES, "orders")
    check_status_history(payments, PAYMENT_STATES, "payments")

    # 7. atRisk derivation == SWRL rule materialization
    overdue_orders = {p["order_id"] for p in payments if p["status"] == "overdue"}
    rule_positive = set()
    for c in complaints:
        if c["order_id"] in overdue_orders:
            rule_positive.add(c["customer_id"])
    data_positive = {c["customer_id"] for c in customers if c.get("at_risk") is True}
    check(data_positive == rule_positive,
          f"atRisk matches SWRL rule (data={len(data_positive)}, rule={len(rule_positive)})")

    # 5. planted patterns (reuse v1 predicates, v2 sizes)
    manifest = json.loads((RAW / "planted_patterns.json").read_text(encoding="utf-8"))
    for key, spec in manifest["patterns"].items():
        members = {k: set(v) for k, v in spec.items() if k not in ("hops", "description", "count")}
        bad = []
        actual_candidates = []
        if key == "P1":
            actual_candidates = [c for c in complaints
                                 if date(2025, 1, 1) <= date.fromisoformat(c["filed_date"]) <= date(2025, 3, 31)
                                 and pay_by_order.get(c["order_id"]) is not None
                                 and pay_by_order[c["order_id"]]["status"] == "overdue"
                                 and date(2025, 1, 1) <= date.fromisoformat(pay_by_order[c["order_id"]]["due_date"]) <= date(2025, 3, 31)]
            for cid in members["complaints"]:
                c = next(c for c in complaints if c["complaint_id"] == cid)
                o = order_by_id[c["order_id"]]
                p = pay_by_order[o["order_id"]]
                if not (date(2025, 1, 1) <= date.fromisoformat(c["filed_date"]) <= date(2025, 3, 31)
                        and p["status"] == "overdue"
                        and date(2025, 1, 1) <= date.fromisoformat(p["due_date"]) <= date(2025, 3, 31)
                        and date.fromisoformat(c["filed_date"]) >= date.fromisoformat(o["order_date"])):
                    bad.append(cid)
        elif key == "P2":
            actual_candidates = [o for o in orders
                                 if date(2025, 4, 1) <= date.fromisoformat(o["order_date"]) <= date(2025, 6, 30)
                                 and prod_by_id[o["product_id"]]["category"] == "Electronics"]
            for oid in members["orders"]:
                o = order_by_id[oid]
                if not (prod_by_id[o["product_id"]]["category"] == "Electronics"
                        and date(2025, 4, 1) <= date.fromisoformat(o["order_date"]) <= date(2025, 6, 30)):
                    bad.append(oid)
        elif key == "P3":
            actual_candidates = [c for c in complaints
                                 if c["category"] == "billing" and order_by_id[c["order_id"]]["status"] == "completed"
                                 and date(2025, 7, 1) <= date.fromisoformat(order_by_id[c["order_id"]]["order_date"]) <= date(2025, 9, 30)]
            for cid in members["complaints"]:
                c = next(c for c in complaints if c["complaint_id"] == cid)
                o = order_by_id[c["order_id"]]
                if not (c["category"] == "billing" and o["status"] == "completed"
                        and date(2025, 7, 1) <= date.fromisoformat(o["order_date"]) <= date(2025, 9, 30)):
                    bad.append(cid)
        else:  # P5
            actual_candidates = [c for c in complaints
                                 if date(2025, 10, 1) <= date.fromisoformat(c["filed_date"]) <= date(2025, 12, 31)
                                 and prod_by_id[order_by_id[c["order_id"]]["product_id"]]["category"] == "Home & Kitchen"]
            for cid in members["complaints"]:
                c = next(c for c in complaints if c["complaint_id"] == cid)
                o = order_by_id[c["order_id"]]
                if not (date(2025, 10, 1) <= date.fromisoformat(c["filed_date"]) <= date(2025, 12, 31)
                        and prod_by_id[o["product_id"]]["category"] == "Home & Kitchen"):
                    bad.append(cid)
        member_ids = members.get("complaints") or members.get("orders") or set()
        check(not bad, f"{key}: all {len(member_ids)} manifest members satisfy predicate (bad: {bad[:3]})")
        check(len(actual_candidates) >= spec["count"],
              f"{key}: actual positives ({len(actual_candidates)}) >= planted ({spec['count']})")

    # free text (only meaningful after enrichment)
    texts = [c["free_text_description"] for c in complaints]
    if any(t for t in texts):
        empty = [c["complaint_id"] for c in complaints if not c["free_text_description"].strip()]
        check(not empty, f"every complaint has non-empty free text (empty: {empty[:3]})")
    else:
        print("SKIP  free-text checks (complaints not yet enriched)")

    if failures:
        print(f"\n{len(failures)} check(s) FAILED")
        return 1
    print(f"\nverify_data_v2 OK: {len(products)} products, {len(customers)} customers, "
          f"{len(orders)} orders, {len(payments)} payments, {len(complaints)} complaints")
    return 0


if __name__ == "__main__":
    sys.exit(main())