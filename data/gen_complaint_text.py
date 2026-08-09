#!/usr/bin/env python3
"""S2 — LLM enrichment of complaint free-text descriptions (DATA_PIPELINE.md §1.2).

Reads `data/raw/complaints.jsonl` (structured rows, includes the internal
`reason` field), renders one prompt per complaint from the committed template
`data/prompts/complaint_generation.txt` using ONLY facts present in the
structured record, calls the generation model (default
`Qwen/Qwen2.5-7B-Instruct`, override with GENERATION_MODEL), and writes the
filled `free_text_description` back into `complaints.jsonl`.

Contract with the rest of the pipeline:
  - runs AFTER gen_synthetic.py and BEFORE verify_data.py;
  - verify_data.py fails until every complaint has non-empty, distinct text;
  - the prompt template, model name, temperature and seed are committed / logged
    so the enrichment is reproducible (DATA_PIPELINE.md §1.2, §6).

Usage:
  uv run --with faker python data/gen_complaint_text.py --dry-run   # print prompts only
  uv run python data/gen_complaint_text.py --limit 5                # smoke test
  uv run python data/gen_complaint_text.py                          # full run (needs GPU)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
PROMPTS = HERE / "prompts"
TEMPLATE = (PROMPTS / "complaint_generation.txt").read_text(encoding="utf-8")

DEFAULT_MODEL = "Qwen/Qwen2.5-7B-Instruct"
TEMPERATURE = 0.3
TOP_P = 0.9
MAX_NEW_TOKENS = 150
SEED = 42


def load(name: str) -> list[dict]:
    return [json.loads(line) for line in (RAW / name).open(encoding="utf-8")]


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
    prompts = [build_prompt(c, orders[c["order_id"]], products[orders[c["order_id"]]["product_id"]],
                            customers[c["customer_id"]], payments[c["order_id"]]) for c in subset]

    if args.dry_run:
        for c, p in zip(subset, prompts):
            print(f"===== {c['complaint_id']} =====")
            print(p)
        print(f"DRY RUN: {len(subset)} prompts rendered from committed template; no model call.")
        return 0

    if not any(complaints):  # pragma: no cover
        print("FATAL: no complaints loaded", file=sys.stderr)
        return 1

    import torch
    from transformers import pipeline

    torch.manual_seed(SEED)
    print(f"loading model {DEFAULT_MODEL} ...", flush=True)
    gen = pipeline("text-generation", model=DEFAULT_MODEL, torch_dtype="bfloat16", device_map="auto")

    filled = 0
    for c, prompt in zip(subset, prompts):
        out = gen(prompt, max_new_tokens=MAX_NEW_TOKENS, do_sample=True,
                  temperature=TEMPERATURE, top_p=TOP_P)[0]["generated_text"]
        text = out.split("Complaint:")[-1].strip()
        if len(text.split()) < 10:
            out = gen(prompt, max_new_tokens=MAX_NEW_TOKENS, do_sample=True,
                      temperature=0.1, top_p=1.0)[0]["generated_text"]
            text = out.split("Complaint:")[-1].strip()
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
    print(f"filled {filled}/{len(subset)} complaints; avg words={sum(lens)/len(lens):.1f}, max={max(lens)}")
    print(f"sample: {subset[0]['complaint_id']}: {subset[0]['free_text_description'][:160]!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
