# STATUS

> This file is the single source of truth for "where the project currently stands."
> Update it on every commit — see `CHECKPOINTING.md` §5. A human (or a fresh agent
> session after sandbox loss) should be able to read only this file and know exactly
> what to do next, without digging through commit history or logs.

Last updated: 2026-08-09 (S1 complete)
Current stage: S1 — ontology design (complete)
Last commit: 13e3f46 (tagged `stage1-complete`)
Last verified: `ontology/validate_ontology.py` passed locally (2026-08-09) and in the molab sandbox (2026-08-09); git -> molab clone/pull loop proven
Next planned action: S2 — synthetic data generator (faker) + generated instance data per DATA_PIPELINE.md §1
Blockers / open questions:
- Sandbox session timeout: not documented / unknown — assume ephemeral (AGENT.md §0); nothing uncommitted counts as existing.
- GITHUB_PAT is not pre-set in the sandbox env; must be exported in-sandbox before any molab-side push.
- Graph store (Neo4j vs RDF store) not yet chosen — must be decided and logged before S3; ontology is store-agnostic by design (ontology/README.md).
- Embedding model + answer LLM not yet fixed — must be chosen and logged before S4/S6 (AGENT.md §2 requires them identical across both systems).

Environment (molab.marimo.io sandbox, confirmed 2026-08-09): NVIDIA RTX PRO 6000 Blackwell Server Edition, 102 GB VRAM, CUDA 13.0 (torch 2.11.0+cu130); 171.8 GB RAM, 20 CPUs, Python 3.13.11, git+uv present (gh absent); ephemeral by design.
