#!/usr/bin/env python3
"""Phase D (D2) — S8 groundedness scorer (V2_PLAN §7.1, EVALUATION.md §1).

NLI claim-decomposition scorer. For each (question, predicted answer, retrieved
evidence chunks):

  1. Split the predicted answer into atomic claims (sentence boundary; a short
     canonical answer is one claim).
  2. Score every claim against every evidence chunk with a cross-encoder MNLI
     model (entailment / neutral / contradiction). A claim is GROUNDED iff its
     best evidence pair is entailment.
  3. groundedness rate = entailed-claim fraction; hallucination / unsupported-
     claim rate = 1 - groundedness.

The "I don't know" abstention is treated as fully grounded (1.0) — it commits
to no unsupported facts. The scorer also reports the abstention rate, which is
what T3 accuracy is computed against.

Checkpoint (logged in DECISIONS.md): cross-encoder/nli-deberta-v3-base
(MNLI + SNLI + FEVER + ANLI, supervised). CPU-capable, GPU-accelerated on molab.

Usage:
  # single pair, JSON on stdin
  echo '{"answer": "pending", "evidence": ["Order o_0001 — Status: pending."]}' \
    | python systems/hybrid/groundedness.py --score

  # batch over a results file + contexts file (see run_d2_groundedness.py)
  python systems/hybrid/groundedness.py --results r.json --contexts c.json --out g.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent

NLI_MODEL = "cross-encoder/nli-deberta-v3-base"
ID_LABELS = {0: "entailment", 1: "neutral", 2: "contradiction"}
ABSTAIN = ("i don't know",)

_scorer = None


def _load_scorer():
    global _scorer
    if _scorer is None:
        from sentence_transformers import CrossEncoder
        _scorer = CrossEncoder(NLI_MODEL, device="cuda" if _torch_cuda() else "cpu")
    return _scorer


def _torch_cuda() -> bool:
    try:
        import torch
        return torch.cuda.is_available()
    except Exception:
        return False


def split_claims(answer: str) -> list[str]:
    """Split a predicted answer into atomic claims.

    Canonical answers ("29.99", "pending", "c_0001") are single claims. Longer
    multi-fact answers are split on sentence boundaries; an un-splittable
    remainder is kept whole so the canonical value is never lost."""
    a = answer.strip()
    if not a:
        return []
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", a) if s.strip()]
    return sentences


def claim_is_abstention(claim: str) -> bool:
    return claim.lower().strip() in ABSTAIN


def nli_label(premise: str, hypothesis: str) -> tuple[str, float]:
    """Return (label, entailment-logit-ish score) for one pair."""
    scorer = _load_scorer()
    # softmax over [entailment, neutral, contradiction]
    logits = scorer.predict([(premise, hypothesis)])[0]
    scores = np.exp(logits - np.max(logits))
    scores = scores / scores.sum()
    label = ID_LABELS[int(np.argmax(logits))]
    return label, float(scores[0])


def score_answer(answer: str, evidence: list[str], question: str = "") -> dict:
    """Groundedness of one predicted answer against retrieved evidence.

    Returns per-claim labels and aggregate groundedness / hallucination /
    abstention."""
    claims = split_claims(answer)
    if not claims:
        return {"claims": [], "grounded": [], "groundedness": 1.0,
                "hallucination": 0.0, "abstention": True, "evidence_n": len(evidence)}
    if all(claim_is_abstention(c) for c in claims):
        return {"claims": claims, "grounded": [True] * len(claims),
                "groundedness": 1.0, "hallucination": 0.0, "abstention": True,
                "evidence_n": len(evidence)}

    per_claim = []
    grounded = []
    for c in claims:
        if claim_is_abstention(c):
            per_claim.append({"claim": c, "label": "abstention", "best": -1.0})
            grounded.append(True)
            continue
        if not evidence:
            per_claim.append({"claim": c, "label": "unsupported", "best": -1.0})
            grounded.append(False)
            continue
        best_label, best_score = None, -1.0
        for e in evidence:
            label, score = nli_label(e, c)
            if score > best_score:
                best_label, best_score = label, score
        grounded.append(best_label == "entailment")
        per_claim.append({"claim": c, "label": best_label, "best": best_score})

    n = len(claims)
    groundedness = sum(grounded) / n
    return {
        "claims": claims, "per_claim": per_claim, "grounded": grounded,
        "groundedness": groundedness, "hallucination": 1.0 - groundedness,
        "abstention": False, "evidence_n": len(evidence),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--score", action="store_true",
                    help="score one {answer, evidence[]} pair from stdin")
    ap.add_argument("--results", help="results json (per-question predicted answers)")
    ap.add_argument("--contexts", help="{qid: [evidence chunks]} json")
    ap.add_argument("--out", default="groundedness_out.json")
    args = ap.parse_args()

    if args.score:
        pair = json.load(sys.stdin)
        res = score_answer(pair["answer"], pair["evidence"])
        print(json.dumps(res, indent=2))
        return 0

    if not args.results or not args.contexts:
        ap.error("need --score or both --results and --contexts")

    results = json.load(open(args.results, encoding="utf-8"))
    contexts = json.load(open(args.contexts, encoding="utf-8"))

    rows, gs, abst = [], [], 0
    for r in results:
        qid = r.get("qid") or r.get("question")
        evidence = contexts.get(str(qid), [])
        if not evidence and isinstance(qid, dict):
            evidence = contexts.get(str(qid.get("qid")), [])
        s = score_answer(r["predicted"], evidence)
        gs.append(s["groundedness"])
        abst += s["abstention"]
        rows.append({"qid": r["qid"], "predicted": r["predicted"],
                     "groundedness": s["groundedness"],
                     "hallucination": s["hallucination"],
                     "claims": s["claims"], "per_claim": s.get("per_claim"),
                     "abstention": s["abstention"], "evidence_n": s["evidence_n"]})

    n = len(rows)
    out = {
        "model": NLI_MODEL,
        "n": n,
        "groundedness": float(np.mean(gs)) if gs else 0.0,
        "hallucination": float(1.0 - np.mean(gs)) if gs else 0.0,
        "abstention_rate": abst / n if n else 0.0,
        "rows": rows,
    }
    print(f"groundedness over {n} answers: {out['groundedness']:.3f} "
          f"(hallucination {out['hallucination']:.3f}, abstention {out['abstention_rate']:.3f})")
    Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
