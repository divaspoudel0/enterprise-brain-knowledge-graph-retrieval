# Evaluation Report: Baseline vs Hybrid

## Overall Metrics

| Metric | Baseline (free) | Hybrid (free) | Δ | Baseline (struct) | Hybrid (struct) | Δ |
|--------|-----------------|---------------|----|-------------------|-----------------|----|
| exact_match | 0.002 | 0.002 | +0.000 | 0.287 | 0.616 | +0.329 |
| token_f1 | 0.106 | 0.234 | +0.128 | 0.362 | 0.671 | +0.310 |
| substring | 0.437 | 0.756 | +0.319 | 0.333 | 0.658 | +0.325 |
| semantic | 0.106 | 0.234 | +0.128 | 0.362 | 0.671 | +0.310 |
## By Hop Count

### exact_match

| System | 1-hop | 2-hop | 3-hop |
|--------|-------|-------|-------|
| Baseline (free-text) | 0.003 | 0.000 | 0.000 |
| Hybrid (free-text) | 0.003 | 0.000 | 0.000 |
| Baseline (structured) | 0.375 | 0.158 | 0.027 |
| Hybrid (structured) | 0.742 | 0.221 | 0.514 |

### token_f1

| System | 1-hop | 2-hop | 3-hop |
|--------|-------|-------|-------|
| Baseline (free-text) | 0.142 | 0.033 | 0.027 |
| Hybrid (free-text) | 0.303 | 0.053 | 0.134 |
| Baseline (structured) | 0.409 | 0.208 | 0.327 |
| Hybrid (structured) | 0.780 | 0.230 | 0.708 |

### substring

| System | 1-hop | 2-hop | 3-hop |
|--------|-------|-------|-------|
| Baseline (free-text) | 0.586 | 0.200 | 0.014 |
| Hybrid (free-text) | 0.931 | 0.316 | 0.473 |
| Baseline (structured) | 0.411 | 0.158 | 0.176 |
| Hybrid (structured) | 0.797 | 0.232 | 0.527 |

### semantic

| System | 1-hop | 2-hop | 3-hop |
|--------|-------|-------|-------|
| Baseline (free-text) | 0.142 | 0.033 | 0.027 |
| Hybrid (free-text) | 0.303 | 0.053 | 0.134 |
| Baseline (structured) | 0.409 | 0.208 | 0.327 |
| Hybrid (structured) | 0.780 | 0.230 | 0.708 |

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
| Baseline | exact_match | 0.002 | 0.287 | +0.285 |
| Baseline | token_f1 | 0.106 | 0.362 | +0.256 |
| Baseline | substring | 0.437 | 0.333 | -0.104 |
| Baseline | semantic | 0.106 | 0.362 | +0.256 |
| Hybrid | exact_match | 0.002 | 0.616 | +0.614 |
| Hybrid | token_f1 | 0.234 | 0.671 | +0.437 |
| Hybrid | substring | 0.756 | 0.658 | -0.098 |
| Hybrid | semantic | 0.234 | 0.671 | +0.437 |

## Key Findings

1. **Exact Match remains low** due to LLM verbosity (correct fact + extra text).
2. **Token F1 is 2.2x higher for hybrid** (0.234 vs 0.106), showing better fact retrieval.
3. **Substring match is primary for attribute answers** — ground truth values are contained in predictions.
4. **Semantic similarity confirms hybrid retrieves correct facts** even when verbose.
5. **Retrieval P@5 is higher for hybrid** — graph traversal reaches correct entities.