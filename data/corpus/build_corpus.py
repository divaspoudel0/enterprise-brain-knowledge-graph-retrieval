#!/usr/bin/env python3
"""S4 — build the retrieval text corpus from data/raw (DATA_PIPELINE.md §3).

Corpus composition (logged in DECISIONS.md 2026-08-09):
  (a) the LLM-generated free-text complaint descriptions, and
  (b) deterministic natural-language records for every entity (products, customers,
      orders, payments) so the vector-only baseline (S6) can retrieve facts across
      the whole dataset, not just complaint text.
Every record carries `record_id` == the source row id (provenance anchor, same value
as eb:source_record_id in the graph — check_sync.py asserts the 1:1 sync).

Chunking (§3): records are short (<~500 tokens), so each record is its own chunk; a
chunk_id -> source_record_id map is still produced for the embedding step.

Output: data/corpus/text_records.jsonl (committed).

Usage:  uv run python data/corpus/build_corpus.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
RAW = HERE / "raw"
OUT_DIR = HERE / "corpus"
OUT = OUT_DIR / "text_records.jsonl"

MAX_CHUNK_TOKENS = 500


def load(name: str) -> list[dict]:
    return [json.loads(line) for line in (RAW / name).open(encoding="utf-8")]


def chunks_of(text: str, start_id: str) -> list[str]:
    """Split long text into <=MAX_CHUNK_TOKENS chunks (no-op for short records)."""
    words = text.split()
    if len(words) <= MAX_CHUNK_TOKENS:
        return [text]
    chunks = []
    for i in range(0, len(words), MAX_CHUNK_TOKENS):
        chunks.append(" ".join(words[i:i + MAX_CHUNK_TOKENS]))
    return chunks


def main() -> int:
    products = load("products.jsonl")
    customers = load("customers.jsonl")
    orders = load("orders.jsonl")
    payments = load("payments.jsonl")
    complaints = load("complaints.jsonl")

    prod_by_id = {p["product_id"]: p for p in products}
    order_by_id = {o["order_id"]: o for o in orders}
    pay_by_order = {p["order_id"]: p for p in payments}

    records = []
    chunk_map = {}  # chunk_id -> source_record_id

    for p in products:
        records.append({
            "record_id": p["product_id"], "entity_type": "Product",
            "text": (f"Product {p['product_id']} — {p['name']}. "
                     f"Category: {p['category']}. Price: {p['price']}."),
        })
    for c in customers:
        records.append({
            "record_id": c["customer_id"], "entity_type": "Customer",
            "text": (f"Customer {c['customer_id']} — {c['name']}. "
                     f"Region: {c['region']}. Signed up: {c['signup_date']}."),
        })
    for o in orders:
        prod = prod_by_id[o["product_id"]]
        records.append({
            "record_id": o["order_id"], "entity_type": "Order",
            "text": (f"Order {o['order_id']} — placed by customer {o['customer_id']} "
                     f"on {o['order_date']}. Product: {prod['product_id']} ({prod['name']}). "
                     f"Amount: {o['amount']}. Status: {o['status']}."),
        })
    for pay in payments:
        o = order_by_id[pay["order_id"]]
        paid = f" Paid: {pay['paid_date']}." if pay.get("paid_date") else ""
        records.append({
            "record_id": pay["payment_id"], "entity_type": "Payment",
            "text": (f"Payment {pay['payment_id']} — for order {pay['order_id']}. "
                     f"Amount: {pay['amount']}. Status: {pay['status']}. "
                     f"Due: {pay['due_date']}.{paid}"),
        })
    for comp in complaints:
        o = order_by_id[comp["order_id"]]
        records.append({
            "record_id": comp["complaint_id"], "entity_type": "Complaint",
            "text": (f"Complaint {comp['complaint_id']} — filed by customer "
                     f"{comp['customer_id']} on {comp['filed_date']} about order "
                     f"{o['order_id']} ({o['order_date']}). Category: {comp['category']}. "
                     f"Description: {comp['free_text_description']}"),
        })

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    n_chunks = 0
    for r in records:
        for i, ch in enumerate(chunks_of(r["text"], r["record_id"])):
            chunk_map[f"{r['record_id']}:{i}"] = r["record_id"]
            n_chunks += 1

    print(f"records: {len(records)} (products {len(products)}, customers {len(customers)}, "
          f"orders {len(orders)}, payments {len(payments)}, complaints {len(complaints)})")
    print(f"chunks: {n_chunks} (1:1 — no record exceeds {MAX_CHUNK_TOKENS} tokens)")
    lens = [len(r["text"].split()) for r in records]
    print(f"token length: min={min(lens)}, max={max(lens)}, mean={sum(lens)/len(lens):.1f}")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
