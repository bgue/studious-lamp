# Runbook — derived documents: run the worker, read a failure, publish, take it back

Purpose: operate the derivation pipeline (P1-I3, ADR-0014): schemas, extraction jobs, validation, publication into tags or
documents, and compensation. Brief: §9 M1, §24.5, §16 exit. Module page: [derivation](../modules/documents/derivation.md).

## When to use
- Trigger: a derived document is stuck in `Processing`, a job `failed`, a publication has to be previewed, approved or taken
  back, or the queue was lost after a restore.

## Before you start
- Access needed: any signed-in person opens, starts, validates and cancels; **admin** registers schemas, publishes tags and
  compensates; a **document controller** (or admin) publishes documents and voids a derived document (ADR-0013). Sign in with
  `tl login NAME`; `--actor` must be you.
- `TL_DB` names the ledger; `TL_OBJECT_STORE` / `TL_OBJECT_ROOT` (and `TL_OBJECT_SECRET` outside a dev setup) name the object
  store the rows and reports live in. The worker and every command that reads rows must see the same store.
- Safe to run during business hours: yes. A worker only reads files and appends events; a publication is one transaction.

## Steps
### 1. Register a schema (admin, once per version)
```
uv run tl derive schema register schema/fixtures/document-schemas/instrument-index@1.0.0.schema.json --company
uv run tl derive schema ls
uv run tl derive schema show instrument-index
```
Expected: `registered instrument-index@1.0.0 company`. A refused schema lists every problem (a pattern over 200 characters, a
reference loop, a mapped column that is not a property). Versions only go up; `retire` hides a version from new work.

### 2. Open, feed and start
```
uv run tl derive open ISD-001 A --schema instrument-index --project P123
uv run tl derive content ISD-001@A/instrument-index data.csv --project P123
uv run tl derive start ISD-001@A/instrument-index --project P123
```
`start` only queues a job. With no `content` file it reads the revision's PDF (metadata only: content extraction is stubbed,
ADR-0008 decision 8).

### 3. Run the worker
```
uv run tl derive worker --once          # run what is queued, then exit
uv run tl derive worker                 # keep running; Ctrl-C ends it cleanly
```
Several workers may run on one ledger; a job is claimed with a lease (300 s) and a worker that dies loses it to the next one.
`uv run tl derive ls --project P123` and `uv run tl derive jobs --project P123` show where things stand; the TUI shows the same on
F11 (job monitor with `j`).

### 4. Read the result
```
uv run tl derive show  ISD-001@A/instrument-index --project P123
uv run tl derive report ISD-001@A/instrument-index --project P123          # issues by row and column
uv run tl derive rows   ISD-001@A/instrument-index --project P123 --limit 20
uv run tl derive diff   ISD-001@A/instrument-index --project P123          # against the previous pass
```
`Invalid` means the report has errors: fix the file, `content` again, `start` again; each pass is kept. `check` validates the
stored rows against another schema version without storing anything (`--schema instrument-index@1.1.0`).

### 5. Publish (preview, then approve)
```
uv run tl derive publish ISD-001@A/instrument-index --project P123                  # preview
uv run tl derive publish ISD-001@A/instrument-index --project P123 --apply          # admin (tags)
uv run tl derive publish ISD-001@A/instrument-index --project P123 --apply --skip-existing
```
The preview lists `+` rows to create, `=` rows that exist (`differs` when their values differ) and `!` invalid rows. A publication
creates records; it never changes existing ones (change them with `tl tag import --apply`). It is one correlated import; every
record gets the pset `provenance` and a `derived_from` link. An agent can only `propose_import`; a person accepts it in the review
queue and needs the same role (`tl proposal accept`).

### 6. Take a publication back (admin)
```
uv run tl derive compensate ISD-001@A/instrument-index --project P123 --reason "wrong file"           # preview
uv run tl derive compensate ISD-001@A/instrument-index --project P123 --reason "wrong file" --apply
```
Compensation reverses exactly the records and links the publication recorded, all or nothing; one record that cannot be reversed
(a tag that was superseded, a document that got a revision) stops it and is named. The original events stay. A compensated key
cannot be published again.

### 7. After a restore
`job_queue` is not in the archive. Queue again the jobs the ledger says are waiting or running:
```
uv run tl derive worker --requeue --once
```
Expected: `requeued <n>`.

## Failure codes of a job
| `tl derive jobs` note | Meaning | What to do |
|---|---|---|
| `extraction_limit` | The extractor used more time, memory or CPU than allowed, or died. Final. | The file is too big or hostile; use a CSV/XLSX the owner prepared, or split the file. |
| `validation_limit` | The schema's patterns took too long on the rows. Final. | Ask an admin to register a version with simpler patterns. |
| `schema_unusable` | The schema cannot be applied (a reference loop or a reference that does not resolve). Final. | Register a corrected version. |
| `contract_violation` | The extractor's answer broke the contract (too large, over a bound). Final. | Report the file to the extractor owner. |
| `no_extractor` | No extractor accepts the file, or the name is unknown. | Use a CSV, XLSX or a PDF/image (metadata only), or name `--extractor`. |
| `extractor_crashed` | The plugin raised. Tried up to 3 times. | See the server log. |
| `job_missing` | The queue row had no job record (a restore mix-up). Failed for good. | `worker --requeue` after the ledger is complete. |

Messages never carry a path or a trace; the server log has the detail. The API answers `503 extractor_unavailable` when an installed
extractor cannot be loaded.

## Verify
- `tl derive show` says `state Published` and `published <n> records`; `tl tag report` (or `tl doc ls`) lists the records.
- After a compensation: `state Valid`, the tags `Deleted`, the `derived_from` links retracted.
- `uv run tl derive jobs --state queued` is empty when the worker is caught up.

## Roll back
- A wrong publication: step 6. A wrong schema version: `tl derive schema retire`. A stuck job: `tl derive cancel JOB_ID` (only
  while queued); a running job whose worker died is reclaimed when its lease ends.

## Related
- [ADR-0014](../adr/0014-derivation-pipeline.md), [documents](documents.md), [proposal-review-queue](proposal-review-queue.md),
  [engineering-standards-and-tags](engineering-standards-and-tags.md), [object-store-reconciliation](object-store-reconciliation.md).
- Limits: rlimits bound time and memory, not the filesystem or the network; a sandbox is a follow-up (ADR-0014).
