#!/usr/bin/env python3
"""Shared infrastructure for BOTH systems (S6 baseline and S7 hybrid) — the fixed
experimental conditions of AGENT.md §2 live here so they cannot drift:

  embedding model  BAAI/bge-small-en-v1.5 (query side uses the bge retrieval prefix)
  answer LLM       Qwen/Qwen2.5-7B-Instruct, greedy (temperature 0)
  benchmark        data/benchmark/benchmark_v1.jsonl
  answer prompt    systems/prompts/answer_template.txt (identical for both systems;
                   only the {context} injection differs)
  retrieval depth  TOP_K = 5 for both systems
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
CORPUS = DATA / "corpus"
GRAPH = DATA / "graph"
BENCHMARK = DATA / "benchmark" / "benchmark_v1.jsonl"
ANSWER_TEMPLATE = (HERE / "prompts" / "answer_template.txt").read_text(encoding="utf-8")
STRUCTURED_ANSWER_TEMPLATE = (HERE / "prompts" / "answer_template_structured.txt").read_text(encoding="utf-8")

EMBED_MODEL = "BAAI/bge-small-en-v1.5"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
LLM_MODEL = "Qwen/Qwen2.5-7B-Instruct"
TOP_K = 5
MAX_NEW_TOKENS = 64
STRUCTURED_MAX_NEW_TOKENS = 256

_emb_model = None
_emb_matrix = None
_emb_meta = None
_corpus = None
_llm = None


def load_corpus() -> list[dict]:
    global _corpus
    if _corpus is None:
        _corpus = [json.loads(line) for line in (CORPUS / "text_records.jsonl").open(encoding="utf-8")]
    return _corpus


def load_embeddings():
    """Returns (matrix float32 [N,384], chunk_ids list, chunk->record map)."""
    global _emb_matrix, _emb_meta
    if _emb_matrix is None:
        _emb_matrix = np.load(CORPUS / "embeddings.npy")
        _emb_meta = json.loads((CORPUS / "embeddings_meta.json").read_text(encoding="utf-8"))
    return _emb_matrix, _emb_meta["chunk_ids"], _emb_meta["chunk_to_record"]


def embed_query(text: str) -> np.ndarray:
    """bge query-side embedding (retrieval prefix applied on the query only)."""
    global _emb_model
    if _emb_model is None:
        from sentence_transformers import SentenceTransformer
        _emb_model = SentenceTransformer(EMBED_MODEL,
                                         device="cuda" if __import__("torch").cuda.is_available() else "cpu")
    return _emb_model.encode([QUERY_PREFIX + text], normalize_embeddings=True).astype(np.float32)[0]


def retrieve(query_emb: np.ndarray, k: int = TOP_K) -> list[dict]:
    """Top-k cosine retrieval over the committed vector index.
    Returns [{chunk_id, record_id, score, text}]."""
    matrix, chunk_ids, chunk_to_record = load_embeddings()
    scores = matrix @ query_emb  # rows already unit-normalized
    order = np.argsort(-scores)[:k]
    records = {r["record_id"]: r for r in load_corpus()}
    out = []
    for idx in order:
        cid = chunk_ids[int(idx)]
        rid = chunk_to_record[cid]
        out.append({"chunk_id": cid, "record_id": rid,
                    "score": float(scores[idx]), "text": records[rid]["text"]})
    return out


def load_llm():
    """Answer LLM (greedy). Single instance reused across the whole run."""
    global _llm
    if _llm is None:
        import torch
        from transformers import pipeline
        torch.manual_seed(42)
        try:
            _llm = pipeline("text-generation", model=LLM_MODEL, torch_dtype="bfloat16", device_map="auto")
        except Exception:
            _llm = pipeline("text-generation", model=LLM_MODEL, torch_dtype="bfloat16", device=0)
    return _llm


def vector_similarity(question: str, record_ids: list[str]) -> dict:
    """Cosine similarity of question embedding to each record's embedding."""
    q_emb = embed_query(question)
    matrix, chunk_ids, chunk_to_record = load_embeddings()
    scores = {}
    for rid in record_ids:
        cid = f"{rid}:0"
        if cid in chunk_ids:
            idx = chunk_ids.index(cid)
            scores[rid] = float(matrix[idx] @ q_emb)
    return scores


def build_context(chunks: list[dict]) -> str:
    return "\n".join(f"[{c['record_id']}] {c['text']}" for c in chunks)


def generate_answer(llm, prompt: str) -> str:
    out = llm(prompt, max_new_tokens=MAX_NEW_TOKENS, do_sample=False,
              top_p=None, temperature=None)[0]["generated_text"]
    return out.split("Answer:")[-1].strip()


def generate_structured_answer(llm, prompt: str) -> dict:
    """Generate with the structured prompt and split predicted_answer / explanation.

    Returns {"predicted_answer": str, "explanation": str, "raw": str}.
    """
    out = llm(prompt, max_new_tokens=STRUCTURED_MAX_NEW_TOKENS, do_sample=False,
              top_p=None, temperature=None)[0]["generated_text"]
    raw = out[len(prompt):].strip() if out.startswith(prompt) else out.strip()
    predicted = ""
    explanation = ""
    # 1) explicit "predicted_answer:" marker anywhere in the raw text — take the
    #    LAST non-empty one (the model sometimes repeats the full output format).
    for m in re.finditer(r"predicted_answer\s*:\s*([^\n]*)", raw, re.IGNORECASE):
        val = m.group(1).strip()
        if val:
            predicted = val
    if predicted:
        m = re.search(r"explanation\s*:\s*(.*)", raw, re.DOTALL | re.IGNORECASE)
        if m:
            explanation = m.group(1).strip()
    else:
        # 2) the prompt ends in "predicted_answer:" so the model continues with
        #    the value — take the first non-empty line(s) before any "explanation:".
        body = []
        for line in raw.splitlines():
            if re.match(r"explanation\s*:", line, re.IGNORECASE):
                explanation = re.split(r"explanation\s*:\s*", line, 1, re.IGNORECASE)[1]
                break
            body.append(line.strip())
        predicted = " ".join(l for l in body if l).strip()
    return {"predicted_answer": predicted, "explanation": explanation, "raw": raw}


def load_benchmark() -> list[dict]:
    return [json.loads(line) for line in BENCHMARK.open(encoding="utf-8")]
