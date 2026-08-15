# STATUS

> This file is the single source of truth for "where the project currently stands."
> Update it on every commit — see `CHECKPOINTING.md` §5. A human (or a fresh agent
> session after sandbox loss) should be able to read only this file and know exactly
> what to do next, without digging through commit history or logs.
>
> **Repo layout (2026-08-15):** restructured into versioned trees — `v1/` (frozen v1,
> S1–S9.5) and `v2/` (v2 plan active), plus shared docs in `docs/`. All paths below
> point into those trees; the canonical structure is in `README.md`.

Last updated: 2026-08-15 (repo restructured into v1/ + v2/ trees; all paths/docs updated)
Current stage: v2 Phase E (D2 S8/S10/human study) DONE; next Phase F — evaluation v2 (molab), then G public release
Last commit: 41cc689 (restructure: v1/v2 trees + docs/; branch chore/repo-restructure — merge into main)
Last verified: S8 groundedness final on the v2 benchmark test (LLM-planner evidence, RAGAS max-entailment): all 0.777, answerable claims 0.657, T3 correct "I don't know" 0.556; S10 interface verified on molab (provenance paths render). D1 results regenerated with separate explanation field (learned EM 0.504 / rule 0.403)
Next planned action: Phase F — evaluation v2 matrix (baseline vs hybrid-rule vs hybrid-learned), ablations, temporal + answerability testbed metrics; then public release
Blockers / open questions: human rating sheet AWAITS the two human annotators (user + peer) — human-in-the-loop blocker per docs/EVALUATION.md §3. S8 NLI residual misses exact-value entailment in structured records (honest caveat).

V2 directions (all approved): D5 schema & data v2 (2,500+ customers), D3 temporal testbed,
D4 answerability testbed, D1 learnable pipeline (linking, hop controller, path planning),
D2 S8 groundedness + S10 query interface + human study; public pre-defense release; publication after defense.
Full detail: v2/V2_PLAN.md.

Environment (molab.marimo.io sandbox, confirmed 2026-08-10; REACHED again 2026-08-14 at new URL sb-2fc6f753bf56c67e): NVIDIA RTX PRO 6000 Blackwell Server Edition, 102 GB VRAM, CUDA 13.0 (torch 2.11.0+cu130); 171.8 GB RAM, 20 CPUs, Python 3.13.11, git+uv present; ephemeral by design.

Phase B pipeline state (2026-08-10):
  - v2/data/raw: 120 products / 2,500 customers / 7,589 orders / 7,589 payments / 1,200 complaints (v2/data/verify_data_v2.py 40/40 PASS)
  - v2/data/graph: enterprise_brain_graph.ttl — 459,175 triples, temporal fields + atRisk materialized (v2/data/verify_graph_v2.py 5170/0 PASS, P1-P5 SPARQL)
  - complaint free-text: 1,200/1,200 LLM-generated (Qwen2.5-7B-Instruct on molab; 380 rewrite passes, 135 stripped)
  - v2/data/corpus: 18,998 records; embeddings.npy 18,998 x 384 (bge-small-en-v1.5)
  - v2/data/corpus/check_sync_v2.py: 18,998 records in 1:1 sync across graph, corpus, and vector index

Phase C state (2026-08-10):
  - v2/data/benchmark/benchmark.jsonl: 1,385 questions, all verified (v2/data/benchmark/verify_benchmark_v2.py OK)
  - T1 multi-hop 885 (1/2/3-hop + P1/P2/P3/P5 + aggregates), T2 temporal 300 (as-of status,
    status-change dates, complaint ordering, earliest/latest order), T3 answerability 200 (entity
    absent / relation absent / pattern absent → "I don't know")
  - splits: train 969 / val 138 / test 278 (70/10/20)

Phase D (D1) state (2026-08-11) — learnable pipeline DONE:
  - v2/systems/hybrid/entity_linker.py (multilingual-e5 mention catalog; bge can't embed
    Devanagari) — combined recall@5 0.961 vs regex-only 0.568; hop_controller.py MLP 0.986 vs
    rule 0.791 vs oracle 1.0
  - v2/systems/hybrid/relation_planner.py (LLM chain proposal + ontology validation + retry +
    heuristic fallback; walk_full for provenance); run_hybrid_learned.py (plan-then-execute) and
    run_hybrid_rule.py
  - End-to-end test 278: learned EM 0.504 / F1 0.518 vs rule 0.403 / 0.425; planned paths 1.18/q
    vs 119.2/q. Full tables in v2/V2_PLAN §6 and d1-learnable-pipeline-report.md.
  - Result JSON regenerated (298d548) with clean `predicted` (canonical answer only) and a
    separate `explanation` field — fixes the Q0003/Q1188/Q0020 leak where the answer LLM's
    "### explanation:" line was concatenated into `predicted` (parse bug; +3 EM total).
  - Caveat: T2 "as of"/"changed on" sub-templates embed the answer in the question (gold = prior
    status) while context shows current — biases both systems (learned 0.154 vs rule 0.200).

Phase E (D2) state (2026-08-14):
  - v2/systems/hybrid/groundedness.py DONE: NLI claim-decomposition
    (cross-encoder/nli-deberta-v3-base, docs/DECISIONS.md); RAGAS max-entailment rule
    (entailment probability > 0.5 over any evidence chunk). Eval on the v2 benchmark test
    (278 q, LLM-planner evidence replay): groundedness all 0.777 / hallucination 0.223;
    answerable claims-only (n=178) 0.657; answerable abstentions 64/242 (0.264, incl. format
    failures); T3 groundedness 0.972, correct "I don't know" 0.556. Files:
    v2/eval/learned_eval_groundedness.json, v2/eval/groundedness_details.json,
    v2/eval/learned_contexts.json. Caveat: NLI misses exact-value entailment inside structured
    records (residual neutral/contradiction on some correct answers) — reported honestly.
  - v2/systems/hybrid/query_interface.py DONE + verified on molab: answer + evidence chunks + provenance
    path rendered (e.g. c_0102 --filedComplaint--> comp_0102 --aboutOrder--> o_00102
    --forProduct--> p_0102) + plan-as-explanation. CLI + optional Gradio.
  - S7.3 human rating sheet PREPARED: 20 multi-hop items (10 learned + 10 rule, blind/shuffled)
    at artifacts human_evidence_path_rating_sheet.md/.csv/.json — AWAITS human annotators.
