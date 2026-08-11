#!/usr/bin/env python3
"""Phase D (D2) — S7.3 human evidence-path rating sheet (EVALUATION.md §3).

Samples multi-hop (2–3 hop, T1/T2) answers from the two committed systems
(hybrid-learned and hybrid-rule) on benchmark_v2, renders each with its
evidence path (from the benchmark's provenance_path + entity ids), and writes a
BLIND sheet (no system labels, shuffled) for the human annotators to fill in.

The sheet must be filled by humans (the agent cannot rate interpretability).
Per EVALUATION.md §3 the sheet is prepared and left for the user; the filled
results are a human-in-the-loop deliverable, flagged in STATUS.md.

Output (artifacts dir):
  human_evidence_path_rating_sheet.md  — ready to annotate (columns below)
  human_evidence_path_rating.csv       — machine-readable blank sheet
"""
from __future__ import annotations

import csv
import json
import random
from pathlib import Path

ARTIFACTS = Path("/home/acer/.local/share/openresearch/files/enterprise-brain-knowledge-graph-retrieval")
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
BENCH = ROOT / "data" / "benchmark" / "benchmark_v2.jsonl"
LEARNED = HERE / "results_hybrid_learned_v2.json"
RULE = HERE / "results_hybrid_rule_v2.json"

N_PER_SYSTEM = 10
SEED = 42


def main() -> int:
    random.seed(SEED)
    questions = {q["qid"]: q for q in
                 (json.loads(l) for l in BENCH.open(encoding="utf-8"))}
    learned = json.load(open(LEARNED, encoding="utf-8"))
    rule = json.load(open(RULE, encoding="utf-8"))

    def sample(rows, n, system):
        multi = [r for r in rows if r["hops_oracle"] >= 2]
        if len(multi) < n:
            raise SystemExit(f"need {n} multi-hop answers, have {len(multi)}")
        out = []
        for r in random.sample(multi, n):
            q = questions[r["qid"]]
            ents = q["query_entities"] or r.get("linked_entities") or []
            out.append({
                "qid": r["qid"], "question": q["question"], "answer": r["predicted"],
                "gold": r["gold"], "path": q.get("provenance_path", ""),
                "entities": "→".join(ents), "system": system,
            })
        return out

    rows = sample(learned, N_PER_SYSTEM, "learned") + sample(rule, N_PER_SYSTEM, "rule")
    random.shuffle(rows)
    for i, r in enumerate(rows):
        r["sample_id"] = f"R{i+1:02d}"

    md = [
        "# Human evidence-path rating sheet (v2, D2 S7.3)",
        "",
        "Blind: items are shuffled; system identity is in `system` only in the CSV/JSON, NOT",
        "shown to annotators. Two annotators (user + one peer) each rate all items.",
        "",
        "Rate per item:",
        "- **Correctness (given question)**: is the answer right? (yes / no / unsure)",
        "- **Interpretability**: is the evidence path (entities + relation path) understandable",
        "  as support for the answer? 1 (opaque) – 5 (clear)",
        "",
        "| ID | Question | Answer | Evidence path (entities) | Provenance | Correct? | Interpretability (1-5) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        md.append(f"| {r['sample_id']} | {r['question']} | `{r['answer']}` | `{r['entities']}` | {r['path']} |  |  |")

    (ARTIFACTS / "human_evidence_path_rating_sheet.md").write_text(
        "\n".join(md) + "\n", encoding="utf-8")

    with (ARTIFACTS / "human_evidence_path_rating.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["sample_id", "qid", "system", "question", "answer", "gold",
                    "evidence_entities", "provenance_path", "correct", "interpretability_1_5"])
        for r in rows:
            w.writerow([r["sample_id"], r["qid"], r["system"], r["question"], r["answer"],
                        r["gold"], r["entities"], r["path"], "", ""])

    (ARTIFACTS / "human_evidence_path_rating.json").write_text(
        json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    n = len(rows)
    print(f"wrote rating sheet for {n} items ({N_PER_SYSTEM} learned + {N_PER_SYSTEM} rule, blind/shuffled)")
    print(f"  {ARTIFACTS / 'human_evidence_path_rating_sheet.md'}")
    print(f"  {ARTIFACTS / 'human_evidence_path_rating.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
