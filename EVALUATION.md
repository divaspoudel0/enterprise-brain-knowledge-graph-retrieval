# EVALUATION.md — Comparison Protocol and Definition of Done

## 1. Metrics (from proposal Table 3) — implement all, do not silently drop any

| Metric | Computed from |
|---|---|
| Precision@k / Recall@k | Retrieved evidence set vs. ground-truth evidence set (S5) |
| MRR | Rank position of first correct evidence item |
| Exact Match / F1 | Generated answer string vs. ground-truth answer |
| Groundedness rate | Groundedness scorer (S8) output, entailed-claim fraction |
| Multi-hop success rate | Accuracy broken down by 1-hop / 2-hop / 3-hop question subsets |
| Hallucination / unsupported-claim rate | 1 − groundedness rate, or claims scored "contradicted"/"neutral" |
| Query latency | Wall-clock time per query, both systems, same hardware, same session |
| Evidence-path interpretability | Human rating — see §3, cannot be automated, do not fabricate |

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
