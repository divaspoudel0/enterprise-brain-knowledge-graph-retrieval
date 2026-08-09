# AGENT.md — Enterprise Brain: Master Instructions

You are executing the BE Major Project **"Enterprise Brain: Knowledge Graph-Augmented
Retrieval for Explainable Multi-Hop Question Answering"** (Tribhuvan University, Pulchowk
Campus, AIML cluster) autonomously, running on a molab.marimo.io GPU sandbox with no
persistent local storage guaranteed. Read this file first, always. Then read, in order:

1. `DATA_PIPELINE.md` — how to acquire, verify, and structure hybrid (graph + text) data.
2. `CHECKPOINTING.md` — how and when to commit to GitHub. Non-negotiable, read before writing any code.
3. `EVALUATION.md` — how the two systems are compared and what "done" means for each metric.

## 0. Non-negotiable operating rules

- **The sandbox can die at any moment.** Assume no in-memory state survives past the next
  10 minutes. Anything not committed to GitHub does not exist. See `CHECKPOINTING.md`.
- **Never fabricate results.** If a metric can't be computed because a component isn't built
  yet, report it as `NOT_YET_COMPUTED`, not a plausible-looking number. This project's entire
  value proposition is groundedness — an agent that hallucinates its own eval results defeats
  the purpose.
- **Ambiguity resolution order**: (1) check this repo's `DECISIONS.md` for a prior ruling,
  (2) if none exists, make the most defensible choice, log it in `DECISIONS.md` with a
  one-line rationale, and proceed — do not block waiting for human input unless the choice
  is irreversible and expensive (e.g. "delete raw data," "spend >$20 API credit," "rewrite
  the ontology schema").
- **No dataset ambiguity**: this project uses a **synthetically generated enterprise dataset**,
  not a scraped public CRM/e-commerce dataset. Public datasets with a genuine
  Customer–Order–Payment–Complaint–Product relational structure rich enough to derive
  verifiable 2–3 hop ground truth do not exist off-the-shelf. Do not spend time searching
  for one. Generation spec is in `DATA_PIPELINE.md` §1.

## 1. Execution order (do not reorder — later stages depend on earlier ones existing in git)

| Stage | Deliverable | Depends on |
|---|---|---|
| S1 | Ontology (Protégé/OWL or JSON-LD schema) | — |
| S2 | Synthetic data generator + generated instance data | S1 |
| S3 | Knowledge graph populated (Neo4j or RDF store) | S1, S2 |
| S4 | Text corpus (free-text fields) chunked + embedded + vector index | S2 |
| S5 | Benchmark QA pairs (1-hop, 2-hop, 3-hop) with graph-derived ground truth | S3 |
| S6 | Vector-only RAG baseline | S4, S5 |
| S7 | Hybrid retriever (entity linking + hop controller + graph traversal + fusion) | S3, S4 |
| S8 | Groundedness scorer | S6 or S7 output |
| S9 | Evaluation run: hybrid vs. baseline on identical S5 benchmark | S6, S7, S8 |
| S10 | Query interface (answer + evidence + graph path) | S7, S8 |
| S11 | Final report assembly (numbers pulled from S9 artifacts only, never re-estimated) | S9 |

Each stage ends with a git commit tagged `stageN-complete` (see `CHECKPOINTING.md`) before
starting the next. Never let S9 run on a benchmark/model config that differs between the two
systems — if you change anything about the LLM, embedding model, or question set, you must
rerun **both** systems, not just the hybrid one, or the comparison is invalid.

## 2. Fixed experimental conditions — do not silently change these

Per the proposal's own methodology (isolating the retrieval mechanism as the sole
independent variable), the following must be **identical** across baseline and hybrid runs:
- Embedding model
- LLM used for answer generation
- Benchmark question set (S5)
- Prompt template for answer generation (only the retrieved-context injection differs)

If you must change any of these mid-project (e.g. API model deprecated), log it in
`DECISIONS.md`, re-run **both** systems from that point, and note the change in the final
report's methodology section — do not present numbers from mismatched configs as comparable.

## 3. Known open decisions the proposal leaves vague — resolve these explicitly, log to DECISIONS.md

- Hop controller: rule-based heuristic vs. learned classifier. Default to rule-based first
  (question-word / entity-count heuristics) to get an end-to-end system working; only build
  the learned classifier if time remains after S9 produces valid results.
- Groundedness scorer: proposal says "lexical overlap and entailment-style scoring" — this is
  underspecified. Concretely: use an off-the-shelf NLI model (e.g. a cross-encoder trained on
  MNLI/ANLI) to score each decomposed claim against the retrieved evidence as
  entailed/neutral/contradicted, and report the entailed fraction as the groundedness rate.
  Log the exact model checkpoint used in `DECISIONS.md` — a metric that isn't reproducible
  isn't a metric.
- k (max hop depth): implement k=1,2,3 as stated, but default experiments to k_max=2 unless
  S5 benchmark data shows meaningful 3-hop question volume; report whichever you used.

## 4. What "done" looks like

The repo must, at minimum, at all times reflect the **last fully committed stage**, with a
`STATUS.md` at repo root stating current stage, last commit hash, and next planned action —
update this on every commit. A human must be able to `git clone` at any point in time and
know exactly where the project stands without reading agent logs.
