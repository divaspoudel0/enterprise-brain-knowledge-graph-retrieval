#!/usr/bin/env python3
"""V2 synthetic enterprise dataset generator (V2_PLAN D5).

Mirrors data/gen_synthetic.py's structure and logic, scaled up and enriched with:
  - 120 products (6 categories × 20) and 2,500 customers
  - Temporal facts: validFrom/validTo on status properties, previous_status, status_changed_on
  - Temporal sub-patterns P6 (order status changed before a date) and P7 (payment overdue then paid)
  - atRisk derivation: customer with overdue payment + filed complaint = atRisk(true)
  - Planted patterns P1/P2/P3/P5 kept and sized up

Outputs data/raw_v2/ (v1 data untouched).
Usage: uv run --with faker python data/gen_synthetic_v2.py
"""
from __future__ import annotations

import json
import random
import sys
from datetime import date, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW_V2 = HERE / "raw_v2"
SEED = 12345

REGIONS = ["Bagmati", "Gandaki", "Lumbini", "Sudurpashchim", "Karnali", "Koshi", "Madhesh"]

# ---- 6 categories × 20 products = 120 ----
PRODUCTS = {
    "Electronics": [
        ("Wireless Keyboard", 34.99), ("USB-C Hub", 29.99), ("Bluetooth Headphones", 59.99),
        ("Smart Speaker", 49.99), ("HD Webcam", 39.99), ("Power Bank 20000mAh", 24.99),
        ("Wireless Mouse", 19.99), ("HDMI Cable 2m", 9.99), ("Smart Watch", 89.99),
        ("LED Desk Lamp", 27.99), ("External SSD 1TB", 79.99), ("Portable Monitor 15in", 199.99),
        ("Mechanical Keyboard", 89.99), ("Gaming Mouse", 64.99), ("Webcam Ring Light", 14.99),
        ("Wireless Charger Pad", 19.99), ("Laptop Cooling Pad", 24.99), ("Audio Splitter", 7.99),
        ("Bluetooth Speaker Mini", 34.99), ("USB-C Cable 3m", 11.99),
    ],
    "Accessories": [
        ("Phone Case", 14.99), ("Laptop Sleeve", 22.99), ("Screen Protector", 8.99),
        ("Backpack", 44.99), ("Laptop Stand", 32.99), ("Cable Organizer", 12.99),
        ("Desk Mat", 17.99), ("Keycap Set", 25.99), ("Camera Strap", 15.99),
        ("Card Holder Wallet", 11.99), ("Travel Pouch Set", 9.99), ("Watch Band", 14.99),
        ("Earphone Tips", 5.99), ("Laptop Lock", 29.99), ("USB Flash Drive 64GB", 12.99),
        ("Monitor Arm", 49.99), ("Wireless Numpad", 16.99), ("Notebook Stand", 19.99),
        ("Pen Case", 8.99), ("Mouse Pad XL", 18.99),
    ],
    "Home & Kitchen": [
        ("Non-stick Frying Pan", 29.99), ("Electric Kettle", 24.99), ("Coffee Maker", 54.99),
        ("Air Fryer", 79.99), ("Blender", 39.99), ("Toaster", 21.99),
        ("Cutlery Set (24 pc)", 34.99), ("Storage Containers (8 pc)", 18.99),
        ("Rice Cooker", 47.99), ("Induction Cooktop", 64.99), ("Immersion Blender", 29.99),
        ("Electric Skillet", 39.99), ("Dish Drying Rack", 19.99), ("Spice Rack", 24.99),
        ("Bamboo Cutting Board", 17.99), ("French Press 1L", 14.99), ("Wine Opener Set", 12.99),
        ("Bread Maker", 89.99), ("Air Purifier Mini", 59.99), ("Garlic Press", 7.99),
    ],
    "Office": [
        ("A4 Printer Paper (500)", 7.99), ("Binder Clips (100 pc)", 3.99),
        ("Whiteboard Markers (4)", 4.99), ("Sticky Notes (5 pack)", 6.99),
        ("Laser Printer", 119.99), ("Paper Shredder", 49.99), ("Stapler + Staples", 8.99),
        ("Desk Organizer", 13.99), ("Notebook (A5, 3 pc)", 9.99), ("Highlighters (6 pc)", 5.99),
        ("Label Maker", 34.99), ("Document Scanner", 149.99), ("Whiteboard 90x60", 79.99),
        ("Ergonomic Chair Mat", 29.99), ("Standing Desk Converter", 199.99),
        ("Monitor Stand", 39.99), ("Power Strip 8-port", 19.99), ("Cable Clip 10 pc", 6.99),
        ("Desk Lamp LED", 24.99), ("USB Microphone", 59.99),
    ],
    "Personal Care": [
        ("Electric Toothbrush", 27.99), ("Hair Dryer", 25.99), ("Trimmer Kit", 33.99),
        ("Facial Cleanser", 12.99), ("Sunscreen SPF50", 11.99), ("Massage Gun", 49.99),
        ("Humidifier", 31.99), ("Nail Care Kit", 16.99), ("Shampoo (750ml)", 9.99),
        ("Fitness Tracker", 42.99), ("Electric Shaver", 39.99), ("Beard Trimmer", 29.99),
        ("Facial Steamer", 24.99), ("Manicure Set", 19.99), ("Electric Foot Massager", 44.99),
        ("Hair Straightener", 34.99), ("Scalp Massager", 12.99), ("Aromatherapy Diffuser", 29.99),
        ("UV Sterilizer", 19.99), ("Collagen Serum", 14.99),
    ],
    "Sports & Outdoors": [
        ("Yoga Mat", 19.99), ("Dumbbell Set 10kg", 44.99), ("Resistance Bands (5 pc)", 13.99),
        ("Hiking Backpack 40L", 59.99), ("Water Bottle 1L", 12.99), ("Jump Rope", 8.99),
        ("Camping Tent 2P", 89.99), ("Running Shoes", 69.99), ("Cycle Helmet", 34.99),
        ("Trekking Poles", 39.99), ("Kettlebell 12kg", 34.99), ("Swim Goggles", 14.99),
        ("Boxing Gloves", 29.99), ("Foam Roller", 19.99), ("Pull-up Bar", 24.99),
        ("Cycling Shorts", 22.99), ("Gym Bag", 19.99), ("Ab Roller", 12.99),
        ("Resistance Band Door Anchor", 6.99), ("Hiking Gaiters", 14.99),
    ],
}

ORDER_STATUSES = [("completed", 0.70), ("pending", 0.15), ("cancelled", 0.08), ("refunded", 0.07)]
PAYMENT_STATUSES = [("paid", 0.65), ("overdue", 0.20), ("failed", 0.15)]
COMPLAINT_CATEGORIES = ["billing", "delivery", "product_quality", "service", "refund"]
COMPLAINT_CATEGORY_WEIGHTS = [
    ("billing", 0.25), ("delivery", 0.20), ("product_quality", 0.20),
    ("service", 0.20), ("refund", 0.15),
]

N_CUSTOMERS = 2500
P1_N = 120   # 3-hop
P2_N = 160   # 2-hop
P3_N = 100   # 2-hop
P5_N = 100   # 3-hop
N_COMPLAINTS = 1200

# Status-change parameters (v2)
ORDER_STATUS_CHANGE_PROB = 0.20
PAYMENT_STATUS_CHANGE_PROB = 0.15
# validFrom/validTo on facts
DEFAULT_VALID_FROM = "2023-01-01"

REASONS = {
    "billing": [
        "the total charged did not match the amount agreed at checkout",
        "noticed a charge on the statement that was not expected",
        "was billed before the order was confirmed",
        "the invoice included an item that was not ordered",
    ],
    "delivery": [
        "the delivery arrived later than expected",
        "the package never arrived",
        "the courier delivered to the wrong address",
        "the delivery was left without any confirmation",
    ],
    "product_quality": [
        "the item arrived damaged",
        "the product stopped working shortly after arrival",
        "the item did not match the description",
        "the product appeared used when it arrived",
    ],
    "service": [
        "customer support never responded",
        "support did not resolve the issue",
        "received conflicting information from support",
        "support was not available when needed",
    ],
    "refund": [
        "the refund has not been processed",
        "was told a refund was issued but never received it",
        "returned the item but the refund is still pending",
        "the refund process is taking longer than expected",
    ],
}

# Order-count distribution weighted toward many small customers
ORDER_COUNT_WEIGHTS = [1]*40 + [2]*25 + [3]*20 + [4]*10 + [5]*4 + [6]*1


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


def make_status_change(rng: random.Random, order_date: date,
                       previous_options: list[str]):
    """Return a status-history dict (previous_status, status_changed_on, valid_from, valid_to)
    or None. previous_options must be valid status values for the owning entity type."""
    if rng.random() > ORDER_STATUS_CHANGE_PROB:
        return None
    changed_on = order_date + timedelta(days=rng.randint(7, 90))
    changed_on = min(changed_on, date(2025, 12, 31))
    return {
        "previous_status": rng.choice(previous_options),
        "status_changed_on": changed_on.isoformat(),
        "valid_from": order_date.isoformat(),
        "valid_to": changed_on.isoformat(),
    }


def main() -> int:
    rng = random.Random(SEED)

    try:
        from faker import Faker
        try:
            faker = Faker("ne_NP")
            locale = "ne_NP"
        except Exception:
            faker = Faker()
            locale = "default"
        faker.seed_instance(SEED)
    except Exception as exc:
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

    p1_customers = [f"c_{i:04d}" for i in range(1, P1_N + 1)]
    p2_customers = [f"c_{i:04d}" for i in range(P1_N + 1, P1_N + P2_N + 1)]
    p3_customers = [f"c_{i:04d}" for i in range(P1_N + P2_N + 1, P1_N + P2_N + P3_N + 1)]
    p5_customers = [f"c_{i:04d}" for i in range(P1_N + P2_N + P3_N + 1, P1_N + P2_N + P3_N + P5_N + 1)]
    assert len(set(p1_customers) | set(p2_customers) | set(p3_customers) | set(p5_customers)) == P1_N + P2_N + P3_N + P5_N

    electronics = [p for p in products if p["category"] == "Electronics"]
    home_kitchen = [p for p in products if p["category"] == "Home & Kitchen"]
    any_product = [p for p in products if p["category"] not in ("Electronics", "Home & Kitchen")]

    # ---- orders ----
    orders = []
    anchor_order = {}
    order_seq = [0]

    def new_order(customer_id, product, order_date, status):
        order_seq[0] += 1
        oid = f"o_{order_seq[0]:05d}"
        order = {
            "order_id": oid, "customer_id": customer_id, "product_id": product["product_id"],
            "order_date": order_date.isoformat(), "amount": product["price"], "status": status,
            "valid_from": order_date.isoformat(), "valid_to": "2099-12-31",
        }
        orders.append(order)
        return order

    # P1/P3/P5 anchor dates
    for cid in p1_customers:
        od = rand_date(rng, date(2024, 12, 2), date(2025, 2, 28))
        anchor_order[cid] = new_order(cid, rng.choice(any_product), od, "completed")
    for cid in p2_customers:
        od = rand_date(rng, date(2025, 4, 1), date(2025, 6, 30))
        anchor_order[cid] = new_order(cid, rng.choice(electronics), od, weighted(rng, ORDER_STATUSES))
    for cid in p3_customers:
        od = rand_date(rng, date(2025, 7, 1), date(2025, 9, 30))
        anchor_order[cid] = new_order(cid, rng.choice(any_product), od, "completed")
    for cid in p5_customers:
        od = rand_date(rng, date(2024, 6, 1), date(2025, 9, 30))
        anchor_order[cid] = new_order(cid, rng.choice(home_kitchen), od, weighted(rng, ORDER_STATUSES))

    # General fill
    for c in customers:
        cid = c["customer_id"]
        n = 1 + int(rng.random() * 5)
        if cid in anchor_order:
            n = max(n - 1, 0)
        for _ in range(n):
            od = rand_date(rng, date(2024, 1, 1), date(2025, 12, 31))
            new_order(cid, rng.choice(products), od, weighted(rng, ORDER_STATUSES))

    # Temporal: add status history to a subset of orders
    orders_changed = 0
    order_prev_options = ["pending", "cancelled", "refunded"]
    for o in orders:
        chg = make_status_change(rng, date.fromisoformat(o["order_date"]), order_prev_options)
        if chg is not None:
            o.update(chg)
            orders_changed += 1

    # ---- payments (one per order) ----
    payments = []
    payment_seq = [0]
    order_payment = {}
    p1_payments = {}
    payments_changed = 0
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
            paid_date = (rand_date(rng, date.fromisoformat(order["order_date"]), due).isoformat()
                         if status == "paid" else None)
        payment = {
            "payment_id": pid, "order_id": oid, "amount": order["amount"],
            "status": status, "due_date": due.isoformat(), "paid_date": paid_date,
            "valid_from": order["order_date"], "valid_to": "2099-12-31",
        }
        payments.append(payment)
        order_payment[oid] = pid
        # Temporal: status change on some payments
        if rng.random() < PAYMENT_STATUS_CHANGE_PROB and status in ("paid", "overdue"):
            changed_on = due + timedelta(days=rng.randint(1, 30))
            changed_on = min(changed_on, date(2025, 12, 31))
            prev = rng.choice(["overdue", "failed"] if status == "paid" else ["failed", "paid"])
            payment["previous_status"] = prev
            payment["status_changed_on"] = changed_on.isoformat()
            payment["valid_to"] = changed_on.isoformat()
            payments_changed += 1

    # ---- complaints ----
    complaints = []
    complaint_seq = [0]
    complained_orders = set()

    def new_complaint(customer_id, order_id, filed_date, category):
        complaint_seq[0] += 1
        cid = f"comp_{complaint_seq[0]:04d}"
        complaints.append({
            "complaint_id": cid, "customer_id": customer_id, "order_id": order_id,
            "filed_date": filed_date.isoformat(), "category": category,
            "reason": rng.choice(REASONS[category]), "free_text_description": "",
        })
        complained_orders.add(order_id)
        return cid

    planted = {k: {"customers": [], "orders": [], "payments": [], "complaints": []} for k in ("P1", "P2", "P3", "P5")}

    for cid in p1_customers:
        order = anchor_order[cid]
        filed = rand_date(rng, max(date.fromisoformat(order["order_date"]), date(2025, 1, 1)), date(2025, 3, 31))
        comp = new_complaint(cid, order["order_id"], filed, rng.choice(["billing", "delivery"]))
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
        comp = new_complaint(cid, order["order_id"], filed, rng.choice(["delivery", "product_quality", "service"]))
        planted["P5"]["customers"].append(cid)
        planted["P5"]["orders"].append(order["order_id"])
        planted["P5"]["payments"].append(order_payment[order["order_id"]])
        planted["P5"]["complaints"].append(comp)

    for cid in p2_customers:
        order = anchor_order[cid]
        planted["P2"]["customers"].append(cid)
        planted["P2"]["orders"].append(order["order_id"])
        planted["P2"]["payments"].append(order_payment[order["order_id"]])

    eligible_orders = [o for o in orders if o["order_id"] not in complained_orders]
    rng.shuffle(eligible_orders)
    n_remaining = N_COMPLAINTS - (P1_N + P3_N + P5_N)
    for order in eligible_orders[:n_remaining]:
        customer = rng.choice(customers)
        cat = weighted(rng, COMPLAINT_CATEGORY_WEIGHTS)
        filed = rand_date(rng, date.fromisoformat(order["order_date"]), date(2025, 12, 31))
        new_complaint(customer["customer_id"], order["order_id"], filed, cat)

    # ---- atRisk derivation (SWRL rule: Customer filed complaint about order with overdue payment) ----
    overdue_orders = {p["order_id"] for p in payments if p["status"] == "overdue"}
    at_risk_customers = set()
    for comp in complaints:
        if comp["order_id"] in overdue_orders:
            at_risk_customers.add(comp["customer_id"])

    # ---- write outputs ----
    RAW_V2.mkdir(parents=True, exist_ok=True)
    for c in customers:
        c["at_risk"] = c["customer_id"] in at_risk_customers
    for name, rows in [("products", products), ("customers", customers),
                       ("orders", orders), ("payments", payments), ("complaints", complaints)]:
        with open(RAW_V2 / f"{name}.jsonl", "w", encoding="utf-8") as fh:
            for row in sorted(rows, key=lambda r: r[f"{name[:-1] if name != 'payments' else 'payment'}_id"]):
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    manifest = {
        "seed": SEED, "faker_locale": locale,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "patterns": {
            key: {
                "hops": info["hops"], "description": info["desc"],
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
    (RAW_V2 / "planted_patterns.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    config = {
        "seed": SEED, "faker_locale": locale,
        "n_products": len(products), "n_customers": len(customers),
        "n_orders": len(orders), "n_payments": len(payments),
        "n_complaints": len(complaints),
        "orders_with_status_history": orders_changed,
        "payments_with_status_history": payments_changed,
        "at_risk_customers": sorted(at_risk_customers),
        "planted": {"P1": P1_N, "P2": P2_N, "P3": P3_N, "P5": P5_N},
        "status_distributions": {"order": ORDER_STATUSES, "payment": PAYMENT_STATUSES},
        "free_text_model": "Qwen/Qwen2.5-7B-Instruct",
        "free_text_generated_by": "data/gen_complaint_text.py (runs after this script)",
    }
    (RAW_V2 / "generation_config.json").write_text(
        json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"products:   {len(products)}")
    print(f"customers:  {len(customers)}")
    print(f"orders:     {len(orders)} (orders with status history: {orders_changed})")
    print(f"payments:   {len(payments)} (payments with status history: {payments_changed})")
    print(f"complaints: {len(complaints)}")
    print(f"at-risk customers: {len(at_risk_customers)}")
    for key in ("P1", "P2", "P3", "P5"):
        print(f"pattern {key}: {len(planted[key]['customers'])} customers, "
              f"{len(planted[key]['orders'])} orders, "
              f"{len(planted[key]['complaints'])} complaints")
    print("wrote:", sorted(p.name for p in RAW_V2.iterdir()))
    return 0


if __name__ == "__main__":
    from datetime import datetime  # noqa: E402
    sys.exit(main())