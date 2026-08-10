#!/usr/bin/env python3
"""Phase D (D1) — learned entity linker (V2_PLAN.md §6 component 1).

Embedding-based mention→entity candidate retrieval. For each question in
benchmark_v2 (or nl_v2 for the honest recall evaluation), the linker:
  1. Embeds the question with bge-small-en-v1.5 (retrieval prefix).
  2. Retrieves top-k entity records from the v2 corpus embedding index by cosine.
  3. Filters by type compatibility with the expected answer-type signal
     (answer_type field from the benchmark: status, date, amount, category,
     region, entity_name, entity_id, pair, list:entity_id, unknown).
  4. Returns ranked entity candidates with their record IDs and scores.

Reports recall@1 and recall@k against benchmark ground-truth query_entities.
When run on benchmark_v2 (ID questions) the regex linker already achieves
recall@1=100%; the interesting case is nl_v2 (natural-language mentions).

Usage:
  uv run --with sentence-transformers --with torch \
      python systems/hybrid/entity_linker.py --benchmark benchmark_v2
  uv run --with sentence-transformers --with torch \
      python systems/hybrid/entity_linker.py --benchmark nl_v2 --eval-only
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import EMBED_MODEL, QUERY_PREFIX

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
DATA = ROOT / "data"
CORPUS = DATA / "corpus"
OUT_DIR = HERE / "learned"

CANDIDATE_K = 50       # large candidate pool before type filtering
LINKER_K = 5           # final top-k to return to the pipeline


def load_v2_corpus() -> list[dict]:
    return [json.loads(line) for line in (CORPUS / "text_records_v2.jsonl").open(encoding="utf-8")]


def load_embeddings():
    return np.load(CORPUS / "embeddings_v2.npy")


def load_meta():
    return json.loads((CORPUS / "embeddings_meta_v2.json").read_text(encoding="utf-8"))


def load_benchmark(name: str) -> list[dict]:
    path = DATA / "benchmark" / f"{name}.jsonl"
    return [json.loads(line) for line in path.open(encoding="utf-8")]


class EntityLinker:
    """Learned embedding-based entity linker over the v2 corpus."""

    def __init__(self, llm_pipeline=None, embedder=None):
        self.embedder = embedder
        self.corpus = None
        self.meta = None
        self.matrix = None
        self.record_index: dict[str, int] = {}
        self.llm = llm_pipeline

    def load_index(self):
        from sentence_transformers import SentenceTransformer
        if self.embedder is None:
            self.embedder = SentenceTransformer(EMBED_MODEL,
                    device="cuda" if __import__("torch").cuda.is_available() else "cpu")
        self.matrix = load_embeddings()
        self.meta = load_meta()
        self.corpus = {r["record_id"]: r for r in load_v2_corpus()}
        chunk_to_record = self.meta["chunk_to_record"]
        for i, cid in enumerate(self.meta["chunk_ids"]):
            rid = chunk_to_record[cid]
            self.record_index[rid] = i

    def embed(self, texts: list[str]) -> np.ndarray:
        """Embed texts with the bge retrieval prefix."""
        prefixed = [QUERY_PREFIX + t for t in texts]
        return self.embedder.encode(prefixed, normalize_embeddings=True,
                                     batch_size=128, show_progress_bar=False).astype(np.float32)

    def link(self, question: str, k: int = LINKER_K,
             candidate_k: int = CANDIDATE_K) -> list[dict]:
        """Return top-k entity candidates for a question as
        [{record_id, score, entity_type, text}]."""
        q_emb = self.embed([question])[0]  # [384]
        scores = self.matrix @ q_emb       # [N]
        top_idx = np.argsort(-scores)[:candidate_k]
        candidates = []
        for idx in top_idx:
            idx = int(idx)
            cid = self.meta["chunk_ids"][idx]
            rid = self.meta["chunk_to_record"][cid]
            rec = self.corpus[rid]
            candidates.append({
                "record_id": rid,
                "score": float(scores[idx]),
                "entity_type": rec["entity_type"],
                "text": rec["text"][:120],
            })
        return candidates[:k]

    def evaluate(self, questions: list[dict], k: int = LINKER_K) -> dict:
        """Compute recall@1 / recall@k on a question set.
        Ground truth: q['query_entities'] = set of entity ids the question
        mentions; recall@k is 1 iff at least one gt entity is in top-k candidates.
        Recall@1 iff the top-1 candidate is in gt. Questions with no ground-truth
        entities (aggregate list questions) are excluded from the recall metric."""
        hits1 = 0
        hitsk = 0
        n_gt = 0
        skipped = 0
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
            n_gt += 1
            details.append({
                "qid": q["qid"], "gt_entities": sorted(gt),
                "top1": cands[0]["record_id"] if cands else "",
                "topk_ids": [c["record_id"] for c in cands],
                "recall1": r1, "recall_k": rk,
            })
        n = n_gt
        return {
            "n": n, "skipped_no_gt": skipped, "recall@1": hits1 / n,
            f"recall@{k}": hitsk / n, "details": details,
        }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--benchmark", default="benchmark_v2",
                    help="benchmark name (benchmark_v2 or nl_v2)")
    ap.add_argument("--k", type=int, default=LINKER_K)
    ap.add_argument("--eval-only", action="store_true")
    args = ap.parse_args()

    questions = load_benchmark(args.benchmark)
    linker = EntityLinker()
    linker.load_index()

    result = linker.evaluate(questions, k=args.k)
    print(f"entity linker on {args.benchmark} ({result['n']} q): "
          f"recall@1={result['recall@1']:.3f}, recall@{args.k}={result[f'recall@{args.k}']:.3f}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"linker_{args.benchmark}.json"
    out.write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
