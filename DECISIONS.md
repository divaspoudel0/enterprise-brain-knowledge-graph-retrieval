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

## <fill in date> — Dataset source
Decision: Synthetic generation, not scraped/public dataset.
Rationale: No public dataset has a Customer–Order–Payment–Complaint–Product schema rich
enough to derive verifiable 2–3 hop ground truth without heavy reshaping; synthetic data
gives verifiable ground truth by construction.
Stage: S2
Reversible: no — benchmark and evaluation depend on this from S5 onward.

## <fill in date> — Groundedness scorer method
Decision: Off-the-shelf NLI/cross-encoder model (e.g. MNLI/ANLI-trained) scoring
entailed/neutral/contradicted per decomposed claim; groundedness rate = entailed fraction.
Rationale: Proposal's "lexical overlap and entailment-style scoring" was underspecified;
this makes the metric reproducible.
Stage: S8
Reversible: yes, but changing it after S9 has run invalidates prior comparisons — must
re-run S9 for both systems if changed.

## <fill in date> — Hop controller default
Decision: Start with rule-based heuristic (question-word / entity-count based); only build
a learned classifier if time remains after S9 produces valid results.
Rationale: Get an end-to-end working system first; learned controller is a stretch goal.
Stage: S7
Reversible: yes.

## <fill in date> — Default max hop depth
Decision: k_max = 2 by default, unless S5 benchmark shows meaningful 3-hop question volume.
Rationale: Matches likely benchmark composition; report whichever k was actually used.
Stage: S7
Reversible: yes, report actual value used regardless.

---

<!-- New entries go below this line, most recent last -->
