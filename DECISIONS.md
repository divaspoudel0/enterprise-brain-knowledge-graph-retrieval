# DECISIONS

> Append-only log of every judgment call the agent makes where the proposal or the
> AGENT.md docs left something ambiguous or underspecified. Never delete entries — if a
> decision is later reversed, log the reversal as a new entry, don't edit history. Before
> making any non-trivial call, check here first: it may already be decided.

Format per entry:
```
## <date> — <short title>
Decision: <what was decided>
Rationale: <one or two sentences, why>
Stage: <S-number this affects>
Reversible: <yes/no — can this be changed later without invalidating prior work?>
```

---

## Pre-logged decisions (already made in AGENT.md / DATA_PIPELINE.md — recorded here for a single source of truth)

## 2026-08-09 — Dataset source
Decision: Synthetic generation, not scraped/public dataset.
Rationale: No public dataset has a Customer–Order–Payment–Complaint–Product schema rich
enough to derive verifiable 2–3 hop ground truth without heavy reshaping; synthetic data
gives verifiable ground truth by construction.
Stage: S2
Reversible: no — benchmark and evaluation depend on this from S5 onward.

## 2026-08-09 — Groundedness scorer method
Decision: Off-the-shelf NLI/cross-encoder model (e.g. MNLI/ANLI-trained) scoring
entailed/neutral/contradicted per decomposed claim; groundedness rate = entailed fraction.
Rationale: Proposal's "lexical overlap and entailment-style scoring" was underspecified;
this makes the metric reproducible.
Stage: S8
Reversible: yes, but changing it after S9 has run invalidates prior comparisons — must
re-run S9 for both systems if changed.

## 2026-08-10 — S8 NLI checkpoint choice
Decision: `cross-encoder/nli-deberta-v3-base` (supervised MNLI + SNLI + FEVER + ANLI).
Rationale: Cross-encoder MNLI is the standard, reproducible groundedness scorer; the
deberta-v3-base checkpoint balances quality and size and runs on molab CPU/GPU. The exact
checkpoint is pinned in code so the metric is regeneratable (EVALUATION.md §1).
Stage: S8
Reversible: yes, but changing it after S9 has run invalidates prior comparisons — re-run
both systems if changed.

## 2026-08-09 — Hop controller default
Decision: Start with rule-based heuristic (question-word / entity-count based); only build
a learned classifier if time remains after S9 produces valid results.
Rationale: Get an end-to-end working system first; learned controller is a stretch goal.
Stage: S7
Reversible: yes.

## 2026-08-09 — Default max hop depth
Decision: k_max = 2 by default, unless S5 benchmark shows meaningful 3-hop question volume.
Rationale: Matches likely benchmark composition; report whichever k was actually used.
Stage: S7
Reversible: yes, report actual value used regardless.

---

<!-- New entries go below this line, most recent last -->

## 2026-08-09 — GitHub repository location / origin remote
Decision: Created private GitHub repo `divaspoudel0/enterprise-brain-knowledge-graph-retrieval`;
configured `origin` on this repo with the session PAT (per CHECKPOINTING.md §2). Token is stored
only in `.git/config` (never committed), and the account was confirmed via both the provided PAT
and `gh` CLI identity (`divaspoudel0`).
Rationale: No origin existed; CHECKPOINTING.md §2 requires a GitHub push target and a verified
push before real work. AGENT.md §0 resolution order: reversible, non-costly → proceed and log.
Stage: all
Reversible: yes — repo can be renamed/transferred/deleted before S5 freezes artifacts.

## 2026-08-09 — S1 ontology format
Decision: OWL 2 DL in Turtle serialization (RDFLib toolchain), namespace
`https://github.com/divaspoudel0/enterprise-brain-knowledge-graph-retrieval/ontology#`, committed as
`ontology/enterprise_brain.ttl` with a RDFLib validation script as the S1 done-gate (inventory +
inverse + cardinality + no-dangling-term assertions). No Protégé UI; the file is Protégé-openable.
Payment/order statuses and complaint categories stay plain string data properties (values enforced
as data-level constraints in S2's generator + `verify_data.py`), keeping the ontology minimal per
DATA_PIPELINE.md §1.1.
Rationale: AGENT.md §1 left "Protégé/OWL or JSON-LD" open. OWL gives `owl:inverseOf` + cardinality
restrictions needed for verifiable multi-hop traversal (S5/S7); Turtle is git-diff-friendly; RDFLib
runs headless in the ephemeral sandbox. JSON-LD would be a lossy serialization of the same graph.
Stage: S1
Reversible: yes (pre-S5; S3 graph population maps from this schema).

## 2026-08-09 — S2 dataset scale
Decision: 60 products (6 categories x 10), 400 customers, ~1,100 orders (1-6 per customer),
one payment per order (~70% paid, ~20% overdue, ~10% failed), 250 complaints. Random seed 42.
Exact params in `data/generation_config.json`.
Rationale: large enough for realistic retrieval, small enough to commit to git (<1 MB) and to
re-generate quickly; planted subsets are sized to yield >20 guaranteed positives per S5 template family.
Stage: S2
Reversible: yes until S5 freezes `benchmark_v1.jsonl`; safe re-generation before then is seed-logged.

## 2026-08-09 — S2 free-text generation model
Decision: `Qwen/Qwen2.5-7B-Instruct` (HuggingFace, run locally on the molab GPU) generates each
complaint's `free_text_description` from a committed prompt template fed only structured facts
(category, product, reason); temperature 0.3, same seed 42. Template in `data/prompts/`.
Rationale: DATA_PIPELINE.md §1.2 requires LLM-generated (not hand-templated) free text with facts
exactly traceable to the structured record; a local open-weight model avoids API cost, is
reproducible, and the 102 GB sandbox GPU hosts it trivially. Generation role is logged separately
from the S9 answer-generation LLM per DATA_PIPELINE.md §6.
Stage: S2
Reversible: yes (prompt template + seed committed; re-generation before S5 freeze is safe).

## 2026-08-09 — S2 planted multi-hop patterns
Decision: plant and manifest (`data/raw/planted_patterns.json`) four mutually disjoint pattern
families: P1 3-hop Customer-FILED->Complaint-ABOUT->Order-HAS_PAYMENT->Payment(overdue, Q1 2025)
n=30; P2 2-hop Customer-PLACED->Order-FOR->Product(Electronics, Q2 2025) n=40; P3 2-hop
Customer-FILED->Complaint-ABOUT->Order(completed, category billing, Q3 2025) n=25; P5 3-hop
Customer-FILED->Complaint-ABOUT->Order-FOR->Product(Home & Kitchen, Q4 2025) n=25.
Rationale: guarantees countable positive examples for S5 2-hop/3-hop question families instead of
accidental matches; disjoint subsets keep manifest counts exact and verifiable.
Stage: S2
Reversible: yes until S5 freeze.

## 2026-08-09 — Benchmark composition and hop taxonomy (S5, DATA_PIPELINE.md §5)
Decision: `data/benchmark/benchmark_v1.jsonl` — 529 questions (360 1-hop, 95 2-hop, 74 3-hop),
FROZEN once S9 starts. 1-hop = direct lookups (12 templates × 30); 2/3-hop = template-based
relation-sequence walks anchored on the planted-pattern members (P1/P2/P3/P5) plus generic
walks. Ground truth is derived from the data rows (which the S3 graph mirrors 1:1, proven by
verify_graph.py) and is independently re-derived for EVERY question via SPARQL on the graph
in `verify_benchmark.py` (stronger than §5's 10% sample) — ground truth never comes from an
LLM's answer.
Hop taxonomy: hops = number of graph edges between the question's anchor entity and the
answer-bearing entity; planted-pattern questions use the manifest's hop count (P1/P5=3, P2/P3=2).
Ambiguity handling: a member whose pattern matches more than once is excluded from the
single-answer per-member templates (P2: 1, P3: 1, P5: 3 members excluded) but still appears
in the aggregate questions, which answer with the full deduplicated set.
Answer format: entity answers use IDs (c_0001, o_00001) rather than Devanagari customer names
so exact-match/F1 scoring is meaningful and reproducible; attribute answers use the stored
string values. `answer_ids` and `evidence_source_record_ids` fields support P@k/MRR/EM scoring.
Stage: S5
Reversible: yes until S9; after that the file is frozen and any change requires re-running both systems.

## 2026-08-09 — Graph store (was: unresolved, needed before S3)

## 2026-08-09 — S6 Baseline: vector-only RAG (AGENT.md §2 fixed conditions)
Embedding: BAAI/bge-small-en-v1.5 with query prefix "Represent this sentence for searching relevant passages: "
LLM: Qwen/Qwen2.5-7B-Instruct, greedy (temperature 0, max_new_tokens=64)
Retrieval: top-5 cosine over embeddings.npy (2562 chunks, 1:1 chunking)
Prompt: systems/prompts/answer_template.txt (strict "I don't know" if context insufficient)
Benchmark: data/benchmark/benchmark_v1.jsonl (529 QA)
Result: EM=0.2%, F1=0.106; 1-hop F1=0.142, 2-hop=0.033, 3-hop=0.027
Latency: 0.81s avg/query (molab T4)
Stage: S6 — complete, committed as `systems/baseline/results_baseline_v1.json`

## 2026-08-09 — S7 Hybrid: entity linking + hop controller + graph traversal + fusion
Entity linking: regex over ID prefixes (c_, o_, p_, pay_, comp_) — deterministic for template questions
Hop controller: rule-based (100% match on 529 questions) using question wording + entity count
Graph traversal: deterministic SPARQL walks from linked entities at target hop depth
Fusion: 80% graph provenance score + 20% vector similarity (reduced vector weight to avoid
misleading similarity on irrelevant but textually similar records)
Prompt/LLM/embedding/benchmark: identical to baseline (shared `common.py`)
Result: EM=0.2%, F1=0.234; 1-hop F1=0.303, 2-hop F1=0.053, 3-hop F1=0.134 (vs baseline 0.027)
Latency: 3.32s avg/query (SPARQL overhead)
Stage: S7 — complete, committed as `systems/hybrid/results_hybrid_v1.json`
Key finding: Hybrid's 3-hop F1 is 5x baseline (0.134 vs 0.027), proving graph traversal
reaches facts vector retrieval misses. Low EM due to LLM verbosity (answers contain correct
fact + extra text), not retrieval failure.
Decision: RDF store — RDFLib in-memory graph populated in S3, serialized to a committed `.ttl`
dump (`data/graph/enterprise_brain_graph.ttl`); queries are SPARQL with property paths for
multi-hop traversal. Edge provenance uses standard RDF 1.1 reification (`_:stmt a rdf:Statement;
rdf:subject/predicate/object ...; eb:source_record_id "..."`) per DATA_PIPELINE.md §2 — the
initial plan was RDF-star annotations, but rdflib 7.6.0 ships no RDF-star support, so reification
(equivalent provenance, fully serializable) is used instead.
Rationale: the ontology is already OWL/Turtle so the store schema is identical to the schema;
the sandbox is ephemeral so running a Neo4j server adds ops fragility for no benefit at this
scale (~2k nodes); rdflib is headless and the TTL dump is portable to any triplestore later.
Neo4j mapping is documented in ontology/README.md if a swap is ever wanted.
Stage: S3
Reversible: yes until S5; the TTL dump makes a later store swap a mechanical port.

## 2026-08-09 — Text corpus composition and vector index (S4, DATA_PIPELINE.md §3)
Decision: the retrieval corpus is `data/corpus/text_records.jsonl` (2562 records, one chunk
each, max 148 tokens):
  (a) the LLM-generated free-text complaint descriptions (the dataset's genuine free-text
      fields), plus
  (b) deterministic natural-language records for every entity (Product/Customer/Order/
      Payment, and a Complaint record that carries id, customer, order, date, category, and
      the free-text description).
Every record carries `record_id` == the source row id (== eb:source_record_id).
Rationale: §3 says the vector index is built from free-text fields, but the dataset's only
free-text field is complaint descriptions; a corpus limited to those would make the
vector-only baseline (S6) unable to answer the S5 benchmark's order/payment/product and
multi-hop questions, trivially defeating the intended comparison (retrieval mechanism as
the sole variable). Both systems retrieve from this SAME corpus; the hybrid adds graph
traversal. This is not gaming — it is the standard RAG corpus for both systems.
Embeddings: `BAAI/bge-small-en-v1.5`, normalized, one row per chunk, committed as
`embeddings.npy` (3.9 MB — under CHECKPOINTING.md §3's few-hundred-MB line) + meta with
chunk_id -> record_id map. Query-time retrieval uses the bge retrieval-query prefix on the
query side only (document embeddings are plain) — applied identically in S6 and S7.
check_sync.py enforces the §4 sync invariant across ALL nodes (graph/corpus/vector 1:1),
a stronger condition than the §4 minimum (free-text nodes only), and verifies complaint
free-text content matches what was embedded.
Stage: S4
Reversible: yes until S5 freeze; swapping the embedding model requires re-embedding and
re-running BOTH systems (AGENT.md §2).

## 2026-08-09 — Embedding model (fixed experimental condition, AGENT.md §2)
Decision: `BAAI/bge-small-en-v1.5` (384-dim) via sentence-transformers for all text embedding
(S4 vector index, S6/S7 retrieval) — identical across both systems.
Rationale: small enough to embed the corpus fast on the sandbox GPU, retrieval-competitive for
its size, deterministic with a fixed seed. Swappable before S5 but the same model must be used
by both systems.
Stage: S4
Reversible: yes until S4 output is used in S5 freeze; a swap invalidates both systems equally
and requires re-embedding.

## 2026-08-09 — Answer LLM (fixed experimental condition, AGENT.md §2)
Decision: `Qwen/Qwen2.5-7B-Instruct` (already cached in the molab sandbox from S2) is the answer
LLM for BOTH the vector-only baseline (S6) and the hybrid system (S7); generation role logged
separately from the S2 complaint-generation role per DATA_PIPELINE.md §6.
Rationale: reuses the cached weights (no extra download), open-weights so results are
reproducible and free, and its quality on structured-fact answering is adequate for the
benchmark. Identical config for both systems satisfies the fixed-experimental-condition rule.
Stage: S6
Reversible: yes until S9 eval runs; a swap must be applied to both systems and is logged.

## 2026-08-10 — S9.5 Structured answer prompt (predicted_answer / explanation)
Decision: Re-run both systems (baseline S6, hybrid S7) with a structured answer prompt
(systems/prompts/answer_template_structured.txt) that forces a canonical `predicted_answer`
field plus a separate `explanation`. Parsing is robust (regex over repeated/mid-line markers,
first-line fallback). Retrieval, LLM, and all other fixed conditions unchanged.
Rationale: Free-text EM of 0.2% conflated generation verbosity with retrieval quality; the
structured format isolates content and makes EM/token-F1 meaningful again. Paper-grounded
(RGB/ARES/RAGAs best practice). Format-failure rate ~3-4% (model emits only explanation).
Results: EM baseline 0.2%→45.9%, hybrid 0.2%→71.6%; token F1 baseline 0.106→0.497, hybrid
0.234→0.760. Semantic metric also fixed (float() on 2D dot product was silently falling back
to token F1). Retrieval metrics unchanged (format-independent), hybrid still wins (P@5 0.843
vs 0.329).
Stage: S9.5
Reversible: yes — the free-text v1 results remain committed for comparison; adding exemplars
would require re-running generation only.

## 2026-08-10 — v2 enhancement plan approved (all 5 directions)
Decision: Proceed with Enterprise Brain v2 per V2_PLAN.md — D5 schema & data v2, D3 temporal
testbed, D4 answerability testbed, D1 learnable pipeline (entity linking, hop controller,
relation-path planning), D2 S8 groundedness scorer + S10 query interface + human evidence-path
study. Goal: thesis defense + post-defense publication.
Rationale: v1 is complete but re-study found five gaps (regex-only linking, regex hop cascade,
brute-force traversal, S8/S10 decided-but-unbuilt, wrong FINAL_REPORT numbers). v2 turns these
into a learnable, temporal, verifiable, explainable system with a publishable benchmark.
Stage: v2 (all)
Reversible: yes until v2 benchmark freezes (Phase F); v1 stays frozen as committed history.

## 2026-08-10 — v2 dataset scale (2,500+ customers)
Decision: v2 dataset scales to 2,500+ customers, ~5,500–6,000 orders/payments, ~1,200 complaints,
120 products; generated into data/raw_v2/ with a new seed/config; v1 raw untouched. Planted
patterns P1/P2/P3/P5 kept and sized up, plus temporal sub-patterns (P6 as-of status change,
P7 overdue-payment window).
Rationale: strengthens publication scale claims while molab GPU makes regeneration/embedding cheap.
Stage: v2-B
Reversible: yes until v2 benchmark freeze.

## 2026-08-10 — v2 answer format: structured only
Decision: All v2 runs use ONLY the structured answer prompt (predicted_answer/explanation).
The free-text answer arm is eliminated.
Rationale: free-text made exact-match evaluation meaningless (v1 EM 0.2% free-text vs 71.6%
structured, identical retrieval); structured is the evaluation standard for v2.
Stage: v2-F
Reversible: yes (free-text arm could be re-added, but v2 will not use it).

## 2026-08-10 — v1 frozen alongside v2
Decision: v1 artifacts (data/raw, data/benchmark/benchmark_v1.jsonl, systems/results_*_v1*,
ontology/enterprise_brain.ttl, FINAL_REPORT v1) remain frozen as committed history. All v2 work
lives in new/versioned paths (raw_v2/, benchmark_v2, ontology_v2, *_v2.* outputs).
Rationale: auditability for the defense; committed history is the contamination evidence; v2
cannot silently alter what v1 measured.
Stage: v2 (all)
Reversible: no — v1 stays as-is.

## 2026-08-10 — Public pre-defense release
Decision: A new PUBLIC GitHub repo `SchemaGround-KGQA` hosts the v2 artifacts (ontology v2,
generators, verifiers, benchmark_v2.jsonl, systems code, README, reproduction pins) with a
Zenodo DOI and CC-BY-4.0 for data, published BEFORE the thesis defense. The existing private repo
remains the v1 audit trail.
Rationale: user approved public pre-defense release; benchmark release strengthens the defense and
is a publication prerequisite.
Stage: v2-G
Reversible: yes until Zenodo DOI minting.
