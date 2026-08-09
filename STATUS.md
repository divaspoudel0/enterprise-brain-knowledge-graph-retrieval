# STATUS

> This file is the single source of truth for "where the project currently stands."
> Update it on every commit — see `CHECKPOINTING.md` §5. A human (or a fresh agent
> session after sandbox loss) should be able to read only this file and know exactly
> what to do next, without digging through commit history or logs.

Last updated: 2026-08-09 (S5 complete)
Current stage: S5 — benchmark QA pairs (complete)
Last commit: 90c2e4a (tagged `stage5-complete`)
Last verified: `data/benchmark/verify_benchmark.py` passed locally + in molab (2026-08-09) — all 529 answers independently re-derived via SPARQL against the graph (360/95/74 by 1/2/3-hop)
Next planned action: S6 — vector-only RAG baseline: embed benchmark questions (bge query prefix), top-k retrieval from embeddings.npy, answer via Qwen2.5-7B-Instruct with identical prompt template (AGENT.md §2), save `results_baseline_v1.json`
Blockers / open questions:
- Sandbox session timeout: not documented / unknown — assume ephemeral (AGENT.md §0); nothing uncommitted counts as existing.
- GITHUB_PAT is not pre-set in the sandbox env; must be exported in-sandbox before any molab-side push.

Environment (molab.marimo.io sandbox, confirmed 2026-08-09): NVIDIA RTX PRO 6000 Blackwell Server Edition, 102 GB VRAM, CUDA 13.0 (torch 2.11.0+cu130); 171.8 GB RAM, 20 CPUs, Python 3.13.11, git+uv present (gh absent); ephemeral by design.
