# Stage S1 — Enterprise Brain Ontology

OWL 2 DL schema for the synthetic enterprise dataset (DATA_PIPELINE.md §1.1),
produced in Stage S1 of AGENT.md. Decision and rationale logged in
DECISIONS.md ("S1 ontology format").

## Files

| File | Contents |
|---|---|
| `enterprise_brain.ttl` | The ontology (OWL 2 DL, Turtle serialization). |
| `example_instances.ttl` | One minimal instance set exercising the full 2-hop pattern `Customer -FILED-> Complaint -ABOUT-> Order -HAS_PAYMENT-> Payment`; smoke fixture for S2/S3. |
| `validate_ontology.py` | RDFLib done-gate for S1: asserts the §1.1 inventory (classes, object/data properties, inverse pairs, domains/ranges, cardinality restrictions) and that the fixture is well-formed. Exit 0 = pass. |

## Namespace

- Base IRI: `https://github.com/divaspoudel0/enterprise-brain-knowledge-graph-retrieval/ontology`
- Term prefix `eb:` (the base + `#`): all classes/properties live here.
- RDF data produced in S3 reuses these term IRIs unchanged.

## Inventory (matches DATA_PIPELINE.md §1.1)

Classes: `Customer`, `Order`, `Payment`, `Complaint`, `Product`.

Object properties (all declared with `owl:inverseOf` on both sides so multi-hop
traversal in S7 can walk either direction):

| Property | Domain -> Range | Inverse |
|---|---|---|
| `placedOrder` | Customer -> Order | `orderPlacedBy` |
| `forProduct` | Order -> Product | `productOrderedIn` |
| `hasPayment` | Order -> Payment | `paymentForOrder` |
| `filedComplaint` | Customer -> Complaint | `complaintFiledBy` |
| `aboutOrder` | Complaint -> Order | `orderComplainedAbout` |

Data properties: `source_record_id` (provenance pointer, DATA_PIPELINE.md §2),
`id`, `name`, `region`, `signup_date`, `order_date`, `amount`, `status`,
`due_date`, `paid_date`, `filed_date`, `category`, `price`,
`free_text_description`.

Cardinality restrictions (exactly 1) so S5 ground-truth paths are always
well-formed: `Order ⊑ =1 orderPlacedBy ⊓ =1 forProduct`;
`Payment ⊑ =1 paymentForOrder`; `Complaint ⊑ =1 complaintFiledBy ⊓ =1 aboutOrder`.

Enumerated values (payment status `{paid, overdue, failed}`, complaint/product
category) are intentionally **not** modeled as OWL enumerations — they are
enforced as data-level constraints in the S2 generator and `verify_data.py`
(DECISIONS.md "S1 ontology format").

## Validate

```bash
uv run --with rdflib python ontology/validate_ontology.py
```

Requires `uv` and network to fetch `rdflib`. Run after every change to this
directory. The file also opens in Protégé for human inspection.

## Mapping note for S3 (decided at S3)

- **If RDF store**: load the TTL schema + instance data as-is; inverse
  properties give bidirectional traversal natively.
- **If Neo4j**: map classes -> labels, object properties -> relationship types,
  data properties -> node properties; store `source_record_id` on every node
  and relationship; keep relationship direction as the schema (domain -> range)
  and use the inverse when traversing backwards.
