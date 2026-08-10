# STATUS

> This file is the single source of truth for "where the project currently stands."
> Update it on every commit — see `CHECKPOINTING.md` §5. A human (or a fresh agent
> session after sandbox loss) should be able to read only this file and know exactly
> what to do next, without digging through commit history or logs.

Last updated: 2026-08-10 (Phase C complete — benchmark v2 verified; next Phase D learnable pipeline)
Current stage: v2 Phase C (benchmark v2) DONE; next Phase D — D1 learnable pipeline (linking, hop controller, relation-path planning)
Last commit: ed86499
Last verified: verify_benchmark_v2 — 1385 questions (T1 885 / T2 300 / T3 200), all answerable ground truths independently re-derived from graph_v2, all unanswerable provably empty; splits train 969 / val 138 / test 278
Next planned action: Phase D — build learnable components per V2_PLAN §6: learned entity linker (mention→entity), learned hop controller, relation-path planner for traversal; train only on benchmark_v2 train split
Blockers / open questions: none

V2 directions (all approved): D5 schema & data v2 (2,500+ customers), D3 temporal testbed,
D4 answerability testbed, D1 learnable pipeline (linking, hop controller, path planning),
D2 S8 groundedness + S10 query interface + human study; public pre-defense release; publication after defense.
Full detail: V2_PLAN.md.

Environment (molab.marimo.io sandbox, confirmed 2026-08-10): NVIDIA RTX PRO 6000 Blackwell Server Edition, 102 GB VRAM, CUDA 13.0 (torch 2.11.0+cu130); 171.8 GB RAM, 20 CPUs, Python 3.13.11, git+uv present (gh absent); ephemeral by design.

Phase B pipeline state (2026-08-10):
  - raw_v2: 120 products / 2,500 customers / 7,589 orders / 7,589 payments / 1,200 complaints (verify_data_v2 40/40 PASS)
  - graph_v2: enterprise_brain_graph.ttl — 459,175 triples, temporal fields + atRisk materialized (verify_graph_v2 5170/0 PASS, P1-P5 SPARQL)
  - complaint free-text: 1,200/1,200 LLM-generated (Qwen2.5-7B-Instruct on molab; 380 rewrite passes, 135 stripped)
  - corpus_v2: 18,998 records; embeddings_v2.npy 18,998 x 384 (bge-small-en-v1.5)
  - check_sync_v2: 18,998 records in 1:1 sync across graph, corpus, and vector index

Phase C state (2026-08-10):
  - benchmark_v2.jsonl: 1,385 questions, all verified (verify_benchmark_v2 OK)
  - T1 multi-hop 885 (1/2/3-hop + P1/P2/P3/P5 + aggregates), T2 temporal 300 (as-of status,
    status-change dates, complaint ordering, earliest/latest order), T3 answerability 200 (entity
    absent / relation absent / pattern absent → "I don't know")
  - splits: train 969 / val 138 / test 278 (70/10/20)
