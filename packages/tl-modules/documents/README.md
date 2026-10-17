# tl-mod-documents (`tl_mod_documents`)

The documents module (M1): documents, revisions, renditions, pinned links that go stale, transmittals, review cycles and
the legacy register import, with the projectors, commands, reads and reports that serve them (§9 M1, §7.3, §29.6).
Decisions: ADR-0010, ADR-0011 (superseded in part), ADR-0012, ADR-0013.

## Public interface
| Symbol | Kind | Purpose |
|---|---|---|
| `tl_mod_documents.module.spec` | function | The entry point `throughline.modules` / `documents`: record types, projectors, generic-command allow-lists and state guards |
| `tl_mod_documents.names` | module | Record types, event types, workflow and list names as constants |
| `tl_mod_documents.projectors` | package | `DocumentProjector`, `RevisionProjector`, `RenditionProjector`, `TransmittalProjector`, `ReviewCycleProjector` |
| `tl_mod_documents.registry` | module | Reads: `get_document`, `find_document`, revisions, renditions, transmittals, review cycles (frozen rows joined with `cur_core_record`) |
| `tl_mod_documents.schemes` | module | The revision scheme engine and the issue statuses with their class (`load_scheme_file`) |
| `tl_mod_documents.handlers.documents` | module | `RegisterDocument`, `UpdateDocument`, `SetDocumentConfidentiality`, `SupersedeDocument`, `VoidDocument`; `register_problems` / `field_problems` (what the command would refuse) |
| `tl_mod_documents.handlers.revisions` | module | `CreateRevision`, `IssueRevision`, `SupersedeRevision`, `VoidRevision` |
| `tl_mod_documents.handlers.renditions` | module | `AttachRendition`, `RegisterSignedRendition`, `ReplaceSignedRendition`; `check_rendition` / `preflight_rendition` (file-free checks the CLI runs before uploading) |
| `tl_mod_documents.handlers.transmittals` | module | `CreateTransmittal`, `IssueTransmittal`, `RecordTransmittalResponse`, `CloseTransmittal`, `VoidTransmittal` |
| `tl_mod_documents.handlers.reviews` | module | `OpenReviewCycle`, `RecordReviewOutcome`, `CloseReviewCycle`, `RecordReviewOutcomeOnBehalf`, `OverrideReviewOutcome` |
| `tl_mod_documents.resolver` | module | Links to documents: `LinkToDocument`, `RepinDocumentLink`, `resolve_pin`, `links_to_documents`, `revision_diff`, `affects_pin` (the class-aware stale rule), `flag_stale_on_issue` |
| `tl_mod_documents.guards` | module | The state guards of the generic commands (uploads into a revision, a draft transmittal) |
| `tl_mod_documents.views` | module | `DocumentView`, `RevisionView`, `DocumentLinkView`, `TransmittalView`, `RevisionDiffView` and their readers: what the API, the TUI and the MCP tools return |
| `tl_mod_documents.reports` | module | Register, history, overdue reviews, transmittal log, stale pins |
| `tl_mod_documents.commands` | module | `API_COMMANDS`: the 24 commands the API offers, each with its `access` (`user` or `controller`: an admin or a document controller, action `control.command.<Name>`) |
| `tl_mod_documents.imports` | package | Legacy register import: `mapping` (template, `read_file_text`, `read_rows`), `diff` (`plan_import`), `apply` (`apply_plan`, all or nothing, source `import:<job>`), `model` |
| `tl_mod_documents.limits` | module | Size limits of commands and of an import file; `CONFIDENTIALITY_NOTE` |
| `tl_mod_documents.testing` | module | `DocumentsWorld`: documents, revisions, files and links in a ledger, for tests of other packages |
| `tl_mod_documents.derivation` | package | The derivation pipeline (P1-I3, ADR-0014; spec `docs/modules/documents/derivation.md`): `schemas`, `derived`, `jobs` (the `extract` and `validate` job kinds), `validation` and `validation_isolated` (validation in a child process), `diff`, `mapping`, `publish` (create-only, correlated, compensation by recorded ids), `views` (the reads), `store` (rows and reports as files, a small parse cache), `worker` (`build_worker`, `requeue_orphans`) |

## Depends on / used by
- Depends on: `tl_core` (ledger, services, `tl_core.modules`), `tl_schema` (generated DDL), `tl_adapters`, `tl_mod_engineering` (code lists and the document number pattern), `pydantic`, `pyyaml`, `sqlalchemy`.
- Used by: the platform through its entry point; `tl_cli` (`doc`, `transmittal`, `review`), `tl_api` (routes and client), `tl_tui` (`F7`), `tl_mcp` (seven read tools) and `tl_sim` (`document_registrar`).

## Commands
```
just test packages/tl-modules/documents
uv run pytest packages/tl-modules/documents -q --adapters sqlite,postgres   # needs TL_PG_URL
uv run tl doc register ISO-1234 --project P123 --title "Isometric" --type ISO --discipline PIP
```

## Confidentiality in Phase 1
In Phase 1 confidentiality is recorded but not enforced: every signed-in person and every agent can read all documents and transmittals of a project, including recipient emails.

## Configuration
| Setting or env var | Default | Notes |
|---|---|---|
| `schema/fixtures/documents/revision-schemes.yaml` | the committed file | Revision schemes, issue statuses with their class, and which scheme numbers which documents |
| `TL_OBJECT_ROOT` | per environment | Where renditions are stored (the object store of the file service) |

## Rules specific to this package
See `AGENTS.md` in this directory.

## Status
Introduced in P1-I2. Module spec: `docs/modules/documents/README.md`; schema: `schema/modules/documents/`; plan: `docs/tickets/P1-I2/README.md`; runbook: `docs/runbooks/documents.md`.
