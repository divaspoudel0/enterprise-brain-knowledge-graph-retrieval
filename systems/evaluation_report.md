# Evaluation Report: Baseline vs Hybrid

## Overall Metrics

| Metric | Baseline (free) | Hybrid (free) | Δ | Baseline (struct) | Hybrid (struct) | Δ |
|--------|-----------------|---------------|----|-------------------|-----------------|----|
| exact_match | 0.002 | 0.002 | +0.000 | 0.459 | 0.716 | +0.257 |
| token_f1 | 0.106 | 0.234 | +0.128 | 0.497 | 0.760 | +0.263 |
| substring | 0.437 | 0.756 | +0.319 | 0.465 | 0.743 | +0.278 |
| semantic | 0.657 | 0.722 | +0.065 | 0.782 | 0.887 | +0.105 |
## By Hop Count

### exact_match

| System | 1-hop | 2-hop | 3-hop |
|--------|-------|-------|-------|
| Baseline (free-text) | 0.003 | 0.000 | 0.000 |
| Hybrid (free-text) | 0.003 | 0.000 | 0.000 |
| Baseline (structured) | 0.575 | 0.263 | 0.149 |
| Hybrid (structured) | 0.867 | 0.284 | 0.541 |

### token_f1

| System | 1-hop | 2-hop | 3-hop |
|--------|-------|-------|-------|
| Baseline (free-text) | 0.142 | 0.033 | 0.027 |
| Hybrid (free-text) | 0.303 | 0.053 | 0.134 |
| Baseline (structured) | 0.580 | 0.314 | 0.333 |
| Hybrid (structured) | 0.891 | 0.293 | 0.721 |

### substring

| System | 1-hop | 2-hop | 3-hop |
|--------|-------|-------|-------|
| Baseline (free-text) | 0.586 | 0.200 | 0.014 |
| Hybrid (free-text) | 0.931 | 0.316 | 0.473 |
| Baseline (structured) | 0.578 | 0.263 | 0.176 |
| Hybrid (structured) | 0.900 | 0.295 | 0.554 |

### semantic

| System | 1-hop | 2-hop | 3-hop |
|--------|-------|-------|-------|
| Baseline (free-text) | 0.675 | 0.580 | 0.668 |
| Hybrid (free-text) | 0.755 | 0.593 | 0.729 |
| Baseline (structured) | 0.820 | 0.680 | 0.729 |
| Hybrid (structured) | 0.958 | 0.615 | 0.890 |

## Retrieval Metrics (P@k / MRR)

| Metric | Baseline (free) | Hybrid (free) | Δ | Baseline (struct) | Hybrid (struct) | Δ |
|--------|-----------------|---------------|----|-------------------|-----------------|----|
| P@1 | 0.285 | 0.529 | +0.244 | 0.285 | 0.529 | +0.244 |
| P@3 | 0.297 | 0.750 | +0.453 | 0.297 | 0.750 | +0.453 |
| P@5 | 0.329 | 0.843 | +0.514 | 0.329 | 0.843 | +0.514 |
| MRR | 0.355 | 0.721 | +0.366 | 0.355 | 0.721 | +0.366 |

## Structured vs Free-text (same retrieval, answer format only)

| System | Metric | Free-text | Structured | Δ |
|--------|--------|-----------|------------|----|
| Baseline | exact_match | 0.002 | 0.459 | +0.457 |
| Baseline | token_f1 | 0.106 | 0.497 | +0.391 |
| Baseline | substring | 0.437 | 0.465 | +0.028 |
| Baseline | semantic | 0.657 | 0.782 | +0.125 |
| Hybrid | exact_match | 0.002 | 0.716 | +0.715 |
| Hybrid | token_f1 | 0.234 | 0.760 | +0.526 |
| Hybrid | substring | 0.756 | 0.743 | -0.013 |
| Hybrid | semantic | 0.722 | 0.887 | +0.165 |

## Key Findings

1. **Exact Match remains low** due to LLM verbosity (correct fact + extra text).
2. **Token F1 is 2.2x higher for hybrid** (0.234 vs 0.106), showing better fact retrieval.
3. **Substring match is primary for attribute answers** — ground truth values are contained in predictions.
4. **Semantic similarity confirms hybrid retrieves correct facts** even when verbose.
5. **Retrieval P@5 is higher for hybrid** — graph traversal reaches correct entities.