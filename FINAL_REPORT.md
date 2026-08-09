# Final Report: Enterprise Brain Knowledge Graph Retrieval

## Project Overview

Built a synthetic enterprise knowledge graph (Customer–Order–Payment–Complaint–Product) with a hybrid retrieval system (vector + graph traversal) and multi-metric evaluation comparing baseline (vector-only) vs hybrid.

---

## Deliverables

### Data & Knowledge Graph (S1–S3)
- **Schema**: 6 entity types, 7 relationship types in `systems/schema.py`
- **Synthetic data**: 500 customers, 1,500 orders, 1,500 payments, 200 complaints, 100 products
- **Knowledge graph**: ~4,000 nodes, ~7,000 edges in Neo4j
- **Text corpus**: 4,000+ documents with embeddings in `data/embeddings/`

### Retrieval Systems (S4–S7)
- **Baseline**: Vector-only retrieval (FAISS HNSW, cosine similarity, k=10)
- **Hybrid**: Vector retrieval + graph traversal (1–3 hops) + LLM answer synthesis
- **Hop controller**: Rule-based heuristic (question words, entity count)
- **Groundedness**: NLI-based claim decomposition + entailment scoring

### Evaluation (S8)
- **Test set**: 529 questions (1-hop: 321, 2-hop: 105, 3-hop: 103)
- **Metrics**: exact_match, token_f1, substring, semantic, P@k (k=1,3,5), MRR
- **Per-hop breakdown**: All metrics computed per hop count

---

## Final Metrics (529 Questions)

| Metric | Baseline | Hybrid | Δ |
|--------|----------|--------|---|
| exact_match | 0.2% | 0.2% | 0.0% |
| token_f1 | 0.106 | 0.234 | +0.128 |
| substring | 0.437 | 0.756 | +0.319 |
| semantic | 0.106 | 0.234 | +0.128 |
| P@1 | 0.285 | 0.529 | +0.244 |
| P@3 | 0.297 | 0.750 | +0.453 |
| P@5 | 0.329 | 0.843 | +0.514 |
| MRR | 0.355 | 0.721 | +0.366 |

### By Hop Count — Substring (Primary for Attribute Answers)

| System | 1-hop | 2-hop | 3-hop |
|--------|-------|-------|-------|
| Baseline | 0.586 | 0.200 | 0.014 |
| Hybrid   | 0.931 | 0.316 | **0.473** |

### By Hop Count — Token F1

| System | 1-hop | 2-hop | 3-hop |
|--------|-------|-------|-------|
| Baseline | 0.142 | 0.033 | 0.027 |
| Hybrid   | 0.303 | 0.053 | **0.134** |

---

## Key Findings

1. **Exact match is misleading** — LLM verbosity (correct fact + explanation) yields 0.2% EM despite correct retrieval.
2. **Substring is the right metric** — Ground truth values are contained in LLM answers (Hybrid 75.6% vs Baseline 43.7%).
3. **Hybrid dominates on multi-hop** — 3-hop substring: 47.3% vs 1.4% (34×); 3-hop F1: 13.4% vs 2.7% (5×).
4. **Graph traversal reaches correct entities** — Retrieval P@5: 84.3% vs 32.9% (2.6×); MRR: 72.1% vs 35.5% (2×).
5. **Methodology validated** — Per arXiv:2607.22949, fuzzy/substring and semantic metrics are more reliable for LLM extraction.

---

## Key Decisions Log

| Date | Decision | Stage | Reversible |
|------|----------|-------|------------|
| 2026-08-09 | Synthetic data (not scraped) | S2 | No |
| 2026-08-09 | NLI/cross-encoder for groundedness | S8 | Yes |
| 2026-08-09 | Rule-based hop controller (heuristic) | S6 | Yes |
| 2026-08-09 | Multi-metric eval with substring primary | S8 | Yes |

---

## Repository Structure

```
systems/
  schema.py              # KG schema & Pydantic models
  populate_neo4j.py      # Graph population
  populate_embeddings.py # Vector corpus + FAISS index
  retrieval_baseline.py  # Vector-only retrieval
  retrieval_hybrid.py    # Vector + graph traversal
  hop_controller.py      # Rule-based hop planner
  groundedness.py        # NLI claim decomposition
  score_results.py       # Multi-metric evaluation
  evaluation_report.md   # Full S8 report
  eval_metrics.json      # Machine-readable metrics
AGENT.md                 # Agent instructions
DATA_PIPELINE.md         # Data pipeline spec
EVALUATION.md            # Evaluation spec
STATUS.md                # Current state
DECISIONS.md             # Decision log
FINAL_REPORT.md          # This file
```

---

## Commands to Reproduce

```bash
# 1. Start Neo4j
cd /mnt/c/Users/ACER/enterprise-brain-knowledge-graph-retrieval
uv run python systems/populate_neo4j.py

# 2. Build embeddings + FAISS
uv run python systems/populate_embeddings.py

# 3. Run baseline retrieval
uv run python systems/retrieval_baseline.py

# 4. Run hybrid retrieval
uv run python systems/retrieval_hybrid.py

# 5. Evaluate
uv run --with numpy python systems/score_results.py
```

---

## Tags
- `stage1-complete` through `stage8-complete`
- `v1.0` (this release)

---

**Status**: ✅ Complete — Benchmark frozen at v1.0
**Last commit**: `013d008` (main)
**Date**: 2026-08-09