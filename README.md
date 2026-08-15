# Enterprise Brain — Knowledge Graph-Augmented Retrieval for Explainable Multi-Hop QA

A synthetic enterprise knowledge graph (Customer–Order–Payment–Complaint–Product) with
**two retrieval systems under fixed experimental conditions** — a vector-only baseline and a
hybrid (vector + graph traversal) system — evaluated with a multi-metric protocol on a
verifiable, graph-derived question-answer benchmark.

> Academic project: Tribhuvan University, Pulchowk Campus, AIML cluster.
> **Start here.** The working instruction docs live in [`docs/`](docs/).

## Repository layout

The repo is split into **two frozen-and-versioned trees plus shared docs** so each version can
be viewed, reproduced, and audited independently.

| Path | Contents |
|---|---|
| [`docs/`](docs/) | Version-agnostic docs: `AGENT.md` (master instructions), `CHECKPOINTING.md` (commit discipline), `DATA_PIPELINE.md` (data spec), `EVALUATION.md` (protocol + definition of done), `DECISIONS.md` (decision log), `STATUS.md` (current state), `BEST_PRACTICES.md` |
| [`v1/`](v1/) | **v1 (S1–S9.5, tag `v1.0`)** — ontology, data, benchmark, baseline + hybrid systems, eval artifacts, and the v1 final report |
| [`v2/`](v2/) | **v2 (Phases A–E)** — ontology v2, data v2 (temporal + larger), benchmark v2 (T1/T2/T3 testbeds), learnable pipeline (hybrid-learned vs hybrid-rule), groundedness + query interface, eval artifacts, and run logs |

## Canonical structure

```
enterprise-brain-knowledge-graph-retrieval/
├── README.md                     # this file
├── docs/                         # version-agnostic guidance
│   ├── AGENT.md  CHECKPOINTING.md  DATA_PIPELINE.md  EVALUATION.md
│   ├── DECISIONS.md  STATUS.md  BEST_PRACTICES.md
├── v1/                           # frozen v1 (S1–S9.5)
│   ├── FINAL_REPORT.md           # v1 report (corrected 2026-08-10)
│   ├── ontology/                 # enterprise_brain.ttl + example_instances.ttl + validator
│   ├── data/
│   │   ├── raw/  graph/  prompts/  corpus/  benchmark/    # data products (benchmark.jsonl frozen)
│   │   └── gen_synthetic.py gen_complaint_text.py populate_graph.py verify_data.py verify_graph.py
│   ├── systems/
│   │   ├── common.py  score_results.py  prompts/
│   │   ├── baseline/run_baseline.py
│   │   └── hybrid/run_hybrid.py
│   └── eval/                     # results_baseline*.json, results_hybrid*.json,
│                                 # eval_metrics.json, evaluation_report.md
└── v2/                           # v2 (Phases A–E, D1/D2 done; Phase F eval pending)
    ├── V2_PLAN.md                # v2 enhancement plan
    ├── ontology/                 # enterprise_brain_v2.ttl + validator (uses v1 example instances)
    ├── data/
    │   ├── raw/  graph/  prompts/  corpus/  benchmark/    # temporal data v2 (benchmark.jsonl frozen)
    │   └── gen_synthetic_v2.py … verify_graph_v2.py
    ├── systems/
    │   ├── common.py  prompts/
    │   └── hybrid/               # entity_linker, hop_controller, relation_planner, groundedness,
    │                             # run_hybrid_learned, run_hybrid_rule, run_d2_groundedness,
    │                             # query_interface, prepare_human_rating_sheet, learned/
    ├── eval/                     # results_hybrid_learned.json, results_hybrid_rule.json,
    │                             # learned_eval*.json, groundedness_details.json, learned_contexts.json
    └── logs/                     # run logs (gen_complaint_v2.log, verify_graph_v2.log)
```

## Quick orientation

- **Current state** of the project: [`docs/STATUS.md`](docs/STATUS.md) — the single source of truth.
- **v1** is complete and frozen (S1–S9.5, structured-prompt headline EM: baseline 45.9% vs
  hybrid 71.6%): [`v1/FINAL_REPORT.md`](v1/FINAL_REPORT.md).
- **v2** enhancement plan (approved 2026-08-10): [`v2/V2_PLAN.md`](v2/V2_PLAN.md). Phases A–E
  done; Phase F evaluation matrix and public release pending.
- **Why the split** (v1 integrity gaps that motivated v2): `V2_PLAN.md §1`.

## Reproducing

Per-version "Commands to Reproduce" are at the bottom of the version's report/plan:
- v1: [`v1/FINAL_REPORT.md`](v1/FINAL_REPORT.md)
- v2: [`v2/V2_PLAN.md`](v2/V2_PLAN.md)

Every run command in the repo uses `Path(__file__)`-relative resolution, so scripts run from
their own version tree (`python v1/…`, `python v2/…`).
