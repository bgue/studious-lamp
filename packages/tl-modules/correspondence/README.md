# tl-mod-correspondence (`tl_mod_correspondence`)

The correspondence module (M10): letters, emails and minutes with their numbers, threads, parties, contract clauses, response
clocks on a project calendar, the General and Document-control domains, and the master register (§9 M10, §18.10, ADR-0010,
ADR-0013, ADR-0016).

## Public interface
| Symbol | Kind | Purpose |
|---|---|---|
| `tl_mod_correspondence.module.spec` | function | The entry point `throughline.modules` / `correspondence`: record types, projectors, generic-command allow-lists and guards, the confidential record types |
| `tl_mod_correspondence.names` | module | Record types, event types, states, vocabularies and file slots as constants |
| `tl_mod_correspondence.projectors` | package | `CorrespondenceProjector`, `ThreadProjector`, `ClockProjector`, `PartyProjector`, `ClauseProjector` |
| `tl_mod_correspondence.registry` | module | Reads: items, threads, clocks, parties, clauses (frozen rows joined with `cur_core_record`, filtered by the viewer) |
| `tl_mod_correspondence.handlers` | package | The commands: `items` (`ReceiveCorrespondence`, `UpdateCorrespondence`), `triage` (`ConfirmTriage`, `ReclassifyCorrespondence`), `responses` (`DraftCorrespondence`, `RecordResponse`, `CloseCorrespondence`, `VoidDraft`, `VoidCorrespondence`), `issue` (`IssueCorrespondence`), `threads` (`AssignThread`, `SupersedeCorrespondence`), `clocks`, `parties`, `clauses`, `confidentiality`, `mail` (`IngestEmail`, `read_email`, `ingest_email`) |
| `tl_mod_correspondence.handlers` (P1-I6: `technical`, `technical_flow`, `commercial`, `commercial_flow`, `escalate`) | package | The Technical and Commercial commands and their flows; `escalate` (`EscalateTechnical`) turns an RFI with a cost or schedule impact into a linked Early Warning (Draft) and writes nothing on the RFI stream |
| `tl_mod_correspondence.evidence`, `export`, `registry_domain`, `reports_technical`, `reports_commercial`, `views_domain` | modules | New in P1-I6: the evidence trail, the bounded register export, the domain registry, the Technical and Commercial reports, and the domain views |
| `tl_mod_correspondence.commands` | module | `API_COMMANDS`: the 47 commands the API offers (24 of them `controller`), each with its `access` (`user` or `controller`) |
| `tl_mod_correspondence.clocks`, `calendars` | modules | The clock engine (a pure replay of events) and the versioned project calendars |
| `tl_mod_correspondence.domains`, `catalog`, `sources` | modules | Domain files compiled and cached by content hash; register sources (`documents.transmittal`) |
| `tl_mod_correspondence.suggest` | module | `suggest`: the triage suggestion engine (a pure function of the text and the domain files) |
| `tl_mod_correspondence.threading` | module | The pure threading rules (`match_thread`, subject normalisation, item numbers in a text) |
| `tl_mod_correspondence.letter` | module | The deterministic letter text and PDF |
| `tl_mod_correspondence.eml`, `eml_isolated` | modules | The bounded EML parser and its call inside the resource envelope |
| `tl_mod_correspondence.views` | module | `ItemView`, `RegisterLineView`, `ClockView`, `ThreadView`, `PartyView`, `ClauseView`, `DomainView`, `SuggestionView`: what the API, the CLI, the TUI and the MCP tools return |
| `tl_mod_correspondence.testing` | module | `CorrWorld`: items, clocks, parties and clauses in a ledger (commands and `forge_*` helpers that write raw events), for tests of other packages |

## Depends on / used by
- Depends on: `tl_core` (ledger, services, confidentiality, files, numbering, workflow), `tl_schema` (generated DDL), `tl_adapters`, `tl_mod_documents` (the transmittal register source, the file service), `pydantic`, `pyyaml`, `sqlalchemy`.
- Used by: the platform through its entry point; `tl_cli` (`tl corr`, `tl rfi`, `tl comm`, `tl evidence`), `tl_api` (routes, client, command table), `tl_tui` (`F12`), `tl_mcp` (ten read tools, five from P1-I5 and five from P1-I6, and `propose_triage`).

## Commands
```
just test packages/tl-modules/correspondence
uv run pytest packages/tl-modules/correspondence -q --adapters sqlite,postgres   # needs TL_PG_URL
uv run tl corr receive --project P123 --subject "Revised programme" --file letter.pdf
just demo P1-I5
```

## Confidentiality
Enforced (ADR-0016): `internal`, `restricted` or `privileged` (named readers). A clock, thread, file, event or proposal that
belongs to a hidden item is hidden with it, and a hidden item answers as one that never existed. Every read in `registry` and
`views` filters by the viewer; the worker and projectors read as the system. See `docs/modules/correspondence/README.md`.

## Configuration
| Setting or env var | Default | Notes |
|---|---|---|
| `schema/fixtures/correspondence/domains/*.yaml` | the committed files | The domains in force |
| `schema/fixtures/calendars/<code>@<version>.yaml` | `P123-default@1` | Project calendars; a version never changes |
| `TL_OBJECT_ROOT` | per environment | Where letters, originals, renditions and attachments are stored |

## Rules specific to this package
See `AGENTS.md` in this directory.

## Status
Introduced in P1-I5; Technical, Commercial and the evidence trail added in P1-I6 (plan: `docs/tickets/P1-I6/README.md`). Module spec: `docs/modules/correspondence/README.md`; schema: `schema/modules/correspondence/`; plan: `docs/tickets/P1-I5/README.md`; runbook: `docs/runbooks/correspondence.md`.
