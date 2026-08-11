# EVALUATION.md — Comparison Protocol and Definition of Done

> v1 evaluated (S9.5). v2 adds two new testbeds and the S8 groundedness metric — see §4.
> Status of v1: baseline vs hybrid compared on `benchmark_v1.jsonl`; results in
> `systems/evaluation_report.md` / `systems/eval_metrics.json` (structured-prompt head).

## 1. Metrics (from proposal Table 3) — implement all, do not silently drop any

| Metric | Computed from | v1 status | v2 status |
|---|---|---|---|
| Precision@k / Recall@k | Retrieved evidence set vs. ground-truth evidence set (S5) | ✅ done | carried over |
| MRR | Rank position of first correct evidence item | ✅ done | carried over |
| Exact Match / F1 | Generated answer string vs. ground-truth answer | ✅ done (structured) | carried over |
| Groundedness rate | Groundedness scorer (S8) output, entailed-claim fraction | ⚠️ **not built** | ✅ built (`groundedness.py`, NLI claim-decomposition); eval pending molab |
| Multi-hop success rate | Accuracy by 1-hop / 2-hop / 3-hop subsets | ✅ done | carried over |
| Hallucination / unsupported-claim rate | 1 − groundedness rate | ⚠️ **not built** | ✅ built (same scorer); eval pending molab |
| Query latency | Wall-clock per query, same hardware/session | ✅ done | carried over |
| Evidence-path interpretability | Human rating — see §3 | ⚠️ **not done** | ✅ v2 deliverable (S10 + human study); rating sheet prepared, AWAITS annotators |

## 2. Run protocol

- Both systems (baseline, hybrid) run against the **exact same frozen benchmark file**
  (`benchmark_vN.jsonl`) in the same sandbox session, same hardware, back-to-back, to keep
  latency numbers comparable.
- Store raw per-question outputs (not just aggregate scores) for both systems as a committed
  artifact (`results_baseline_vN.json`, `results_hybrid_vN.json`) — aggregate numbers without
  the underlying per-question trace cannot be audited later and should not be treated as final.
- Recompute aggregate metrics from the stored per-question outputs via a script, not by hand —
  this makes the final report's numbers regeneratable/auditable from committed artifacts alone.

## 3. Evidence-path interpretability (human rating)

This metric genuinely cannot be computed by the agent alone — it requires a human (you, or
your project supervisor/peers) to look at a sample of outputs and rate whether the shown
evidence path is understandable. The agent's job here is to **prepare** a rating sheet (e.g.
20 sampled multi-hop answers with their evidence paths, blind as to which system produced
each) and leave it for you to fill in — not to invent a plausible-looking score itself. Flag
this explicitly in `STATUS.md` as a human-in-the-loop blocker when reached.

## 4. Statistical honesty

- With a modest benchmark size, differences between baseline and hybrid on some metrics may
  not be statistically significant — report confidence intervals or at minimum sample sizes
  per hop-depth bucket, and do not claim an improvement is real if it's within noise for a
  bucket with, say, 8 questions in it.
- If the hybrid system underperforms the baseline on any metric (plausible for 1-hop questions
  where graph traversal adds latency for no benefit), report that honestly — the proposal's
  own hypothesis is explicitly that hybrid should not degrade 1-hop performance; if it does,
  that is a real finding, not something to obscure.

## 5. Definition of done for S9

S9 is complete only when: both result files exist and are committed, the metrics table is
regenerated from those files (not hand-typed), the human-rating sheet is prepared (even if not
yet filled), and `STATUS.md` reflects this. Do not mark S9 complete based on partial metrics.

## 6. v2 additions (V2_PLAN.md D3/D4/D1 — approved 2026-08-10)

### 6.1 v2 testbeds (benchmark_v2.jsonl)
- **T1 multi-hop** — 1/2/3-hop family, re-generated on graph_v2 (same template families).
- **T2 temporal** — as-of status, before/after ordering, time-validity, latest/earliest aggregate
  questions over the v2 time-validated facts (validFrom/validTo). Correct answers are derived
  from the temporal annotations via SPARQL.
- **T3 answerability / negative rejection** — questions whose answer is absent (entity
  nonexistent or relation absent); the only correct output is exactly `"I don't know"`.

### 6.2 v2 metrics (added to §1's list)
- **Abstention accuracy (T3)**: P(correct abstention) over unanswerable questions —
  abstaining correctly when unanswerable vs. hallucinating an answer.
- **Temporal accuracy (T2)**: answer accuracy over temporal questions.
- **Groundedness rate** and **hallucination/unsupported-claim rate** from the v2
  `groundedness.py` scorer (completes the two ⚠️ rows in §1).

### 6.3 v2 learned-component ablations (D1)
On the v2 test split only (train/val/test split is generated with the benchmark):
- Entity linking: regex (v1) vs learned — report recall@k.
- Hop controller: rule-based (v1) vs learned vs oracle — report accuracy.
- Traversal: brute-force (v1) vs relation-path planning — report paths enumerated + accuracy.
- Fusion: linear 0.8/0.2 vs reciprocal-rank fusion — report P@k/MRR.
- Model transfer: Qwen2.5-7B vs Llama-3.1-8B on a ~100-question subset.

### 6.4 v2 answer format
All v2 runs use ONLY the structured answer prompt (`predicted_answer`/`explanation`); the
free-text arm is eliminated (logged in DECISIONS.md 2026-08-10).

### 6.5 v2 definition of done
v2 evaluation is complete only when: baseline, hybrid-rule, and hybrid-learned have all run on
`benchmark_v2.jsonl` (T1/T2/T3) with the structured prompt; the v2 metrics table is regenerated
from committed result files; the groundedness scorer and query interface exist and are committed;
the human evidence-path rating sheet is prepared and filled; and `STATUS.md` + `FINAL_REPORT.md`
reflect the v2 state.
