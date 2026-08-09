#!/usr/bin/env python3
"""S2 — LLM enrichment of complaint free-text descriptions (DATA_PIPELINE.md §1.2).

Reads `data/raw/complaints.jsonl` (structured rows, includes the internal
`reason` field), renders one prompt per complaint from the committed template
`data/prompts/complaint_generation.txt` using ONLY facts present in the
structured record, calls the generation model (default
`Qwen/Qwen2.5-7B-Instruct`, override with GENERATION_MODEL), and writes the
filled `free_text_description` back into `complaints.jsonl`.

Fact-fidelity enforcement (DATA_PIPELINE.md §1.2 "never let the LLM invent
facts"): after the first pass, any complaint whose text contains a number that
is not one of its fact numbers is sent through a second, explicit rewrite pass
(remove every figure not in the facts); if figures still remain they are
stripped mechanically and a warning is printed. `verify_data.py` independently
asserts this.

Contract: runs AFTER gen_synthetic.py and BEFORE verify_data.py; verify_data.py
fails until every complaint has non-empty, distinct, fact-faithful text.

Usage:
  uv run python data/gen_complaint_text.py --dry-run   # print prompts only
  uv run python data/gen_complaint_text.py --limit 5   # smoke test
  uv run python data/gen_complaint_text.py             # full run (needs GPU)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
PROMPTS = HERE / "prompts"
TEMPLATE = (PROMPTS / "complaint_generation.txt").read_text(encoding="utf-8")

DEFAULT_MODEL = "Qwen/Qwen2.5-7B-Instruct"
TEMPERATURE = 0.2
TOP_P = 0.9
MAX_NEW_TOKENS = 150
SEED = 42

_NUM = re.compile(r"\d+(?:\.\d+)?")


def load(name: str) -> list[dict]:
    return [json.loads(line) for line in (RAW / name).open(encoding="utf-8")]


def facts_block(c: dict, order: dict, product: dict, customer: dict, payment: dict) -> str:
    paid_note = f", paid on {payment['paid_date']}" if payment.get("paid_date") else ""
    due_note = f", due {payment['due_date']}" if payment.get("due_date") else ""
    return (
        "Facts:\n"
        f"- Customer name: {customer['name']}\n"
        f"- Customer region: {customer['region']}\n"
        f"- Product: {product['name']} (category: {product['category']}, price: {product['price']})\n"
        f"- Order placed: {order['order_date']} (status: {order['status']}, amount: {order['amount']})\n"
        f"- Payment: {payment['status']}{paid_note}{due_note}\n"
        f"- Complaint category: {c['category']}\n"
        f"- What happened (reason): {c['reason']}"
    )


def build_prompt(c: dict, order: dict, product: dict, customer: dict, payment: dict) -> str:
    paid_note = f", paid on {payment['paid_date']}" if payment.get("paid_date") else ""
    due_note = f", due {payment['due_date']}" if payment.get("due_date") else ""
    return TEMPLATE.format(
        customer_name=customer["name"],
        region=customer["region"],
        product_name=product["name"],
        product_category=product["category"],
        price=product["price"],
        order_date=order["order_date"],
        order_status=order["status"],
        amount=order["amount"],
        payment_status=payment["status"],
        paid_date_note=paid_note,
        due_date_note=due_note,
        category=c["category"],
        reason=c["reason"],
    )


def allowed_numbers(c: dict, order: dict, product: dict, payment: dict) -> set[str]:
    facts = [order["amount"], product["price"], order["order_date"],
             c["filed_date"], payment.get("due_date"), payment.get("paid_date")]
    allowed: set[str] = set()
    for v in facts:
        if v is None:
            continue
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            allowed.add(str(v))
        else:
            for tok in _NUM.findall(str(v)):
                allowed.add(str(int(float(tok))) if float(tok).is_integer() else tok)
    return allowed


def disallowed_numbers(text: str, allowed: set[str]) -> list[str]:
    return [tok for tok in _NUM.findall(text) if tok not in allowed]


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="process only the first N complaints (0 = all)")
    ap.add_argument("--dry-run", action="store_true", help="print prompts, do not call the model")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    complaints = load("complaints.jsonl")
    orders = {o["order_id"]: o for o in load("orders.jsonl")}
    products = {p["product_id"]: p for p in load("products.jsonl")}
    customers = {c["customer_id"]: c for c in load("customers.jsonl")}
    payments = {p["order_id"]: p for p in load("payments.jsonl")}

    subset = complaints[: args.limit] if args.limit else complaints
    ctx = []
    for c in subset:
        o = orders[c["order_id"]]
        ctx.append((c, o, products[o["product_id"]], customers[c["customer_id"]], payments[o["order_id"]]))

    if args.dry_run:
        for c, o, prod, cust, pay in ctx:
            print(f"===== {c['complaint_id']} =====")
            print(build_prompt(c, o, prod, cust, pay))
        print(f"DRY RUN: {len(subset)} prompts rendered from committed template; no model call.")
        return 0

    if not complaints:  # pragma: no cover
        print("FATAL: no complaints loaded", file=sys.stderr)
        return 1

    import torch
    from transformers import pipeline

    torch.manual_seed(SEED)
    print(f"loading model {DEFAULT_MODEL} ...", flush=True)
    try:
        gen = pipeline("text-generation", model=DEFAULT_MODEL, torch_dtype="bfloat16", device_map="auto")
    except Exception:
        gen = pipeline("text-generation", model=DEFAULT_MODEL, torch_dtype="bfloat16", device=0)

    def call(prompt: str, temperature: float = TEMPERATURE) -> str:
        out = gen(prompt, max_new_tokens=MAX_NEW_TOKENS, do_sample=True,
                  temperature=temperature, top_p=TOP_P)[0]["generated_text"]
        return out.split("Complaint:")[-1].strip()

    rewrites = 0
    stripped = 0
    filled = 0
    for c, o, prod, cust, pay in ctx:
        allowed = allowed_numbers(c, o, prod, pay)
        prompt = build_prompt(c, o, prod, cust, pay)
        text = call(prompt)
        if len(text.split()) < 10:
            text = call(prompt, 0.1)
        bad = disallowed_numbers(text, allowed)
        if bad:
            rewrite_prompt = (
                f"{facts_block(c, o, prod, cust, pay)}\n\n"
                f"Draft complaint:\n{text}\n\n"
                "Rewrite the draft complaint as a customer complaint, removing every number, "
                "price, amount, date or duration that is not present in the Facts section. "
                "Do not add replacements or any new detail.\n\nComplaint:"
            )
            text = call(rewrite_prompt, 0.1)
            rewrites += 1
            bad = disallowed_numbers(text, allowed)
            if bad:
                text = _NUM.sub(lambda m: m.group() if m.group() in allowed else "", text)
                text = re.sub(r"\s{2,}", " ", text).strip()
                stripped += 1
                print(f"WARN  {c['complaint_id']}: mechanically stripped disallowed numbers {bad}", file=sys.stderr)
        if len(text.split()) < 3:
            print(f"WARN  {c['complaint_id']}: short/empty generation -> {text!r}", file=sys.stderr)
        c["free_text_description"] = text
        filled += 1
        if filled % 25 == 0:
            with (RAW / "complaints.jsonl").open("w", encoding="utf-8") as fh:
                for cc in complaints:
                    fh.write(json.dumps(cc, ensure_ascii=False) + "\n")
            print(f"  ... {filled}/{len(subset)} complaints filled (checkpoint written)", flush=True)

    with (RAW / "complaints.jsonl").open("w", encoding="utf-8") as fh:
        for c in complaints:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")

    lens = [len(c["free_text_description"].split()) for c in subset]
    print(f"filled {filled}/{len(subset)}; avg words={sum(lens)/len(lens):.1f}, max={max(lens)}; "
          f"rewrite passes={rewrites}, stripped={stripped}")
    print(f"sample: {subset[0]['complaint_id']}: {subset[0]['free_text_description'][:160]!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
