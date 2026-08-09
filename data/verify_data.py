#!/usr/bin/env python3
"""S2 verification — DATA_PIPELINE.md §1.3 (mandatory before S3/S4).

Loads the generated raw data and fails loudly (exit 1) on any violation:
  1. Referential integrity: every Order/Payment/Complaint foreign key resolves.
  2. Uniqueness: no duplicate entity ids.
  3. Required fields: no null/empty values (free-text fields are exempt until the
     LLM enrichment step has run).
  4. Free text (when enriched): every complaint has exactly one non-empty
     `free_text_description`, none over ~500 tokens.
  5. Planted multi-hop patterns: every manifest member satisfies its predicate
     AND the actual positive count is >= the planted count (guaranteed positives
     for S5).
  6. Consistency: one payment per order, payment amount == order amount,
     complaint filed on/after its order date.

Usage:  uv run python data/verify_data.py
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"

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

    # 3. required fields (no null/empty); free-text + paid_date exempt pre-enrichment
    required = {
        "products": ["product_id", "name", "category", "price"],
        "customers": ["customer_id", "name", "region", "signup_date"],
        "orders": ["order_id", "customer_id", "product_id", "order_date", "amount", "status"],
        "payments": ["payment_id", "order_id", "amount", "status", "due_date"],
        "complaints": ["complaint_id", "customer_id", "order_id", "filed_date", "category", "reason"],
    }
    for name, fields in required.items():
        rows = {"products": products, "customers": customers, "orders": orders,
                "payments": payments, "complaints": complaints}[name]
        bad = [r[fields[0]] for r in rows if any(r.get(f) in (None, "") for f in fields)]
        check(not bad, f"required fields present: {name} (bad: {bad[:3]})")

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

    # 4. free text (only meaningful after enrichment)
    texts = [c["free_text_description"] for c in complaints]
    enriched = any(t for t in texts)
    if enriched:
        empty = [c["complaint_id"] for c in complaints if not c["free_text_description"].strip()]
        check(not empty, f"every complaint has non-empty free text (empty: {empty[:3]})")
        overlong = [c["complaint_id"] for c in complaints
                    if len(c["free_text_description"].split()) > 500]
        check(not overlong, f"no free-text field exceeds ~500 tokens (over: {overlong[:3]})")
        check(len(texts) == len({t.strip() for t in texts}), "free-text descriptions are distinct")
    else:
        print("SKIP  free-text checks (complaints not yet enriched by gen_complaint_text.py)")

    # 5. planted patterns (manifest members satisfy predicate; actual >= planted)
    manifest = json.loads((RAW / "planted_patterns.json").read_text(encoding="utf-8"))
    for key, spec in manifest["patterns"].items():
        members = {k: set(v) for k, v in spec.items() if k not in ("hops", "description", "count")}
        bad = []
        if key == "P1":
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
            for oid in members["orders"]:
                o = order_by_id[oid]
                if not (prod_by_id[o["product_id"]]["category"] == "Electronics"
                        and date(2025, 4, 1) <= date.fromisoformat(o["order_date"]) <= date(2025, 6, 30)):
                    bad.append(oid)
        elif key == "P3":
            for cid in members["complaints"]:
                c = next(c for c in complaints if c["complaint_id"] == cid)
                o = order_by_id[c["order_id"]]
                if not (c["category"] == "billing" and o["status"] == "completed"
                        and date(2025, 7, 1) <= date.fromisoformat(o["order_date"]) <= date(2025, 9, 30)):
                    bad.append(cid)
        elif key == "P5":
            for cid in members["complaints"]:
                c = next(c for c in complaints if c["complaint_id"] == cid)
                o = order_by_id[c["order_id"]]
                if not (date(2025, 10, 1) <= date.fromisoformat(c["filed_date"]) <= date(2025, 12, 31)
                        and prod_by_id[o["product_id"]]["category"] == "Home & Kitchen"):
                    bad.append(cid)
        member_ids = members.get("complaints") or members.get("orders") or set()
        check(not bad, f"{key}: all {len(member_ids)} manifest members satisfy predicate (bad: {bad[:3]})")

        # count actual positives per pattern
        if key == "P1":
            actual = [c for c in complaints
                      if date(2025, 1, 1) <= date.fromisoformat(c["filed_date"]) <= date(2025, 3, 31)
                      and pay_by_order.get(c["order_id"]) is not None
                      and pay_by_order[c["order_id"]]["status"] == "overdue"
                      and date(2025, 1, 1) <= date.fromisoformat(pay_by_order[c["order_id"]]["due_date"]) <= date(2025, 3, 31)]
        elif key == "P2":
            actual = [o for o in orders
                      if date(2025, 4, 1) <= date.fromisoformat(o["order_date"]) <= date(2025, 6, 30)
                      and prod_by_id[o["product_id"]]["category"] == "Electronics"]
        elif key == "P3":
            actual = [c for c in complaints
                      if c["category"] == "billing" and order_by_id[c["order_id"]]["status"] == "completed"
                      and date(2025, 7, 1) <= date.fromisoformat(order_by_id[c["order_id"]]["order_date"]) <= date(2025, 9, 30)]
        else:  # P5
            actual = [c for c in complaints
                      if date(2025, 10, 1) <= date.fromisoformat(c["filed_date"]) <= date(2025, 12, 31)
                      and prod_by_id[order_by_id[c["order_id"]]["product_id"]]["category"] == "Home & Kitchen"]
        check(len(actual) >= spec["count"], f"{key}: actual positives ({len(actual)}) >= planted ({spec['count']})")

    if failures:
        print(f"\n{len(failures)} check(s) FAILED")
        return 1
    print(f"\nverify_data OK: {len(products)} products, {len(customers)} customers, "
          f"{len(orders)} orders, {len(payments)} payments, {len(complaints)} complaints")
    return 0


if __name__ == "__main__":
    sys.exit(main())
