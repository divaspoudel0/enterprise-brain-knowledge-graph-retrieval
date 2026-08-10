# STATUS

> This file is the single source of truth for "where the project currently stands."
> Update it on every commit — see `CHECKPOINTING.md` §5. A human (or a fresh agent
> session after sandbox loss) should be able to read only this file and know exactly
> what to do next, without digging through commit history or logs.

Last updated: 2026-08-10 (Phase B complete — graph v2, LLM free-text, corpus, embeddings all green)
Current stage: v2 Phase B (data pipeline) DONE; next Phase C — benchmark v2 (T1/T2/T3 testbeds)
Last commit: 847785f
Last verified: verify_graph_v2 5170 PASS / 0 FAIL; check_sync_v2 18998 records 1:1 across graph+corpus+vectors (2026-08-10)
Next planned action: Phase C — write data/benchmark/generate_benchmark_v2.py (T1 multi-hop ~800, T2 temporal ~300, T3 answerability ~200) + verifier; then D1 learnable pipeline (Phase D)
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
