#!/usr/bin/env python3
"""S4 — embed the text corpus into a vector index (DATA_PIPELINE.md §3).

Loads data/corpus/text_records.jsonl and embeds every chunk with the fixed
experimental-condition model `BAAI/bge-small-en-v1.5` (384-dim, AGENT.md §2 /
DECISIONS.md 2026-08-09). Document embeddings are plain; at query time the bge
retrieval-query prefix is applied on the query side only (standard bge usage).

Outputs (committed; ~4 MB, under CHECKPOINTING.md §3's size line):
  data/corpus/embeddings.npy        float32 matrix, one row per chunk
  data/corpus/embeddings_meta.json  {chunk_ids: [...], chunk_id -> record_id map}
The meta chunk order == npy row order. `check_sync.py` asserts the graph <-> text
1:1 sync using the record_ids.

Usage:  uv run --with sentence-transformers python data/corpus/embed_corpus.py
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
    chunk_ids = [f"{r['record_id']}:0" for r in records]  # 1:1 chunking, see build_corpus.py

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
