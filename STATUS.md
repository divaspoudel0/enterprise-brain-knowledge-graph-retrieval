# STATUS

> This file is the single source of truth for "where the project currently stands."
> Update it on every commit — see `CHECKPOINTING.md` §5. A human (or a fresh agent
> session after sandbox loss) should be able to read only this file and know exactly
> what to do next, without digging through commit history or logs.

Last updated: 2026-08-09 (S2 complete)
Current stage: S2 — synthetic dataset generated & verified (complete)
Last commit: a93ac53 (tagged `stage2-complete`)
Last verified: `data/verify_data.py` passed locally + in molab (2026-08-09) — FK integrity, planted patterns P1/P2/P3/P5 present, free-text fact-fidelity checks clean (250/250)
Next planned action: S3 — knowledge-graph population: map data/raw -> RDFLib graph (RDF store per DECISIONS) with provenance, serialize to data/graph/, verify against DATA_PIPELINE.md §2
Blockers / open questions:
- Sandbox session timeout: not documented / unknown — assume ephemeral (AGENT.md §0); nothing uncommitted counts as existing.
- GITHUB_PAT is not pre-set in the sandbox env; must be exported in-sandbox before any molab-side push.
- S3 dependency note: rdflib must be installed in the molab kernel env when populating the graph there (it is not in the base kernel; use `uv run --with rdflib` or pip).

Environment (molab.marimo.io sandbox, confirmed 2026-08-09): NVIDIA RTX PRO 6000 Blackwell Server Edition, 102 GB VRAM, CUDA 13.0 (torch 2.11.0+cu130); 171.8 GB RAM, 20 CPUs, Python 3.13.11, git+uv present (gh absent); ephemeral by design.
