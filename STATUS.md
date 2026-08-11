# STATUS

> This file is the single source of truth for "where the project currently stands."
> Update it on every commit — see `CHECKPOINTING.md` §5. A human (or a fresh agent
> session after sandbox loss) should be able to read only this file and know exactly
> what to do next, without digging through commit history or logs.

Last updated: 2026-08-11 (Phase D D1 DONE + D2 S8/S10 built; groundedness eval pending on molab)
Current stage: v2 Phase D (D1 learnable pipeline) DONE; Phase E (D2 S8 groundedness + S10 interface + human study) in progress
Last commit: a51aa3b
Last verified: D1 results committed (bdcb5c8) — learned EM 0.496/F1 0.512 vs rule 0.399/0.422 on benchmark_v2 test (278 q); S8/S10 code committed (a51aa3b)
Next planned action: run S8 groundedness eval (`run_d2_groundedness.py`) + verify S10 interface on molab once the sandbox is reachable; then fill the human rating sheet (human-in-the-loop)
Blockers / open questions: molab sandbox `sb-a54b5f4e98907401.sb.molab.run` unreachable since 2026-08-11 (all GPU work blocked: D2 groundedness NLI, S10 verification). Human rating sheet prepared (20 items) and AWAITS the two human annotators (user + peer) — human-in-the-loop blocker per EVALUATION.md §3.

V2 directions (all approved): D5 schema & data v2 (2,500+ customers), D3 temporal testbed,
D4 answerability testbed, D1 learnable pipeline (linking, hop controller, path planning),
D2 S8 groundedness + S10 query interface + human study; public pre-defense release; publication after defense.
Full detail: V2_PLAN.md.

Environment (molab.marimo.io sandbox, confirmed 2026-08-10): NVIDIA RTX PRO 6000 Blackwell Server Edition, 102 GB VRAM, CUDA 13.0 (torch 2.11.0+cu130); 171.8 GB RAM, 20 CPUs, Python 3.13.11, git+uv present (gh absent); ephemeral by design. NOTE: unreachable as of 2026-08-11.

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

Phase D (D1) state (2026-08-11) — learnable pipeline DONE:
  - entity_linker.py (multilingual-e5 mention catalog; bge can't embed Devanagari) — combined
    recall@5 0.961 vs regex-only 0.568; hop_controller.py MLP 0.986 vs rule 0.791 vs oracle 1.0
  - relation_planner.py (LLM chain proposal + ontology validation + retry + heuristic fallback;
    walk_full for provenance); run_hybrid_learned.py (plan-then-execute) and run_hybrid_rule_v2.py
  - End-to-end test 278: learned EM 0.496 / F1 0.512 vs rule 0.399 / 0.422; planned paths 1.18/q
    vs 119.2/q. Full tables in V2_PLAN §6 and d1-learnable-pipeline-report.md.
  - Caveat: T2 "as of"/"changed on" sub-templates embed the answer in the question (gold = prior
    status) while context shows current — biases both systems (learned 0.154 vs rule 0.200).

Phase E (D2) state (2026-08-11):
  - S8 groundedness.py built (NLI claim-decomposition, cross-encoder/nli-deberta-v3-base, logged
    in DECISIONS.md) + run_d2_groundedness.py (replays retrieval, scores frozen D1 answers)
    — RUN PENDING on molab.
  - S10 query_interface.py built (CLI + optional Gradio; answer + evidence chunks + provenance
    path + plan-as-explanation) — VERIFICATION PENDING on molab.
  - S7.3 human rating sheet PREPARED: 20 multi-hop items (10 learned + 10 rule, blind/shuffled)
    at artifacts human_evidence_path_rating_sheet.md/.csv/.json — AWAITS human annotators.
