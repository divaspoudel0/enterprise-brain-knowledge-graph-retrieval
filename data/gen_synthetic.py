#!/usr/bin/env python3
"""S2 — synthetic enterprise dataset generator (structured rows first).

Produces the five entity files under data/raw/ with full referential integrity
plus a manifest of deliberately planted multi-hop patterns (P1/P2/P3/P5), the
guaranteed positive examples that S5 benchmark generation will walk.

Determinism: a single `random.Random(SEED)` (default 42) drives all choices;
faker is seeded identically. Re-running with the same seed reproduces the exact
same dataset. The free-text fields (complaint descriptions) are NOT written here
— they are filled by `gen_complaint_text.py` via a committed LLM prompt template
(DATA_PIPELINE.md §1.2). `verify_data.py` refuses to accept the dataset until
both steps have run.

Usage:  uv run --with faker python data/gen_synthetic.py
"""
from __future__ import annotations

import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
PROMPTS = HERE / "prompts"

SEED = 42

REGIONS = ["Bagmati", "Gandaki", "Lumbini", "Sudurpashchim", "Karnali", "Koshi", "Madhesh"]

# 6 categories x 10 products = 60 products
PRODUCTS = {
    "Electronics": [
        ("Wireless Keyboard", 34.99), ("USB-C Hub", 29.99), ("Bluetooth Headphones", 59.99),
        ("Smart Speaker", 49.99), ("HD Webcam", 39.99), ("Power Bank 20000mAh", 24.99),
        ("Wireless Mouse", 19.99), ("HDMI Cable 2m", 9.99), ("Smart Watch", 89.99),
        ("LED Desk Lamp", 27.99),
    ],
    "Accessories": [
        ("Phone Case", 14.99), ("Laptop Sleeve", 22.99), ("Screen Protector", 8.99),
        ("Backpack", 44.99), ("Laptop Stand", 32.99), ("Cable Organizer", 12.99),
        ("Desk Mat", 17.99), ("Keycap Set", 25.99), ("Camera Strap", 15.99),
        ("Card Holder Wallet", 11.99),
    ],
    "Home & Kitchen": [
        ("Non-stick Frying Pan", 29.99), ("Electric Kettle", 24.99), ("Coffee Maker", 54.99),
        ("Air Fryer", 79.99), ("Blender", 39.99), ("Toaster", 21.99),
        ("Cutlery Set (24 pc)", 34.99), ("Storage Containers (8 pc)", 18.99),
        ("Rice Cooker", 47.99), ("Induction Cooktop", 64.99),
    ],
    "Office": [
        ("A4 Printer Paper (500)", 7.99), ("Binder Clips (100 pc)", 3.99),
        ("Whiteboard Markers (4)", 4.99), ("Sticky Notes (5 pack)", 6.99),
        ("Laser Printer", 119.99), ("Paper Shredder", 49.99), ("Stapler + Staples", 8.99),
        ("Desk Organizer", 13.99), ("Notebook (A5, 3 pc)", 9.99), ("Highlighters (6 pc)", 5.99),
    ],
    "Personal Care": [
        ("Electric Toothbrush", 27.99), ("Hair Dryer", 25.99), ("Trimmer Kit", 33.99),
        ("Facial Cleanser", 12.99), ("Sunscreen SPF50", 11.99), ("Massage Gun", 49.99),
        ("Humidifier", 31.99), ("Nail Care Kit", 16.99), ("Shampoo (750ml)", 9.99),
        ("Fitness Tracker", 42.99),
    ],
    "Sports & Outdoors": [
        ("Yoga Mat", 19.99), ("Dumbbell Set 10kg", 44.99), ("Resistance Bands (5 pc)", 13.99),
        ("Hiking Backpack 40L", 59.99), ("Water Bottle 1L", 12.99), ("Jump Rope", 8.99),
        ("Camping Tent 2P", 89.99), ("Running Shoes", 69.99), ("Cycle Helmet", 34.99),
        ("Trekking Poles", 39.99),
    ],
}

ORDER_STATUSES = [("completed", 0.75), ("pending", 0.15), ("cancelled", 0.06), ("refunded", 0.04)]
PAYMENT_STATUSES = [("paid", 0.70), ("overdue", 0.20), ("failed", 0.10)]
COMPLAINT_CATEGORIES = ["billing", "delivery", "product_quality", "service", "refund"]
COMPLAINT_CATEGORY_WEIGHTS = [
    ("billing", 0.25), ("delivery", 0.20), ("product_quality", 0.20),
    ("service", 0.20), ("refund", 0.15),
]
ORDER_COUNT_WEIGHTS = [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 4, 4, 4, 4, 4, 4, 4, 5, 5, 5, 6]

REASONS = {
    "billing": [
        "was charged twice for the same order",
        "was overcharged compared to the quoted price",
        "noticed an unexpected charge on the statement",
        "was billed before the order shipped",
    ],
    "delivery": [
        "the delivery arrived several days late",
        "the package never arrived",
        "the courier delivered to the wrong address",
        "the delivery was left without any signature",
    ],
    "product_quality": [
        "the item arrived damaged",
        "the product stopped working within a week",
        "the item did not match the description",
        "the product looked used when it arrived",
    ],
    "service": [
        "customer support never responded",
        "was put on hold for a long time",
        "support was unable to resolve the issue",
        "received conflicting information from support",
    ],
    "refund": [
        "the refund has not been processed",
        "was told a refund was issued but never received it",
        "returned the item but the refund is still pending",
    ],
}

# ---- planted pattern sizes (logged in DECISIONS.md 2026-08-09) ----
N_CUSTOMERS = 400
P1_N = 30  # 3-hop: Customer->Complaint->Order->Payment(overdue, due Q1 2025), complaint filed Q1 2025
P2_N = 40  # 2-hop: Customer->Order->Product(Electronics) placed Q2 2025
P3_N = 25  # 2-hop: Customer->Complaint->Order(completed, billing) placed Q3 2025
P5_N = 25  # 3-hop: Customer->Complaint->Order->Product(Home & Kitchen) filed Q4 2025
N_COMPLAINTS = 250


def rand_date(rng: random.Random, start: date, end: date) -> date:
    days = (end - start).days
    return start + timedelta(days=rng.randint(0, days))


def weighted(rng: random.Random, pairs):
    total = sum(w for _, w in pairs)
    r = rng.random() * total
    upto = 0.0
    for value, w in pairs:
        upto += w
        if r <= upto:
            return value
    return pairs[-1][0]


def main() -> int:
    rng = random.Random(SEED)

    # faker for names (ne_NP if available, else default), seeded for determinism
    try:
        from faker import Faker
        try:
            faker = Faker("ne_NP")
            locale = "ne_NP"
        except Exception:
            faker = Faker()
            locale = "default"
        faker.seed_instance(SEED)
    except Exception as exc:  # pragma: no cover - faker is required
        print(f"FATAL: faker unavailable: {exc!r}", file=sys.stderr)
        return 1

    # ---- product catalog ----
    products = []
    for category, items in PRODUCTS.items():
        for i, (name, price) in enumerate(items, start=1):
            pid = f"p_{len(products) + 1:04d}"
            products.append({"product_id": pid, "name": name, "category": category, "price": price})

    # ---- customers ----
    customers = []
    for i in range(1, N_CUSTOMERS + 1):
        customers.append({
            "customer_id": f"c_{i:04d}",
            "name": faker.name(),
            "region": rng.choice(REGIONS),
            "signup_date": rand_date(rng, date(2023, 1, 1), date(2024, 12, 31)).isoformat(),
        })
    by_id = {c["customer_id"]: c for c in customers}

    p1_customers = [f"c_{i:04d}" for i in range(1, P1_N + 1)]
    p2_customers = [f"c_{i:04d}" for i in range(P1_N + 1, P1_N + P2_N + 1)]
    p3_customers = [f"c_{i:04d}" for i in range(P1_N + P2_N + 1, P1_N + P2_N + P3_N + 1)]
    p5_customers = [f"c_{i:04d}" for i in range(P1_N + P2_N + P3_N + 1, P1_N + P2_N + P3_N + P5_N + 1)]
    assert len(set(p1_customers) | set(p2_customers) | set(p3_customers) | set(p5_customers)) == P1_N + P2_N + P3_N + P5_N

    electronics = [p for p in products if p["category"] == "Electronics"]
    home_kitchen = [p for p in products if p["category"] == "Home & Kitchen"]
    any_product = [p for p in products if p["category"] not in ("Electronics", "Home & Kitchen")]

    # ---- orders (anchors first, then general fill) ----
    orders = []
    anchor_order = {}  # customer_id -> order dict used as that customer's planted anchor
    order_seq = [0]

    def new_order(customer_id, product, order_date, status):
        order_seq[0] += 1
        oid = f"o_{order_seq[0]:05d}"
        order = {
            "order_id": oid,
            "customer_id": customer_id,
            "product_id": product["product_id"],
            "order_date": order_date.isoformat(),
            "amount": product["price"],
            "status": status,
        }
        orders.append(order)
        return order

    # P1 anchors: order placed 2024-12-02..2025-02-28 so payment due lands in Q1 2025
    for cid in p1_customers:
        od = rand_date(rng, date(2024, 12, 2), date(2025, 2, 28))
        anchor_order[cid] = new_order(cid, rng.choice(any_product), od, "completed")
    # P2 anchors: Electronics order placed in Q2 2025
    for cid in p2_customers:
        od = rand_date(rng, date(2025, 4, 1), date(2025, 6, 30))
        anchor_order[cid] = new_order(cid, rng.choice(electronics), od, weighted(rng, ORDER_STATUSES))
    # P3 anchors: completed order placed in Q3 2025
    for cid in p3_customers:
        od = rand_date(rng, date(2025, 7, 1), date(2025, 9, 30))
        anchor_order[cid] = new_order(cid, rng.choice(any_product), od, "completed")
    # P5 anchors: Home & Kitchen order placed before Q4 2025
    for cid in p5_customers:
        od = rand_date(rng, date(2024, 6, 1), date(2025, 9, 30))
        anchor_order[cid] = new_order(cid, rng.choice(home_kitchen), od, weighted(rng, ORDER_STATUSES))

    # general fill: per-customer order counts, keeping at least the anchor
    for c in customers:
        cid = c["customer_id"]
        n = rng.choice(ORDER_COUNT_WEIGHTS)
        if cid in anchor_order:
            n = max(n - 1, 0)
        for _ in range(n):
            od = rand_date(rng, date(2024, 1, 1), date(2025, 12, 31))
            new_order(cid, rng.choice(products), od, weighted(rng, ORDER_STATUSES))

    # ---- payments (one per order) ----
    payments = []
    payment_seq = [0]
    order_payment = {}
    p1_payments = {}
    for order in sorted(orders, key=lambda o: o["order_id"]):
        payment_seq[0] += 1
        pid = f"pay_{payment_seq[0]:05d}"
        oid = order["order_id"]
        due = date.fromisoformat(order["order_date"]) + timedelta(days=30)
        if any(order is anchor_order[c] for c in p1_customers):
            status = "overdue"
            paid_date = None
            p1_payments[oid] = pid
        else:
            status = weighted(rng, PAYMENT_STATUSES)
            paid_date = rand_date(rng, date.fromisoformat(order["order_date"]), due).isoformat() if status == "paid" else None
        payment = {
            "payment_id": pid,
            "order_id": oid,
            "amount": order["amount"],
            "status": status,
            "due_date": due.isoformat(),
            "paid_date": paid_date,
        }
        payments.append(payment)
        order_payment[oid] = pid

    # ---- complaints ----
    complaints = []
    complaint_seq = [0]
    complained_orders = set()

    def new_complaint(customer_id, order_id, filed_date, category):
        complaint_seq[0] += 1
        cid = f"comp_{complaint_seq[0]:04d}"
        complaints.append({
            "complaint_id": cid,
            "customer_id": customer_id,
            "order_id": order_id,
            "filed_date": filed_date.isoformat(),
            "category": category,
            "reason": rng.choice(REASONS[category]),
            "free_text_description": "",
        })
        complained_orders.add(order_id)
        return cid

    planted = {k: {"customers": [], "orders": [], "payments": [], "complaints": []} for k in ("P1", "P2", "P3", "P5")}

    for cid in p1_customers:
        order = anchor_order[cid]
        filed = rand_date(rng, max(date.fromisoformat(order["order_date"]), date(2025, 1, 1)), date(2025, 3, 31))
        cat = rng.choice(["billing", "delivery"])
        comp = new_complaint(cid, order["order_id"], filed, cat)
        planted["P1"]["customers"].append(cid)
        planted["P1"]["orders"].append(order["order_id"])
        planted["P1"]["payments"].append(order_payment[order["order_id"]])
        planted["P1"]["complaints"].append(comp)

    for cid in p3_customers:
        order = anchor_order[cid]
        filed = rand_date(rng, date.fromisoformat(order["order_date"]), date(2025, 12, 31))
        comp = new_complaint(cid, order["order_id"], filed, "billing")
        planted["P3"]["customers"].append(cid)
        planted["P3"]["orders"].append(order["order_id"])
        planted["P3"]["payments"].append(order_payment[order["order_id"]])
        planted["P3"]["complaints"].append(comp)

    for cid in p5_customers:
        order = anchor_order[cid]
        filed = rand_date(rng, max(date.fromisoformat(order["order_date"]), date(2025, 10, 1)), date(2025, 12, 31))
        cat = rng.choice(["delivery", "product_quality", "service"])
        comp = new_complaint(cid, order["order_id"], filed, cat)
        planted["P5"]["customers"].append(cid)
        planted["P5"]["orders"].append(order["order_id"])
        planted["P5"]["payments"].append(order_payment[order["order_id"]])
        planted["P5"]["complaints"].append(comp)

    # P2 is order-based, not complaint-based: record anchor orders/payments
    for cid in p2_customers:
        order = anchor_order[cid]
        planted["P2"]["customers"].append(cid)
        planted["P2"]["orders"].append(order["order_id"])
        planted["P2"]["payments"].append(order_payment[order["order_id"]])

    # remaining random complaints up to N_COMPLAINTS, each about a distinct order
    eligible_orders = [o for o in orders if o["order_id"] not in complained_orders]
    rng.shuffle(eligible_orders)
    n_remaining = N_COMPLAINTS - (P1_N + P3_N + P5_N)
    for order in eligible_orders[:n_remaining]:
        customer = rng.choice(customers)
        cat = weighted(rng, COMPLAINT_CATEGORY_WEIGHTS)
        filed = rand_date(rng, date.fromisoformat(order["order_date"]), date(2025, 12, 31))
        new_complaint(customer["customer_id"], order["order_id"], filed, cat)

    # ---- write outputs ----
    RAW.mkdir(parents=True, exist_ok=True)
    for name, rows in [("products", products), ("customers", customers),
                       ("orders", orders), ("payments", payments), ("complaints", complaints)]:
        with open(RAW / f"{name}.jsonl", "w", encoding="utf-8") as fh:
            for row in sorted(rows, key=lambda r: r[f"{name[:-1] if name != 'payments' else 'payment'}_id"]):
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    manifest = {
        "seed": SEED,
        "faker_locale": locale,
        "generated_at_utc": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "patterns": {
            key: {
                "hops": info["hops"],
                "description": info["desc"],
                "count": len(planted[key]["customers"]),
                "customers": sorted(planted[key]["customers"]),
                "orders": sorted(planted[key]["orders"]),
                "payments": sorted(planted[key]["payments"]),
                "complaints": sorted(planted[key]["complaints"]),
            }
            for key, info in [
                ("P1", {"hops": 3, "desc": "Customer-FILED->Complaint-ABOUT->Order-HAS_PAYMENT->Payment(status=overdue, due Q1 2025); complaint filed Q1 2025"}),
                ("P2", {"hops": 2, "desc": "Customer-PLACED->Order-FOR->Product(category=Electronics); order placed Q2 2025"}),
                ("P3", {"hops": 2, "desc": "Customer-FILED->Complaint-ABOUT->Order(status=completed, placed Q3 2025); complaint category billing"}),
                ("P5", {"hops": 3, "desc": "Customer-FILED->Complaint-ABOUT->Order-FOR->Product(category=Home & Kitchen); complaint filed Q4 2025"}),
            ]
        },
    }
    (RAW / "planted_patterns.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    config = {
        "seed": SEED,
        "faker_locale": locale,
        "n_products": len(products),
        "n_customers": len(customers),
        "n_orders": len(orders),
        "n_payments": len(payments),
        "n_complaints": len(complaints),
        "planted": {"P1": P1_N, "P2": P2_N, "P3": P3_N, "P5": P5_N},
        "status_distributions": {"order": ORDER_STATUSES, "payment": PAYMENT_STATUSES},
        "free_text_model": "Qwen/Qwen2.5-7B-Instruct",
        "free_text_generated_by": "data/gen_complaint_text.py (runs after this script)",
    }
    (RAW / "generation_config.json").write_text(
        json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # ---- summary ----
    print(f"products:   {len(products)}")
    print(f"customers:  {len(customers)}")
    print(f"orders:     {len(orders)}")
    print(f"payments:   {len(payments)}")
    print(f"complaints: {len(complaints)}")
    for key in ("P1", "P2", "P3", "P5"):
        print(f"pattern {key}: {len(planted[key]['customers'])} customers, "
              f"{len(planted[key]['orders'])} orders, "
              f"{len(planted[key]['complaints'])} complaints")
    print("wrote:", sorted(p.name for p in RAW.iterdir()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
