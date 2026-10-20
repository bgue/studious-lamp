# tl-mod-schemareg (`tl_mod_schemareg`)

The schema registry module: the ledgered lifecycle of schema packages, per-project adoption pins and waivers, and the source that feeds them into the effective schema (§27.4). Decisions: `docs/tickets/P1-I8/FANOUT.md`, ADR-0010. Spec: `docs/modules/schemareg/README.md`.

## Public interface
| Symbol | Kind | Purpose |
|---|---|---|
| `tl_mod_schemareg.module.spec` | function | The entry point `throughline.modules` / `schemareg`; carries `schema_source` |
| `tl_mod_schemareg.names` | module | Record types, event types, tables, workflow states |
| `tl_mod_schemareg.projectors` | package | `SchemaPackageProjector`, `AdoptionProjector`, `WaiverProjector` |
| `tl_mod_schemareg.handlers.packages` | module | The package commands (draft, revise, analyse, submit, review, publish, deprecate, retire) |
| `tl_mod_schemareg.handlers.adoption` | module | `AdoptSchemaPackage` |
| `tl_mod_schemareg.handlers.waivers` | module | `RequestWaiver`, `ApproveWaiver`, `RevokeWaiver` |
| `tl_mod_schemareg.analysis` | module | The trial schema, the classification and the impact of a draft or a pin (writes nothing) |
| `tl_mod_schemareg.impact` / `impact_types` | modules | `impact_report(old, new, facts)`, a pure function, and its types |
| `tl_mod_schemareg.source` | module | `LedgerRegistrySource`: published packages, pins, approved waivers for `DirectorySchemaProvider` |
| `tl_mod_schemareg.registry` | module | Reads: packages, adoptions, waivers |
| `tl_mod_schemareg.views` | module | Read models for the API, CLI and TUI: `package_summaries`, `package_detail` (reports, lint, text diff), `adoption_views`, `waiver_views`, `drift_views`, `sample_test` |
| `tl_mod_schemareg.commands` | module | `API_COMMANDS` with their access levels |
| `tl_mod_schemareg.testing` | module | `RegistryWorld`: a ledger and a schema provider that reads it, for tests of other packages |

## Depends on / used by
- Depends on: `tl_core` (ledger, services, `schema_provider`), `tl_schema` (packages, classify, compose), `tl_adapters`, `pydantic`, `sqlalchemy`.
- Used by: the platform through its entry point; `tl_api` (`/schema/...` reads, `/commands/<Name>` writes, client in `tl_api.client.schemareg`), `tl_cli` (`tl schema package ...`), `tl_tui` (the workbench, through `TuiClient`).

## Conformance dashboard
`dashboard.conformance_dashboard(conn, project)` is one read of how a project's records stand (brief 27.3, 27.5): per record type the stored `ok`, `warning`, `nonconformant` and `waived` counts and the records checked against an older schema than the one in force (stale, a NULL hash included), the approved waivers with their days left, the expired ones as a count, and the company packages the project is behind on. The stored status is read, never recomputed, and the counts are taken as the current viewer (ADR-0016). CLI: `tl schema conformance --project P [--json]`.

## Commands
```
just test -- packages/tl-modules/schemareg
```

## Configuration
| Setting or env var | Default | Notes |
|---|---|---|
| none | | The bounds are constants in `limits.py` (256 KiB a package, 366 days a waiver) |

## Rules specific to this package
See `AGENTS.md` in this directory.

## Status
Introduced in P1-I8. Last interface change: P1-I8.
