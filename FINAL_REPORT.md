# Final Report (v1): Enterprise Brain Knowledge Graph Retrieval

> This is the **v1 final report** (S1–S9.5), written 2026-08-09 and **corrected 2026-08-10**
> against verified repo facts. A v2 report will be produced at the end of the v2 enhancement
> plan (see `V2_PLAN.md`). All numbers below are recomputed from committed artifacts
> (`systems/eval_metrics.json`, `data/benchmark/benchmark_v1.jsonl`).

## Project Overview

A synthetic enterprise knowledge graph (Customer–Order–Payment–Complaint–Product) with two
retrieval systems under fixed experimental conditions — a vector-only baseline and a hybrid
(vector + graph traversal) system — evaluated with a multi-metric protocol on a 529-question
benchmark with ground truth derived from the data rows (and mirrored 1:1 by the RDF graph).

---

## Deliverables (verified)

### Data & Knowledge Graph (S1–S3)
- **Ontology**: OWL 2 DL (`ontology/enterprise_brain.ttl`), 5 classes, 10 object properties
  (5 inverse pairs), 12 datatype properties, cardinality restrictions on Order/Payment/Complaint.
- **Synthetic data**: 400 customers, 926 orders, 926 payments, 250 complaints, 60 products
  (6 categories × 10). Config in `data/raw/generation_config.json`.
- **Knowledge graph**: RDF graph (`data/graph/enterprise_brain_graph.ttl`, RDFLib — not Neo4j),
  ~2,562 instance nodes, ~5,800 undirected object-property edges (edges stored in both
  directions of every declared inverse pair), with `eb:source_record_id` provenance on nodes
  and reified statements on edges.
- **Text corpus**: 2,562 text records (`data/corpus/text_records.jsonl`) — LLM-generated
  complaint descriptions plus deterministic natural-language records for every entity — chunked
  and embedded with `BAAI/bge-small-en-v1.5` (384-d) into a committed vector index.

### Retrieval Systems (S4–S7)
- **Baseline** (`systems/baseline/run_baseline.py`): vector-only retrieval, top-k cosine over the
  committed index, k=5, answer via `Qwen/Qwen2.5-7B-Instruct` (greedy).
- **Hybrid** (`systems/hybrid/run_hybrid.py`): regex entity linking + rule-based hop controller
  (1–3 hops) + deterministic SPARQL traversal over the graph + linear fusion
  (0.8 × graph_score + 0.2 × vector_similarity) + same answer LLM.
- **Shared fixed conditions** (`systems/common.py`): identical embedding model, LLM, prompt
  template, benchmark, and TOP_K for both systems.
- **Answer format** (S9.5): structured prompt (`predicted_answer` / `explanation`) — free-text
  answering was shown to make exact-match evaluation meaningless (see Key Findings).

### Evaluation (S8)
- **Test set**: 529 questions (1-hop: 360, 2-hop: 95, 3-hop: 74).
- **Metrics**: exact_match, token_f1, substring, semantic cosine, P@k (k=1,3,5), MRR, all broken
  down per hop count and per template family.
- Raw per-question traces committed (`systems/*/results_*_v1*.json`); aggregates recomputed from
  those traces by `systems/score_results.py`.

---

## Final Metrics — Structured Answer Format (S9.5, 529 Questions)

The S9.5 structured prompt is the metric head for v1 (see Key Findings #1 for why free-text is
not reported as a headline).

| Metric | Baseline | Hybrid | Δ |
|--------|----------|--------|---|
| exact_match | 45.9% | 71.6% | +25.7 |
| token_f1 | 0.497 | 0.760 | +0.263 |
| substring | 0.465 | 0.743 | +0.278 |
| semantic | 0.782 | 0.887 | +0.105 |
| P@1 | 0.285 | 0.529 | +0.244 |
| P@3 | 0.297 | 0.750 | +0.453 |
| P@5 | 0.329 | 0.843 | +0.514 |
| MRR | 0.355 | 0.721 | +0.366 |

> Retrieval metrics (P@k, MRR) are format-independent and identical to the free-text run.
> Generation metrics (EM, token-F1, substring, semantic) are from the structured run.
> Full per-hop and per-template breakdowns: `systems/evaluation_report.md`, `systems/eval_metrics.json`.

### By Hop Count — Exact Match (Structured)

| System | 1-hop | 2-hop | 3-hop |
|--------|-------|-------|-------|
| Baseline | 57.5% | 26.3% | 14.9% |
| Hybrid   | 86.7% | 28.4% | **54.1%** |

### By Hop Count — Token F1 (Structured)

| System | 1-hop | 2-hop | 3-hop |
|--------|-------|-------|-------|
| Baseline | 0.580 | 0.314 | 0.333 |
| Hybrid   | 0.891 | 0.293 | **0.721** |

> Values: `systems/eval_metrics.json` → `baseline_structured` / `hybrid_structured`, `by_hop`.

---

## Key Findings

1. **Answer format dominates exact-match evaluation.** With identical retrieval and the same
   LLM, switching from free-text to a structured `predicted_answer`/`explanation` format moved
   hybrid EM from **0.2% → 71.6%** (baseline 0.2% → 45.9%). Free-text EM conflates generation
   verbosity with retrieval quality and is not a meaningful headline metric for this task.
2. **Substring vs exact-match** — v1 free-text substring: Hybrid 75.6% vs Baseline 43.7%
   (headline in the original v1 report); structured substring: 74.3% vs 46.5%. Substring is more
   forgiving of answer-format noise but still reflects retrieval quality.
3. **Hybrid dominates on multi-hop** — 3-hop structured EM 54.1% vs 14.9% (~3.6×); 3-hop token F1
   0.721 vs 0.333 (~2.2×). The gap is largest at 1-hop for generation metrics (86.7% vs 57.5% EM).
4. **Graph traversal reaches the correct entities** — retrieval P@5 84.3% vs 32.9% (2.6×);
   MRR 72.1% vs 35.5% (2×). Format-independent.
5. **Format failures are residual** — ~3–4% of structured answers emit only an explanation with
   no parseable `predicted_answer`; flagged as future work (few-shot exemplars).

---

## Known limitations (v1) — fixed by v2

- Entity linking is a regex over exact IDs; it works only because v1 benchmark questions embed
  IDs verbatim. v2 replaces it with a learned linker (V2_PLAN D1).
- The hop controller is a rule-based regex cascade; v2 replaces it with a learned classifier.
- Graph traversal brute-forces all property chains (10^h); v2 introduces relation-path planning.
- S8 groundedness scorer and S10 query interface were decided but **not built in v1**; they are
  v2 deliverables (V2_PLAN D2).
- Benchmark v1 has no temporal questions and no unanswerable (negative-rejection) questions;
  v2 adds both testbeds (V2_PLAN D3/D4).

---

## Key Decisions Log (summary — full log in `DECISIONS.md`)

| Date | Decision | Stage | Reversible |
|------|----------|-------|------------|
| 2026-08-09 | Synthetic data (not scraped) | S2 | No |
| 2026-08-09 | OWL 2 DL Turtle ontology, RDFLib toolchain | S1 | Yes (pre-S5) |
| 2026-08-09 | Dataset scale: 400 customers / 926 orders / 926 payments / 250 complaints / 60 products | S2 | Yes (pre-S5) |
| 2026-08-09 | Qwen/Qwen2.5-7B-Instruct = answer LLM (also complaint free-text generator) | S6 | Yes |
| 2026-08-09 | bge-small-en-v1.5 embedding model (both systems) | S4 | Yes |
| 2026-08-09 | Groundedness scorer: NLI/cross-encoder (MNLI/ANLI) | S8 | Yes — **built in v2** |
| 2026-08-09 | Rule-based hop controller (learned deferred) | S6/S7 | Yes — **learned in v2** |
| 2026-08-09 | Multi-metric eval, substring primary for attribute answers | S8 | Yes |
| 2026-08-10 | Structured answer prompt (predicted_answer/explanation) | S9.5 | Yes |
| 2026-08-10 | v2 enhancement plan approved (all 5 directions) | v2 | Yes |

---

## Repository Structure (actual, verified 2026-08-10)

```
AGENT.md                    # Master instructions (v1 execution)
CHECKPOINTING.md            # Commit/checkpoint protocol
DATA_PIPELINE.md            # Data acquisition & sync spec
DECISIONS.md                # Decision log (v1 + v2)
EVALUATION.md               # Comparison protocol & metrics
FINAL_REPORT.md             # This file (v1 report)
STATUS.md                   # Current state (v2 plan active)
V2_PLAN.md                  # v2 enhancement plan (approved)
ontology/
  enterprise_brain.ttl      # OWL 2 DL schema (v1)
  example_instances.ttl     # Sample instances
  validate_ontology.py      # S1 done-gate
data/
  gen_synthetic.py          # S2 structured generator
  gen_complaint_text.py     # S2 free-text (LLM) generator
  populate_graph.py         # S3 RDF graph population
  verify_data.py / verify_graph.py
  raw/                      # v1 entity rows + generation_config + planted_patterns
  graph/enterprise_brain_graph.ttl
  corpus/                   # text_records.jsonl, embeddings.npy, embeddings_meta.json
  benchmark/                # benchmark_v1.jsonl (frozen), generate/verify scripts
systems/
  common.py                 # Shared fixed conditions + LLM/embedding/context helpers
  baseline/run_baseline.py  # S6 vector-only RAG
  hybrid/run_hybrid.py      # S7 hybrid retriever
  score_results.py          # S8 multi-metric evaluation
  prompts/                  # answer templates (free-text v1, structured S9.5)
  evaluation_report.md / eval_metrics.json
```

---

## Commands to Reproduce (v1)

```bash
# 1. Generate + verify data (structured), then free-text
uv run --with faker python data/gen_synthetic.py
uv run --with torch --with transformers python data/gen_complaint_text.py
uv run python data/verify_data.py

# 2. Populate + verify graph
uv run --with rdflib python data/populate_graph.py
uv run --with rdflib python data/verify_graph.py

# 3. Build + embed corpus
uv run python data/corpus/build_corpus.py
uv run --with sentence-transformers --with torch python data/corpus/embed_corpus.py

# 4. Generate + verify benchmark
uv run python data/benchmark/generate_benchmark.py
uv run python data/benchmark/verify_benchmark.py

# 5. Run both systems (structured; free-text arm historical only)
uv run --with sentence-transformers --with torch --with transformers python systems/baseline/run_baseline.py --structured
uv run --with sentence-transformers --with torch --with transformers --with rdflib python systems/hybrid/run_hybrid.py --structured

# 6. Evaluate
uv run --with numpy --with sentence-transformers python systems/score_results.py
```

---

## Tags
- `stage1-complete` … `stage8-complete`, `v1.0` (v1 release)

---

**Status (v1)**: ✅ Complete and frozen (S1–S9.5). **v2 plan active** — see `V2_PLAN.md`.
**Last commit**: `e7a26f9` (v1 HEAD)
**Date**: v1 report 2026-08-09, corrected 2026-08-10
