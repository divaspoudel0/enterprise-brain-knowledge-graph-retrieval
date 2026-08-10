#!/usr/bin/env python3
"""Phase D (D1) — learned hop controller (V2_PLAN.md §6 component 2).

Small classifier over (question embedding + linked-entity features) → {1,2,3}.
Trained on the benchmark_v2 train split; labels = verified SPARQL hops
(q['hops'] from the verified benchmark — ground truth derived from the graph).
Evaluated on val/test: learned vs rule (v1 regex cascade) vs oracle (q['hops']).

Features:
  - 384-d bge question embedding (retrieval prefix)
  - counts of linked entity types (customer/order/product/payment/complaint)
  - has 'overdue' / 'complaint' lexical cues (cheap, improves small-data fit)
Trained with sklearn MLPClassifier (or logistic fallback) after standardization.

Usage:
  uv run --with sentence-transformers --with torch --with scikit-learn \
      python systems/hybrid/hop_controller.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import EMBED_MODEL, QUERY_PREFIX

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
DATA = ROOT / "data"
BENCH = DATA / "benchmark" / "benchmark_v2.jsonl"
OUT_DIR = HERE / "learned"

ID_RE = re.compile(r"\b(c_\d+|o_\d{5}|p_\d{4}|pay_\d{5}|comp_\d{4})\b")
TYPE_OF = {"c_": "customer", "o_": "order", "p_": "product", "pay_": "payment", "comp_": "complaint"}


def load_benchmark() -> list[dict]:
    return [json.loads(line) for line in BENCH.open(encoding="utf-8")]


def entity_features(question: str) -> list[float]:
    ids = set(ID_RE.findall(question))
    counts = {t: 0 for t in TYPE_OF.values()}
    for e in ids:
        counts[TYPE_OF[e[:2]]] += 1
    q = question.lower()
    return [
        counts["customer"], counts["order"], counts["product"],
        counts["payment"], counts["complaint"],
        float("overdue" in q), float("complaint" in q),
        float("which product" in q), float("which customer" in q),
        float("changed status" in q), float("before it changed" in q),
        float("filed earlier" in q), float("earliest order" in q),
        float("latest order" in q), float(" as of " in q or " on " in q and "status" in q),
        float("i don't know" in q),
    ]


def question_embeddings(texts: list[str]):
    from sentence_transformers import SentenceTransformer
    device = "cuda" if __import__("torch").cuda.is_available() else "cpu"
    model = SentenceTransformer(EMBED_MODEL, device=device)
    emb = model.encode([QUERY_PREFIX + t for t in texts], normalize_embeddings=True,
                       batch_size=128, show_progress_bar=False)
    return np.asarray(emb, dtype=np.float32)


def rule_hop(question: str) -> int:
    q = question.lower()
    if re.search(r"what is the (status|amount|price|category|region|signup|due|filed) of", q):
        return 1
    if re.search(r"what is the payment (status|due date) for order", q):
        return 1
    if re.search(r"when is the payment for order .* due", q):
        return 1
    if re.search(r"filed a complaint .* overdue payment.* due", q):
        return 3
    if re.search(r"filed a complaint .* order .* product", q):
        return 3
    if re.search(r"filed a complaint .* completed order", q):
        return 2
    if re.search(r"which .* product .* order", q):
        return 2
    if re.search(r"customer .* order .* product", q):
        return 2
    if re.search(r"changed status", q) or re.search(r"before it changed", q):
        return 2
    if re.search(r"filed earlier", q) or re.search(r"earliest order", q) or re.search(r"latest order", q):
        return 2
    if re.search(r"i don't know", q):
        return 1
    return 2


def main() -> int:
    questions = load_benchmark()
    texts = [q["question"] for q in questions]
    print("embedding questions...")
    emb = question_embeddings(texts)  # [N, 384]
    feats = np.asarray([entity_features(t) for t in texts], dtype=np.float32)
    X = np.hstack([emb, feats])  # [N, 384+16]

    y = np.asarray([q["hops"] for q in questions], dtype=int)
    splits = np.asarray([q["split"] for q in questions])
    train = splits == "train"
    val = splits == "val"
    test = splits == "test"

    from sklearn.neural_network import MLPClassifier
    from sklearn.preprocessing import StandardScaler
    scaler = StandardScaler().fit(X[train])
    Xt = scaler.transform(X[train])
    clf = MLPClassifier(hidden_layer_sizes=(64, 32), max_iter=300, random_state=42,
                        early_stopping=True, n_iter_no_change=20, learning_rate_init=1e-3)
    clf.fit(Xt, y[train])

    def acc(mask):
        return float((clf.predict(scaler.transform(X[mask])) == y[mask]).mean())

    learned_train = acc(train)
    learned_val = acc(val)
    learned_test = acc(test)

    rule_preds = np.asarray([rule_hop(t) for t in texts])
    rule_test = float((rule_preds[test] == y[test]).mean())
    oracle_test = 1.0

    print(f"hop controller learned accuracy — train {learned_train:.3f}, "
          f"val {learned_val:.3f}, test {learned_test:.3f}")
    print(f"rule (v1 cascade) test {rule_test:.3f}; oracle test {oracle_test:.3f}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    assets = OUT_DIR / "hop_controller_assets"
    assets.mkdir(parents=True, exist_ok=True)
    import joblib
    joblib.dump(clf, assets / "model.joblib")
    joblib.dump(scaler, assets / "scaler.joblib")

    out = OUT_DIR / "hop_controller.json"
    out.write_text(json.dumps({
        "learned_train": learned_train, "learned_val": learned_val,
        "learned_test": learned_test, "rule_test": rule_test, "oracle_test": oracle_test,
        "n_train": int(train.sum()), "n_val": int(val.sum()), "n_test": int(test.sum()),
    }, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
