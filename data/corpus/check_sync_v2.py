#!/usr/bin/env python3
"""S4 (v2) — sync integrity test (DATA_PIPELINE.md §4). CI-style, fails loudly on drift.

Confirms a strict 1:1 correspondence between three views of the v2 data:
  graph nodes  (data/graph_v2/enterprise_brain_graph.ttl, via eb:source_record_id)
  text corpus  (data/corpus/text_records_v2.jsonl, via record_id)
  vector index (data/corpus/embeddings_v2.npy + embeddings_meta_v2.json, via chunk ids)
plus a content check that the free-text stored on complaint graph nodes is exactly
the text that was embedded. A sync failure here is a build-breaking error.

Usage:  uv run --with rdflib python data/corpus/check_sync_v2.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from rdflib import Graph, Namespace
from rdflib.namespace import RDF

HERE = Path(__file__).resolve().parent.parent
RAW = HERE / "raw_v2"
TTL = HERE / "graph_v2" / "enterprise_brain_graph.ttl"
CORPUS = HERE / "corpus" / "text_records_v2.jsonl"
META = HERE / "corpus" / "embeddings_meta_v2.json"
NPY = HERE / "corpus" / "embeddings_v2.npy"

EB_NS = "https://github.com/divaspoudel0/enterprise-brain-knowledge-graph-retrieval/ontology#"
EB = Namespace(EB_NS)

failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    if cond:
        print(f"PASS  {msg}")
    else:
        print(f"FAIL  {msg}")
        failures.append(msg)


def main() -> int:
    g = Graph()
    g.parse(TTL, format="turtle")

    # 1. graph node ids
    instance_nodes = set()
    for klass in (EB.Product, EB.Customer, EB.Order, EB.Payment, EB.Complaint):
        instance_nodes |= set(g.subjects(RDF.type, klass))
    graph_ids = {str(g.value(u, EB.source_record_id)) for u in instance_nodes}

    # 2. corpus ids
    records = [json.loads(line) for line in CORPUS.open(encoding="utf-8")]
    corpus_ids = {r["record_id"] for r in records}

    # 3. vector index ids (chunk_id -> record_id)
    meta = json.loads(META.read_text(encoding="utf-8"))
    vector_ids = set(meta["chunk_to_record"].values())
    import numpy as np
    emb = np.load(NPY)
    check(emb.shape[0] == len(meta["chunk_ids"]), f"embeddings rows ({emb.shape[0]}) == chunk ids ({len(meta['chunk_ids'])})")

    check(graph_ids == corpus_ids, f"graph ids == corpus ids (graph {len(graph_ids)}, corpus {len(corpus_ids)})")
    check(graph_ids == vector_ids, f"graph ids == vector ids (graph {len(graph_ids)}, vector {len(vector_ids)})")
    check(len(graph_ids) == sum(1 for _ in instance_nodes), "every graph node has a distinct source_record_id")

    # free-text content sync: graph free_text == embedded description text
    corpus_by_id = {r["record_id"]: r for r in records}
    bad_content = []
    for comp_node in g.subjects(RDF.type, EB.Complaint):
        rid = str(g.value(comp_node, EB.source_record_id))
        ft = str(g.value(comp_node, EB.free_text_description) or "")
        rec = corpus_by_id.get(rid)
        if rec is None or rec["entity_type"] != "Complaint" or f"Description: {ft}" not in rec["text"]:
            bad_content.append(rid)
    check(not bad_content, f"complaint free-text on graph nodes == embedded text (bad: {bad_content[:3]})")

    if failures:
        print(f"\n{len(failures)} check(s) FAILED — sync is a build-breaking error")
        return 1
    print(f"\ncheck_sync_v2 OK: {len(graph_ids)} records in 1:1 sync across graph, corpus, and vector index")
    return 0


if __name__ == "__main__":
    sys.exit(main())
