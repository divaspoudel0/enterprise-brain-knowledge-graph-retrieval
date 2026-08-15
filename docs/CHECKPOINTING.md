# CHECKPOINTING.md — GitHub Commit Discipline for an Ephemeral Sandbox

The molab.marimo.io sandbox can be destroyed at any point with no warning. Treat every
minute of uncommitted work as work that does not exist yet. This file governs *when* and
*how* to commit — read it before writing the first line of code.

## 1. Commit frequency — time-based, not milestone-based

Milestone-based commits ("commit when a stage is done") are not sufficient — a stage can take
hours, and losing hours of a synthetic-data generation run because the sandbox died is exactly
the failure mode you're guarding against. Rules:

- **Hard rule: commit at least every 15 minutes of active work**, regardless of whether a
  logical unit is "finished." A commit of an in-progress, partially-working script is strictly
  better than losing it.
- **Also commit immediately after**: any successful data verification pass (`verify_data.py`,
  `check_sync.py`), any successful stage completion, any point before starting a
  long-running/expensive operation (LLM batch calls, embedding generation, GPU training) — if
  that operation fails or the sandbox dies mid-run, you want to resume from just before it, not
  from an hour earlier.
- If mid-work and unsure whether something is "commit-worthy," commit anyway with a
  `wip:` prefixed message. A messy history that preserves work beats a clean history that
  lost it.

## 2. Auth setup (do this first, every fresh sandbox boot)

- The GitHub PAT is provided via environment variable (`GITHUB_PAT` or equivalent — confirm
  actual var name at sandbox start; do not hardcode the token anywhere in committed files or
  print it to logs).
- Configure git remote using the token once per sandbox session:
  `git remote set-url origin https://<GITHUB_PAT>@github.com/<org>/<repo>.git`
- Verify push access works with a trivial commit (e.g. update `docs/STATUS.md` timestamp) at the
  very start of every session, before doing any real work — discovering auth is broken after
  an hour of uncommitted work defeats the entire point of this file.

## 3. Large / binary artifacts

- Do not commit raw model weights, large embedding indexes, or full Neo4j database dumps
  directly into git if they exceed a few hundred MB — use Git LFS, or push to a release asset
  / external artifact store, and commit a small manifest/pointer file instead.
- Do commit: code, configs, schemas, benchmark files, small sample data, logs, metrics/results
  (JSON/CSV), the ontology file, `docs/DECISIONS.md`, `docs/STATUS.md`.
- If unsure whether a file is "too large," check its size before committing — do not let a
  failed push (due to size) go unnoticed; verify each push actually succeeded (`git log
  origin/main` or equivalent) rather than assuming.

## 4. Recovery protocol (run this at the start of every new sandbox session)

1. `git clone` (or `git pull` if repo already present).
2. Read `docs/STATUS.md` — this tells you the last completed stage and next action.
3. Read `docs/DECISIONS.md` — do not re-litigate decisions already logged there.
4. Re-run the most recent verification scripts (`v1/data/verify_data.py`, `v2/data/verify_data_v2.py`,
   `v1/data/corpus/check_sync.py`, `v2/data/corpus/check_sync_v2.py`) against
   whatever data exists in the repo before resuming — do not assume that because a commit
   says "S3 complete," the committed artifacts actually pass verification; the sandbox may
   have died mid-write.
5. Resume from the exact next action listed in `STATUS.md`.

## 5. STATUS.md format (update `docs/STATUS.md` on every commit, no exceptions)

```markdown
# STATUS

Last updated: <timestamp>
Current stage: S<N> — <short description>
Last commit: <hash>
Last verified: <what verification script last passed, and when>
Next planned action: <one sentence>
Blockers / open questions: <or "none">
```

## 6. What NOT to do

- Do not wait until a stage is "polished" to commit — commit the ugly intermediate state.
- Do not rely on the sandbox's local disk as a source of truth for anything more than a few
  minutes old.
- Do not silently overwrite `v1/data/benchmark/benchmark.jsonl` or `v2/data/benchmark/benchmark.jsonl`
  or other frozen artifacts — if data must change after evaluation has started against it, bump the
  version (new `vN/` tree) and log why in `docs/DECISIONS.md`, so prior evaluation runs remain
  interpretable rather than orphaned.
