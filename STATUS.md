# STATUS

> This file is the single source of truth for "where the project currently stands."
> Update it on every commit — see `CHECKPOINTING.md` §5. A human (or a fresh agent
> session after sandbox loss) should be able to read only this file and know exactly
> what to do next, without digging through commit history or logs.

Last updated: 2026-08-09 (S7 complete)
Current stage: S7 — hybrid retriever (complete)
Last commit: 926d8f7 (tagged `stage7-complete`)
Last verified: hybrid results in molab (2026-08-09)
Next planned action: S8 — evaluate and report: compute EM/F1/P@k/MRR per EVALUATION.md §2,
write comparison table, commit `evaluation_report.md`; S9 — freeze benchmark, tag `v1.0`.
Blockers / open questions:
- Sandbox session timeout: not documented / unknown — assume ephemeral (AGENT.md §0); nothing uncommitted counts as existing.
- GITHUB_PAT is not pre-set in the sandbox env; must be exported in-sandbox before any molab-side push.
- LLM answer formatting: hybrid retrieves correct facts (3-hop F1=0.134 vs baseline 0.027) but
  EM is low due to verbosity. Consider stricter prompt or post-processing for S8 scoring.

Environment (molab.marimo.io sandbox, confirmed 2026-08-09): NVIDIA RTX PRO 6000 Blackwell Server Edition, 102 GB VRAM, CUDA 13.0 (torch 2.11.0+cu130); 171.8 GB RAM, 20 CPUs, Python 3.13.11, git+uv present (gh absent); ephemeral by design.
