# V2_PLAN.md — Enterprise Brain v2 Enhancement Plan

> Master plan for upgrading the completed v1 project into a defense-ready, publication-grade
> artifact. Read this file first for any v2 work. This document is the single source of truth
> for *what v2 will do*; per-phase execution details live in the phase's own implementation
> notes and in `DECISIONS.md`.
>
> Status: **APPROVED 2026-08-10** by user (all 5 directions; defense + post-defense publication;
> public pre-defense release). v1 remains frozen as committed history.

---

## 1. Problem statement (why v2 exists)

The v1 system is complete and evaluated (S1–S9.5, tag `v1.0`), but re-study of the repo and the
literature surfaced five integrity and novelty gaps that block a thesis defense and a publication:

| # | Gap found in v1 | Consequence |
|---|---|---|
| G1 | **Entity linking is a regex over exact IDs** (`run_hybrid.py:71` `ID_RE`). Works only because benchmark questions embed IDs verbatim. | The system cannot answer real natural-language questions ("the order Mr. Shrestha placed in March"). Regex is not a generalizable contribution. |
| G2 | **Hop controller is a 40+ line regex cascade** hand-tuned to each template family (`run_hybrid.py:75-121`). `AGENT.md` §3 deferred a learned controller; it was never built. | Not generalizable; no learning story to publish. |
| G3 | **Traversal brute-forces all 10 property chains** (3-hop = 1000 SPARQL paths) with early truncation (`run_hybrid.py:192-208`). | Does not scale; no semantic path selection. |
| G4 | **S8 groundedness scorer decided but never built**; **S10 query interface decided but never built**. `FINAL_REPORT.md` lists both as existing files (`groundedness.py`, etc.) that are not in the repo. `EVALUATION.md` §3 requires a human evidence-path rating that was never done. | Thesis title promises "Explainable Multi-Hop QA" but the explainability deliverable is missing; report makes unverifiable claims. |
| G5 | **`FINAL_REPORT.md` numbers are wrong** (claims 500/1500/1500/200/100; actual data is 400/926/926/250/60) and cites a non-existent arXiv ID. | Defense panel would catch this. |

### v2 goal

Turn the v1 artifacts into a **learnable, temporal, verifiable, explainable** enterprise KG-QA
system with a **publishable benchmark** — while keeping v1 frozen as committed history for
auditability.

---

## 2. Scope & non-goals

### In scope (all 5 approved directions)

- **D5 — Schema & data v2**: ontology enrichment (OWL enumerations, subclass taxonomy,
  time-validity, SWRL-style rules), larger synthetic dataset, regenerated graph/corpus/embeddings.
- **D3 — Temporal QA**: new temporal testbed (T2) in benchmark v2, grounded in EXAQT/TempoQR/CronQuestions.
- **D4 — Answerability / negative rejection**: new testbed (T3) in benchmark v2, grounded in RGB
  and uncertainty-abstention literature.
- **D1 — Learnable pipeline**: learned entity linking, learned hop controller, relation-path
  planning (RoG/PoG/Adaptive-RAG/GNN-RAG grounded) replacing the three v1 heuristics.
- **D2 — Explainability deliverable**: S8 groundedness scorer (NLI claim decomposition) and S10
  query interface (answer + evidence + graph path) + human evidence-path study.
- **Integrity repair**: correct `FINAL_REPORT.md`, `STATUS.md`, `DECISIONS.md`, `EVALUATION.md`.

### Out of scope (explicitly deferred)

- Multi-language / multilingual QA.
- Deployment / serving infrastructure (S10 is a local interface, not a production service).
- Real (non-synthetic) enterprise data — the synthetic benchmark is a deliberate, logged choice.

---

## 3. Fixed experimental conditions (v2 — extends AGENT.md §2)

These must remain identical across every compared system; changes are logged in `DECISIONS.md`.

| Condition | v1 value | v2 value (unless changed & logged) |
|---|---|---|
| Embedding model | `BAAI/bge-small-en-v1.5` | unchanged |
| Answer LLM | `Qwen/Qwen2.5-7B-Instruct` (greedy) | unchanged for main runs; `Llama-3.1-8B-Instruct` used ONLY for the transfer ablation |
| Answer prompt | structured `answer_template_structured.txt` | structured ONLY (free-text arm eliminated per user) |
| Retrieval depth | TOP_K=5 | unchanged |
| Benchmark | `benchmark_v1.jsonl` (frozen) | `benchmark_v2.jsonl` (new; v1 frozen) |

**Rule:** any change to the conditions above requires re-running ALL compared systems from that
point and logging the change. The v1→v2 data/schema change is a full re-generation (D5) and is
logged as one entry; within v2, conditions stay fixed.

---

## 4. Data & schema v2 (D5)

### 4.1 Ontology enrichment (`ontology/enterprise_brain_v2.ttl`, v1 file kept)

1. **OWL enumerations** — replace bare-string statuses/categories with `owl:oneOf` restrictions:
   `OrderStatus {completed, pending, cancelled, refunded}`, `PaymentStatus {paid, overdue, failed}`,
   `ComplaintCategory {billing, delivery, product_quality, service, refund}`.
2. **Subclass taxonomy** — `Product` subclasses by category (`ElectronicsProduct`, `HomeKitchenProduct`,
   …) so type-aware questions and inference are well-formed.
3. **Time validity** — `eb:validFrom` / `eb:validTo` datatype properties (xsd:date) applied to
   time-varying facts (`status`, `due_date`), enabling "as of date" queries (T2).
4. **SWRL-style rules** — document derived properties as TTL comments + a derivable
   `eb:atRisk` property (payment overdue ∧ complaint exists → customer at risk); inference questions
   derive answers from the rule, verifiable via SPARQL against the rule's preconditions.
5. **Backward compatibility** — v1 instance data must still validate against v2 ontology for the
   v1-frozen audit trail (validate both graphs in `validate_ontology.py`).

### 4.2 Dataset v2 (scale: 2,500+ customers — approved option "larger")

| Entity | v1 | v2 target |
|---|---|---|
| Products | 60 | 120 (keep 6 categories × 20, or extend categories) |
| Customers | 400 | **2,500** |
| Orders | 926 | ~5,500–6,000 (1–6 per customer) |
| Payments | 926 | ~5,500–6,000 (≥1 per order; some orders get 2 payments for installment reasoning) |
| Complaints | 250 | ~1,200 |

- New `gen_synthetic.py` path or `gen_synthetic_v2.py` with its own seed/config; write
  `data/raw_v2/` (separate dir) so v1 raw stays untouched. Planted patterns P1/P2/P3/P5 are kept
  (sized up) plus **temporal sub-patterns** (P6: as-of status change; P7: overdue payment window).
- `verify_data_v2.py` (or v1 verifier parameterized over dir) must pass before graph population.

### 4.3 Downstream regeneration order (strict)

```
raw_v2 → verify_data_v2 → populate_graph_v2 (graph_v2.ttl) → gen_complaint_text_v2 (LLM, molab)
→ build_corpus_v2 → embed_corpus_v2 (molab) → verify_graph_v2 + check_sync_v2  (all gates green)
```

---

## 5. Benchmark v2 (D3 + D4)

### 5.1 Composition (three testbeds)

| Testbed | Capability (RGB) | Question types | Approx. count |
|---|---|---|---|
| T1 multi-hop | information integration | 1/2/3-hop family (same templates as v1, re-generated on graph_v2, more instances) | ~800 |
| T2 temporal | temporal reasoning | as-of status, before/after ordering, time-validity, latest/earliest aggregate | ~300 |
| T3 answerability | negative rejection | unanswerable (entity absent / relation absent) → correct output `"I don't know"` | ~200 |
| **Total** | | | **~1,300** |

### 5.2 Per-question metadata (all testbeds)

`qid, template_id, hops, pattern, question, answer, answer_type, answer_ids, is_answerable,
evidence_source_record_ids, query_entities, provenance_path`

### 5.3 Verification contract (`verify_benchmark_v2.py`)

- **Every answerable question's ground truth is independently recomputed via SPARQL** over
  graph_v2 (never trusted from generation time).
- **Every unanswerable question is verified to have no answer in the graph** (SPARQL returns
  empty / satisfiability check), so `"I don't know"` is provably the only correct output.
- **Temporal questions verified against the validFrom/validTo annotations.**
- Output: `benchmark_v2.jsonl` + a verification report (all questions pass, else generation fails).

### 5.4 Splits (required for D1's learned components)

Split v2 into **train / validation / test** (e.g., 70/10/20) at generation time; split metadata
stored per question (`split: train|val|test`). Learned components train only on `train`,
tune on `val`, report on `test`. This split is what makes the learned-hop-controller claim
non-circular and publishable.

### 5.5 Frozen-benchmark rule

`benchmark_v2.jsonl` freezes once Phase F evaluation starts. v1 stays frozen forever. Both carry
`check_sync` guarantees with their respective graphs.

---

## 6. Learnable pipeline (D1)

Replaces the three v1 heuristics in `run_hybrid.py` with a **plan-then-execute** pipeline.
v1's rule-based hybrid stays in the repo (baseline v2 "hybrid-rule"); the new one is "hybrid-learned".

| Component | v1 (frozen) | v2 new | Training signal |
|---|---|---|---|
| Entity linking | regex `ID_RE` | multilingual embedding (intfloat/multilingual-e5-small) mention→entity retrieval over a mention catalog (products, customers in Devanagari); regex fast path for ID references | bge-small-en-v1.5 cannot embed Devanagari names (measured); multilingual catalog retrieval is the learned replacement |
| Hop controller | regex cascade | small classifier (question embedding + linked-entity features → {1,2,3}) | v2 train questions; labels = verified SPARQL hops |
| Traversal | brute-force 10^h chains | relation-path planning: LLM proposes relation sequence → validated against ontology → targeted SPARQL walk (RoG/PoG) | prompt-only (no training); plan validated by execution |
| Fusion | linear 0.8/0.2 | linear (sensitivity reported) + RRF comparison | n/a |

### Evaluation claims the learned pipeline must support

- Linker recall@k on v2 dev/test (honest measure of real-world utility; v1 regex recall@1 = 100%
  only because questions embedded IDs).
- Hop-controller accuracy (learned vs rule vs oracle) on test.
- Traversal: paths enumerated (~1 planned vs 1000 brute) and accuracy.
- The **plan is the explanation** → feeds S10 provenance rendering.

### D1 status: DONE (results committed)

| Component | Metric | Result |
|---|---|---|
| Linker (mentions-only, 751 q, natural-language surfaces regex can't parse) | learned recall@1 / recall@5 vs regex recall@5 | **0.708 / 0.776 vs 0.264** |
| Linker (all 1281 q) | combined (regex IDs + learned mentions) recall@1 / recall@5 vs regex-only recall@5 | **0.752 / 0.961 vs 0.568** |
| Hop controller (test 278) | learned vs rule vs oracle accuracy | **0.986 vs 0.791 vs 1.000** |
| Traversal (test 278) | planned paths/q vs brute-force queries/q | **1.18 vs 119.2** |
| End-to-end (test 278) | hybrid-learned vs hybrid-rule EM / F1 | **0.504 / 0.518 vs 0.403 / 0.425** |
| Plan validity (LLM planner, hop1 sample) | validated plans | 40/40 (100%) |

Components: `systems/hybrid/entity_linker.py`, `hop_controller.py`, `relation_planner.py`,
`run_hybrid_learned.py` (plan-then-execute), `run_hybrid_rule_v2.py` (baseline).
T2 note: the temporal "as of"/"changed on" sub-templates embed the answer in the question
("changed status from X to Y" → gold X) while context shows the current status; the fixed
"answer ONLY from context" prompt biases both systems there (learned 0.154 vs rule 0.200 EM
on T2) — a benchmark/prompt nuance, not a regression of the learned components.

---

## 7. Explainability deliverable (D2)

> Status 2026-08-14: S8 + S10 DONE, evaluated and verified on molab; sheet prepared.

### 7.1 S8 — `groundedness.py` (was decided, never built)

- NLI claim-decomposition: split predicted answer into claims; score each against retrieved
  evidence with an MNLI/ANLI cross-encoder (entailed/neutral/contradicted).
- Groundedness rate = entailed fraction; hallucination/unsupported-claim rate = 1 − that.
- Model checkpoint logged in `DECISIONS.md` (`cross-encoder/nli-deberta-v3-base`). Completes
  `EVALUATION.md` §1's metric list.
- `run_d2_groundedness.py` replays the D1 retrieval deterministically (greedy, seeded planner)
  to recover the exact evidence each frozen answer saw, then scores it.
- RESULTS (benchmark_v2 test, 278 q, LLM-planner evidence replay):
  groundedness all **0.777** (hallucination 0.223); answerable claims-only (n=178) **0.657**;
  answerable abstentions 64/242 (0.264, incl. format failures); T3 groundedness 0.972 with
  correct "I don't know" 0.556. Decision rule: RAGAS max-entailment (entailment prob > 0.5
  over any evidence chunk); verified that nli-deberta-v3-base outputs
  [contradiction, entailment, neutral] logits (first fix was inverted).
  Caveat: NLI misses exact-value entailment inside structured records (some correct answers
  score neutral/contradiction) — residual unsupported-claim rate is an upper bound.

### 7.2 S10 — `query_interface.py`

- Local interface (CLI + optional Gradio) returning: **answer + retrieved evidence chunks +
  graph provenance path** (rendered as Customer→Complaint→Order→Payment with relation labels).
- For hybrid-learned: the generated relation plan is shown as the explanation
  (`planner.walk_full` returns the full node chain per hit for rendering).
- VERIFIED on molab: e.g. Q "Which product did customer c_0102 order in the order they filed
  a complaint about?" → plan `[filedComplaint, aboutOrder, forProduct]`, provenance
  `c_0102 --filedComplaint--> comp_0102 --aboutOrder--> o_00102 --forProduct--> p_0102`,
  answer + 7 evidence chunks returned.

### 7.3 Human evidence-path study (`EVALUATION.md` §3)

- Sheet PREPARED (20 items, blind/shuffled) at
  artifacts `human_evidence_path_rating_sheet.md`/`.csv`/`.json`; awaits the annotators.
- 2 annotators (user + one peer) rate sampled answers per system on:
  (a) answer correctness given context; (b) path/evidence interpretability.
- Report Cohen's κ; results feed both the thesis appendix and the paper's human-eval section.
- Sheet PREPARED (20 items, blind/shuffled) at
  artifacts `human_evidence_path_rating_sheet.md`/`.csv`/`.json`; awaits the annotators.

---

## 8. Evaluation v2 (Phase F, molab)

### 8.1 Systems compared (all on `benchmark_v2.jsonl`, structured prompt only)

1. baseline (vector-only)
2. hybrid-rule (v1 pipeline, re-pointed at v2 data)
3. hybrid-learned (new pipeline)

### 8.2 Metrics

- Existing: EM, token-F1, substring, semantic cosine, P@k/MRR, per-hop, per-template.
- **New**: groundedness rate, abstention accuracy (T3; correct `"I don't know"` vs hallucination),
  temporal accuracy (T2), per-testbed accuracy, per-split (test-only for learned claims).

### 8.3 Ablations (molab runs)

| Ablation | Detail |
|---|---|
| Model transfer | Qwen2.5-7B vs Llama-3.1-8B on a subset (~100 q) → format/EM effect not model-specific |
| Linker | regex vs learned (recall@k) |
| Hop controller | rule vs learned vs oracle |
| Traversal | brute vs planned (paths enumerated, accuracy) |
| Fusion | 0.8/0.2 vs RRF vs weight sweep |

---

## 9. Integrity repair (Phase A — do first, no GPU)

1. `FINAL_REPORT.md`: correct data counts (400/926/926/250/60 → v1 section; v2 counts added in v2
   report), replace fabricated `Repository Structure` with the real tree, fix metric headline to
   structured results, remove/flag non-existent arXiv citation.
2. `STATUS.md`: current state reflects v2 plan.
3. `DECISIONS.md`: log the v2 decisions (approved directions, scale 2,500+, structured-only,
   public pre-defense release, v1-frozen).
4. `EVALUATION.md`: mark S8/S10 as pending v2 deliverables, add T2/T3 metrics.

---

## 10. Public release (pre-defense, per user)

- New **public** GitHub repo `SchemaGround-KGQA` hosting: ontology v2, generators, verifiers,
  `benchmark_v2.jsonl`, systems code, README, reproduction pins.
- Zenodo DOI + CC-BY-4.0 for the benchmark data.
- Reproducibility statement (fixed seeds, pinned model versions).
- v1 artifacts remain in the existing private repo for the audit trail.

---

## 11. Publication package (post-defense)

- Paper skeleton targeting ACL/EMNLP Datasets & Benchmarks (or main track) on the niche:
  *verifiable schema-grounded enterprise multi-hop QA benchmark (temporal + answerability
  testbeds) with a learnable plan-and-traverse pipeline and groundedness evaluation.*
- Written only after Phase F numbers exist (no fabricated results — AGENT.md §0).

---

## 12. Execution order & status

```
Phase A (integrity repair)  ▸ B (schema/data v2) ▸ C (benchmark v2) ▸ D (learnable pipeline)
▸ E (S8+S10+human study) ▸ F (eval v2) ▸ G (report + release + paper)
```

| Phase | Deliverable | GPU | Status |
|---|---|---|---|
| A | Corrected reports + decision log | no | **PENDING (next)** |
| B | Ontology v2 + dataset v2 + graph/corpus/embeddings v2 | yes (text gen, embed) | PENDING |
| C | benchmark_v2.jsonl (T1/T2/T3) + verifier + splits | no | PENDING |
| D | Learned linker/hop-controller/path-planner | yes (train, plan) | PENDING |
| E | groundedness.py + query_interface.py + human study | yes (NLI) | PENDING |
| F | Full eval v2 + ablations | yes | PENDING |
| G | FINAL_REPORT v2 + public release + paper skeleton | no | PENDING |

## 13. Open risks

1. **Learned linker data** — needs natural-language questions without embedded IDs; if
   generation quality is poor, fall back to name-based mention detection + embedding ranking
   (documented fallback, not a failure).
2. **NLI groundedness on short answers** — some answers are single tokens (ids, amounts); claim
   decomposition may be trivial. Mitigation: decompose the explanation field when present.
3. **Scale (2,500+ customers) embedding time** — small model, fast on molab; if slow, chunk in
   batches (logged).
4. **Time budget** — if a phase slips, priority order is A ▸ B ▸ C ▸ E ▸ D ▸ F ▸ G (defense
   deliverables first: corrected reports, temporal+answerability benchmark, S8/S10, human study).
