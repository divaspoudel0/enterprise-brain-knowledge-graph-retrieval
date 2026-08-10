#!/usr/bin/env python3
"""Phase D (D1) — learned entity linker (V2_PLAN.md §6 component 1).

Mention→entity linking over the v2 entities. The linker keeps two surfaces:

  - ID references (order/payment/complaint IDs quoted like reference numbers) are
    resolved by the exact-id extractor — realistic, since you quote an order or
    complaint number in the real world.
  - Natural-language mentions (product names/categories, customer names in
    Devanagari, regions) are resolved by a LEARNED multilingual embedding model
    (intfloat/multilingual-e5-small) over a mention catalog built from raw_v2,
    followed by cosine top-k retrieval. The English-only bge-small-en-v1.5 cannot
    embed Devanagari customer names, which is why the linker uses its own
    multilingual embedder.

Evaluation reports recall@1/recall@k for the full set and for the mentions-only
subset (natural-language surfaces the v1 regex cannot parse) — this is the
honest real-world utility measure (V2_PLAN §6 evaluation claims).

Usage:
  uv run --with sentence-transformers --with torch \
      python systems/hybrid/entity_linker.py --benchmark nl_v2
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw_v2"
OUT_DIR = HERE / "learned"

ID_RE = re.compile(r"\b(c_\d+|o_\d{5}|p_\d{4}|pay_\d{5}|comp_\d{4})\b")
LINKER_K = 5

# multilingual embedder for mention matching (Devanagari customer names, EN names)
EMBED_MODEL = "intfloat/multilingual-e5-small"
QUERY_PREFIX = "query: "
PASSAGE_PREFIX = "passage: "


def load_raw(name: str) -> list[dict]:
    return [json.loads(line) for line in (RAW / name).open(encoding="utf-8")]


class EntityLinker:
    """Learned multilingual mention→entity linker over raw_v2."""

    def __init__(self, embedder=None):
        self.embedder = embedder
        self.entries: list[dict] = []      # {record_id, entity_type, texts}
        self.entry_rows: dict[str, list[int]] = {}
        self.matrix: np.ndarray | None = None
        self.texts: list[str] = []

    def load_index(self):
        from sentence_transformers import SentenceTransformer
        if self.embedder is None:
            self.embedder = SentenceTransformer(EMBED_MODEL,
                    device="cuda" if __import__("torch").cuda.is_available() else "cpu")
        products = load_raw("products.jsonl")
        customers = load_raw("customers.jsonl")
        self.texts, self.entries = [], []
        row = 0
        for p in products:
            self.texts += [
                PASSAGE_PREFIX + f"product {p['name']}",
                PASSAGE_PREFIX + f"{p['category']} product",
                PASSAGE_PREFIX + f"product {p['product_id']} {p['name']}",
            ]
            self.entries += [
                {"record_id": p["product_id"], "entity_type": "Product"},
                {"record_id": p["product_id"], "entity_type": "Product"},
                {"record_id": p["product_id"], "entity_type": "Product"},
            ]
            for _ in range(3):
                self.entry_rows.setdefault("Product", []).append(row)
                row += 1
        for c in customers:
            self.texts.append(PASSAGE_PREFIX + f"customer {c['name']}")
            self.entries.append({"record_id": c["customer_id"], "entity_type": "Customer"})
            self.entry_rows.setdefault("Customer", []).append(row)
            row += 1
        self.matrix = self.embedder.encode(self.texts, normalize_embeddings=True,
                                           batch_size=256, show_progress_bar=False).astype(np.float32)

    def mentioned_types(self, question: str) -> list[str]:
        q = question.lower()
        hits = []
        if "product" in q or "electronics" in q or "home & kitchen" in q or "category" in q:
            hits.append("Product")
        if "customer" in q or "region" in q or "sign" in q:
            hits.append("Customer")
        return hits or ["Product", "Customer"]

    def link(self, question: str, k: int = LINKER_K) -> list[dict]:
        q_emb = self.embedder.encode([QUERY_PREFIX + question], normalize_embeddings=True)[0]
        scores_all = self.matrix @ q_emb
        types = self.mentioned_types(question)
        merged = []
        for t in types:
            rows = self.entry_rows.get(t, [])
            if not rows:
                continue
            sub = scores_all[rows]
            order = np.argsort(-sub)[: k * 3]
            for j in order:
                idx = rows[int(j)]
                merged.append((float(sub[j]), self.entries[idx]["record_id"], t))
        merged.sort(key=lambda x: -x[0])
        out, seen = [], set()
        for score, rid, t in merged:
            if rid in seen:
                continue
            seen.add(rid)
            out.append({"record_id": rid, "score": score, "entity_type": t})
            if len(out) >= k:
                break
        return out

    def evaluate(self, questions: list[dict], k: int = LINKER_K) -> dict:
        hits1 = hitsk = 0
        regex_h1 = regex_hk = 0
        m_h1 = m_hk = m_reghk = 0
        n_gt = n_mentions = skipped = 0
        details = []
        for q in questions:
            gt = set(q["query_entities"])
            if not gt:
                skipped += 1
                continue
            cands = self.link(q["question"], k=k)
            cand_ids = {c["record_id"] for c in cands}
            r1 = bool(gt & {cands[0]["record_id"] if cands else ""})
            rk = bool(gt & cand_ids)
            hits1 += r1
            hitsk += rk

            re_ids = set(ID_RE.findall(q["question"]))
            re1 = bool(gt & {sorted(re_ids)[0] if re_ids else ""})
            rek = bool(gt & re_ids)
            regex_h1 += re1
            regex_hk += rek

            if q.get("mentions_only"):
                n_mentions += 1
                m_h1 += r1
                m_hk += rk
                m_reghk += rek
            n_gt += 1
            details.append({
                "qid": q["qid"], "gt_entities": sorted(gt),
                "top1": cands[0]["record_id"] if cands else "",
                "topk_ids": [c["record_id"] for c in cands],
                "regex_ids": sorted(re_ids), "recall1": r1, "recall_k": rk,
                "regex_recall1": re1, "regex_recall_k": rek,
            })
        n = n_gt
        return {
            "n": n, "skipped_no_gt": skipped,
            "recall@1": hits1 / n, f"recall@{k}": hitsk / n,
            "regex_recall@1": regex_h1 / n, f"regex_recall@{k}": regex_hk / n,
            "mentions_only": {
                "n": n_mentions,
                "recall@1": m_h1 / n_mentions if n_mentions else 0,
                f"recall@{k}": m_hk / n_mentions if n_mentions else 0,
                f"regex_recall@{k}": m_reghk / n_mentions if n_mentions else 0,
            },
            "details": details,
        }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--benchmark", default="nl_v2")
    ap.add_argument("--k", type=int, default=LINKER_K)
    args = ap.parse_args()

    questions = [json.loads(line) for line in (DATA / "benchmark" / f"{args.benchmark}.jsonl").open(encoding="utf-8")]
    linker = EntityLinker()
    linker.load_index()

    result = linker.evaluate(questions, k=args.k)
    print(f"entity linker on {args.benchmark} ({result['n']} q): "
          f"recall@1={result['recall@1']:.3f}, recall@{args.k}={result[f'recall@{args.k}']:.3f}")
    print(f"  regex baseline: recall@1={result['regex_recall@1']:.3f}, "
          f"recall@{args.k}={result[f'regex_recall@{args.k}']:.3f}")
    mo = result["mentions_only"]
    print(f"  mentions-only ({mo['n']} q): learned recall@1={mo['recall@1']:.3f}, "
          f"learned recall@{args.k}={mo[f'recall@{args.k}']:.3f}, "
          f"regex recall@{args.k}={mo[f'regex_recall@{args.k}']:.3f}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"linker_{args.benchmark}.json"
    out.write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
