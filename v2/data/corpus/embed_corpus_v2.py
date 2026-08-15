#!/usr/bin/env python3
"""S4 (v2) — embed the v2 text corpus into a vector index (DATA_PIPELINE.md §3).

Mirrors data/corpus/embed_corpus.py for the v2 corpus. Same fixed
experimental-condition model `BAAI/bge-small-en-v1.5` (384-dim). Outputs:
  v2/data/corpus/embeddings.npy
  v2/data/corpus/embeddings_meta.json
`check_sync_v2.py` asserts the graph <-> text <-> vectors 1:1 sync.

Usage:  uv run --with sentence-transformers python v2/data/corpus/embed_corpus_v2.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
CORPUS = HERE / "text_records.jsonl"
OUT_NPY = HERE / "embeddings.npy"
OUT_META = HERE / "embeddings_meta.json"

MODEL = "BAAI/bge-small-en-v1.5"
BATCH = 64


def main() -> int:
    from sentence_transformers import SentenceTransformer

    records = [json.loads(line) for line in CORPUS.open(encoding="utf-8")]
    texts = [r["text"] for r in records]
    chunk_ids = [f"{r['record_id']}:0" for r in records]  # 1:1 chunking, see build_corpus_v2.py

    print(f"loading model {MODEL} ...", flush=True)
    model = SentenceTransformer(MODEL, device="cuda" if __import__("torch").cuda.is_available() else "cpu")

    print(f"embedding {len(texts)} chunks ...", flush=True)
    emb = model.encode(texts, batch_size=BATCH, show_progress_bar=False, normalize_embeddings=True)
    emb = np.asarray(emb, dtype=np.float32)
    assert emb.shape[0] == len(chunk_ids)

    np.save(OUT_NPY, emb)
    meta = {"model": MODEL, "dim": int(emb.shape[1]), "chunk_ids": chunk_ids,
            "chunk_to_record": {cid: rid for cid, rid in zip(chunk_ids, (r["record_id"] for r in records))}}
    OUT_META.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    print(f"shape: {emb.shape}; mean row norm={float(np.linalg.norm(emb, axis=1).mean()):.3f}")
    print(f"wrote {OUT_NPY} ({OUT_NPY.stat().st_size/1e6:.1f} MB) and {OUT_META}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
