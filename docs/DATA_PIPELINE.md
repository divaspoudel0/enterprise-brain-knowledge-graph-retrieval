# DATA_PIPELINE.md — Hybrid Data Acquisition, Verification, and Handling

This is the hardest and highest-risk part of the project. "Hybrid" means two structurally
different data products must be derived from the *same* underlying entities and stay
mutually consistent:

- **Graph data**: structured entities + relationships (Customer, Order, Payment, Complaint,
  Product and the edges between them) → loaded into Neo4j/RDF.
- **Text data**: free-text fields (complaint descriptions, order notes, product reviews) →
  chunked, embedded, loaded into a vector index.

If these two drift out of sync (e.g. a complaint node exists in the graph but its text was
never embedded, or vice versa), every downstream groundedness number is meaningless. Treat
sync integrity as a first-class test, not an afterthought.

## 1. Data source: synthetic generation (decided — see AGENT.md §0)

Do not scrape real customer/company data — this is unnecessary risk (PII, ToS violations,
scraping instability) for zero benefit, since the benchmark needs verifiable *derived* ground
truth, which synthetic data gives you by construction and real scraped data does not.

### 1.1 Schema (minimum viable, expand only if time allows)
```
Customer(id, name, region, signup_date)
Order(id, customer_id, product_id, order_date, amount, status)
Payment(id, order_id, amount, status[paid|overdue|failed], due_date, paid_date)
Complaint(id, customer_id, order_id, filed_date, category, free_text_description)
Product(id, name, category, price)
```
Relationships: `Customer -PLACED-> Order -FOR-> Product`, `Order -HAS_PAYMENT-> Payment`,
`Customer -FILED-> Complaint -ABOUT-> Order`.

### 1.2 Generation method
- Use a Python generator (`faker` for names/dates/text scaffolding) to produce structured
  rows first, enforcing referential integrity (every Payment references a real Order, etc.)
  and enforcing a **known distribution of multi-hop patterns** — e.g. deliberately generate
  N customers who satisfy "overdue payment AND filed complaint in quarter X" so 2-hop and
  3-hop benchmark questions have guaranteed positive examples, not just accidental ones.
- For free-text fields (complaint descriptions), do NOT hand-write hundreds of templates.
  Generate via LLM call with explicit structured input (category, product, complaint reason)
  so the text is varied but the underlying facts are still exactly known and traceable —
  never let the LLM invent facts not present in the structured record it was given.
- Log the generation seed and LLM prompt template used in `docs/DECISIONS.md` for reproducibility.

### 1.3 Verification (mandatory before proceeding to S3/S4)
Run and commit a `verify_data.py` that asserts, and fails loudly if violated:
- Every foreign key resolves (no orphan Payment/Complaint/Order records).
- Every free-text field has a corresponding structured record it was derived from.
- The known-planted multi-hop patterns (§1.2) are actually present and countable in the
  generated data — this is your ground truth for benchmark generation in S5.
- No duplicate IDs, no null required fields.
Do not proceed to graph population on unverified data. This check is cheap; a corrupted
benchmark discovered in week 6 is not.

## 2. Graph construction (S3)

- Load structured entities as nodes, relationships as edges, directly from the verified
  synthetic data (§1.3) — do not re-derive relationships heuristically, use the explicit
  foreign keys.
- Store a `source_record_id` property on every node/edge pointing back to the original
  generated row. This is the provenance chain the proposal promises ("retrieved evidence and
  graph paths can always be traced to their origin") — without it, explainability claims in
  the final report are unverifiable.

## 3. Vector index construction (S4)

- Chunk free-text fields (likely no chunking needed for short complaint descriptions; if any
  text field exceeds ~500 tokens, chunk with overlap and keep a `chunk_id -> source_record_id`
  map).
- Embed with the model fixed in `docs/AGENT.md` §2. Do not change embedding models between
  building the baseline and building the hybrid system.
- Store the same `source_record_id` provenance on every vector index entry as in §2 — this
  is what lets evidence fusion (S7) attribute a passage back to a graph node.

## 4. Sync integrity test (run after every regeneration of data)

A single script (`v1/data/corpus/check_sync.py` for v1, `v2/data/corpus/check_sync_v2.py` for v2)
must confirm: for every node in the graph with a free-text
field, there exists exactly one corresponding vector index entry with a matching
`source_record_id`, and vice versa. Run this as a CI-style check on every commit that touches
data — treat a sync failure as a build-breaking error, not a warning.

## 5. Benchmark generation (S5) — depends on §1–4 being verified

- Generate 1-hop questions as direct lookups on a single node/edge.
- Generate 2-hop and 3-hop questions by walking the *known planted patterns* from §1.2 via
  template-based relation-sequence walks (as the proposal specifies), producing the
  ground-truth answer directly from the graph traversal that generated the question — never
  from an LLM's own answer to the question, or you've silently made your ground truth
  unverifiable.
- Manually spot-check (or have the agent do an automated sanity pass) a random 10% sample:
  does the generated question's stated ground truth actually match a fresh independent graph
  query? If not, the template has a bug — fix the template, not the individual question.
- Store the benchmark as a versioned artifact inside its versioned tree
  (`v1/data/benchmark/benchmark.jsonl`, `v2/data/benchmark/benchmark.jsonl`) in git. Never
  regenerate the benchmark silently mid-project once evaluation (S9/Phase F) has started against
  it — that invalidates every prior comparison.

## 6. Anti-patterns to avoid (agent: check yourself against this list before each data-related commit)

- Regenerating synthetic data after the benchmark is frozen without also regenerating and
  re-verifying the benchmark.
- Letting the LLM used for free-text generation (§1.2) also grade its own groundedness later —
  keep generation and evaluation models/roles separate in your logs even if the same
  underlying model is called, to avoid quietly building an unfalsifiable evaluation loop.
- Treating "the script ran without errors" as equivalent to "the data is correct." Run §1.3
  and §4 explicitly; do not skip because a prior run passed.
