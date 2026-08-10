# Best Practices for RAG Evaluation & Structured Answer Generation

Findings from the structured-answer-prompt experiment (S9.5), grounded in the
research literature (EMNLP 2024 "Searching for Best Practices in RAG", RGB
benchmark AAAI 2024, ARES NAACL 2024, RAGAs EACL 2024, MultiMedQA Nature 2023,
MIRAGE Findings-ACL 2024, IRCoT ACL 2023, GRAG Findings-NAACL 2025, KGP AAAI
2024, LLM-as-a-Judge MT-Bench 2023).

## Why the structured prompt worked

Our free-text answers scored EM=0.2% even when the retrieval was correct: the
model answered in full sentences ("The order record for o_00655 indicates its
status is completed."), so exact string equality against a canonical ground
truth always failed. Forcing a two-field output — a minimal `predicted_answer`
plus a separate `explanation` — let exact-match measure *content* instead of
*verbosity*:

| System | EM (free) | EM (structured) | Token F1 (free) | Token F1 (struct) |
|--------|-----------|-----------------|-----------------|-------------------|
| Baseline | 0.2% | 45.9% | 0.106 | 0.497 |
| Hybrid   | 0.2% | 71.6% | 0.234 | 0.760 |

Retrieval was held constant; only the output format changed. This matches the
well-known finding that exact match (and token F1) conflate generation
verbosity with retrieval quality — a core motivation for canonicalized
answer formats in RAG/QA evaluation.

## Recommendations (in priority order)

### 1. Keep a canonical answer surface for automatic metrics
Exact-match and token-F1 are only meaningful against a canonical, minimal
answer. Two robust ways to get one:
- **Structured prompting** (what we did): ask for `predicted_answer` +
  `explanation`. Cheap, works on any instruction-tuned LLM, zero cost to
  deployment if you discard the explanation. ~3–4% of generations still miss
  the field — add **2–3 few-shot exemplars** (status, amount, entity-id) and,
  for production, **constrained/JSON decoding** to make the field guaranteed.
- **Post-hoc extraction** (parser or second LLM pass) over free-text answers
  when you cannot change the generator.

### 2. Report multiple metrics, never EM alone (RGB / RAGAs / ARES)
One scalar hides which component fails. We now track:
- **Exact match (EM)** — strict; meaningful only with canonical answers.
- **Token F1** — forgiving of word order/extra tokens.
- **Substring/contains** — right for attribute answers whose ground truth is a
  single value.
- **Semantic cosine (bge-small)** — agrees with token F1 on short answers but
  still useful for verbose paraphrases (fix: index `[0,0]` of the dot product;
  `float()` on a (1,1) array silently fell back to token F1).
- **Retrieval metrics P@k / MRR** — the ONLY format-independent view of
  retrieval health (hybrid P@5 0.843 vs baseline 0.329). These prove graph
  traversal reaches correct entities independently of generation.
- **LLM-as-judge** (RAGAs `answer_relevancy`, ARES `faithfulness`, MT-Bench) —
  for open-ended/qualitative dimensions, but with documented biases
  (verbosity, position); use only as a complement, not a replacement.

### 3. Diagnose RAG failures by component, not by final accuracy (RGB)
RGB (AAAI 2024) decomposes RAG capability into four testbeds:
1. **Noise robustness** — can the reader ignore distractors in context?
2. **Negative rejection** — does it answer "I don't know" when the context
   lacks the answer? (Our prompt explicitly instructs this.)
3. **Information integration** — multi-hop synthesis (our 2/3-hop family).
4. **Counterfactual robustness** — trust the context over parametric memory.
Design benchmark subsets per capability so a score drop tells you *which*
component to fix. Our per-hop and per-template breakdowns are the first step.

### 4. Keep retrieval and generation conditions fixed across systems
Both systems must share the same embedding model, retriever depth (k), LLM,
prompt template, and generation settings; only the retrieval mechanism should
vary. We enforce this by importing fixed conditions from `common.py`. This is
what makes the baseline-vs-hybrid comparison a true test of retrieval, not of
incidental prompt/model drift. (MIRAGE, EMNLP-24 best practices: the same
principle at larger scale.)

### 5. For multi-hop/graph QA, interleave retrieval with reasoning (IRCoT, KGP, GRAG)
For 3-hop questions our graph traversal is decisive (structured 3-hop EM 54.1%
vs baseline 14.9%). The literature pushes this further:
- **IRCoT (ACL 2023)**: interleave retrieval with chain-of-thought steps —
  retrieve, reason a step, retrieve again. +15 points on multi-hop QA over
  single-shot retrieve-and-read.
- **KGP (AAAI 2024)**: build a passage-level graph and traverse it with an
  LLM agent, gathering supporting passages progressively.
- **GRAG (Findings-NAACL 2025)**: retrieve optimal textual subgraphs and feed
  LLMs both text view and graph view for multi-hop reasoning.
A learned hop controller (vs our rules) and step-by-step graph-guided reasoning
are the natural next upgrades for the hybrid.

### 6. Guard against the "lost in the middle" and corpus quality traps
MIRAGE documents the **lost-in-the-middle** effect: LLMs attend less to the
middle of a long context. With k=5 compact records this is mild, but keep
contexts short, order them by fused score, and cap token length. Also ensure
the retrieval corpus matches the ground-truth source (ours mirrors the graph
1:1, verified by `check_sync.py`).

## Concrete next steps for this project

1. **Add few-shot exemplars** to `answer_template_structured.txt` (status,
   amount, entity_id, list) to push the ~3–4% format-failure rate toward 0.
2. **Track `format_failure_rate`** (no `predicted_answer` field) as its own
   metric so prompt regressions are visible.
3. **Add RGB-style negative-rejection testbed**: questions whose answer is NOT
   in the context; score "I don't know" correctness.
4. **Cross-validate the semantic metric** with LLM-as-judge on a 50-question
   sample (RAGAs-style) to confirm cosine is not over-optimistic.
5. **If more multi-hop gains are wanted**, port IRCoT-style interleaving or an
   LLM graph-traversal agent (KGP/GRAG) on top of the existing SPARQL walks.
