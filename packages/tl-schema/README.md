# tl-schema (`tl_schema`)

The schema runtime: generators that turn the LinkML sources in `schema/` into Pydantic models, JSON Schema, and current-state DDL for SQLite and Postgres (§5.4, §6.1, §14), plus the package registry, the effective-schema compiler, JSON Schema validation, form metadata, conformance and lint for company and project pset packages (§6.3, §27).

## Public interface
| Symbol | Kind | Purpose |
|---|---|---|
| `tl_schema.generate` (`python -m tl_schema.generate [--check]`) | module / command | Runs every generator; `--check` fails when committed output differs (codegen drift gate, §25.4) |
| `tl_schema.generate.GENERATORS`, `outputs()` | list, function | The registered generators and their combined `{path: text}` output |
| `tl_schema.generators.pydantic_gen`, `jsonschema_gen` | modules | LinkML to Pydantic v2 and JSON Schema (run inside `schema/core` so no absolute paths leak) |
| `tl_schema.generators.ddl.generate` | function | Classes annotated `tl:current_state` to `cur_<module>_<class>` DDL per dialect |
| `tl_schema.generators.ddl_types.column_type`, `sql_literal` | functions | LinkML built-in type to SQL type and DEFAULT literal, table driven |
| `tl_schema.ddl_loader.statements(table, dialect)` | function | Reads the committed generated DDL at runtime, one string per statement |
| `tl_schema.generators.promoted`: `promoted_columns`, `column_ddl` | functions | `ALTER TABLE` statements for `materialize: true` pset properties (`pset__<pset>__<property>`) |
| `tl_schema.packages`: `PackageDoc` and friends | models | The package YAML subset: company, extension and project packages (unknown keys are errors) |
| `tl_schema.registry`: `PackageRegistry`, `parse_package`, `load_package`, `default_schema_dir` | class, functions | Load `schema/fixtures/*.yaml`, versions, pins, `adopted(scope)`, `check()`, `fingerprint()` |
| `tl_schema.compile.compile_psets`, `SchemaCompileError` | function, exception | Resolve packages into psets; every "projects cannot" rule has a `rule` code |
| `tl_schema.compose`: `compose`, `EffectiveCache`, `core_digest` | functions, class | `EffectiveSchema` for a scope with its content hash; artefacts cached by hash |
| `tl_schema.effective`: `EffectiveSchema`, `EffectivePset`, `EffectiveProperty`, `states_cover`, `required_in` | models, helpers | The resolved, hashable schema every runtime reader uses |
| `tl_schema.validation`: `record_json_schema`, `validate_psets` | functions | JSON Schema of a record type's `psets`; structured value issues |
| `tl_schema.conformance.evaluate` | function | `ok / warning / nonconformant / waived` for a record's psets, state and date |
| `tl_schema.formgen.form_metadata` | function | `FormMetadata` for the TUI (contract models in `tl_schema.forms`) |
| `tl_schema.lint.lint_documents` | function | Lint rules L001 to L007 over package documents |
| `tl_schema.linkml_render`: `build_view`, `linkml_yaml` | functions | The effective schema as LinkML (pset classes merged into core) for lint and export |
| `tl_schema.generators.catalog.generate`, `build_events` | functions | The event catalog from the `tl:event_type` classes in `schema/core/events.yaml`: a CloudEvents JSON Schema and a sample per event type, `catalog/asyncapi.json`, `docs/event-catalog.md` (all under `generated/`) |
| `tl_schema.catalog`: `event_types`, `envelope_schema`, `sample`, `asyncapi` | functions | Read the committed catalog at runtime (`tl webhook test`, contract tests) |
| `tl_schema.catalog_asyncapi.asyncapi_document`, `catalog_markdown.render_catalog_markdown`, `catalog_types.EventTypeInfo` | functions, model | Pure renderers of the catalog and the data they take |
| `tl_schema.generated.*` | package | Generated output. Never edit by hand |

## Depends on / used by
- Depends on: `schema/core/*.yaml` (LinkML sources), `schema/fixtures/*.yaml` (package files), `linkml`, `linkml-runtime`, `pydantic`, `jsonschema`, `pyyaml`.
- Used by: `tl_core` (projectors load generated DDL; pset services use the effective schema), `tl_cli` (`tl schema`).

## Commands
```
just gen
just check
just test packages/tl-schema
```

## Configuration
| Setting or env var | Default | Notes |
|---|---|---|
| `--out DIR`, `--schema-dir DIR` | `generated/`, `schema/core` | Test hooks for `tl_schema.generate` |
| `TL_SCHEMA_DIR` | `schema/fixtures` | Directory of package files read by the registry |

## Rules specific to this package
See `AGENTS.md` in this directory.

## Status
Introduced in P0-I1. Last interface change: P0-I5 workstream B (event catalog, `schema/core/integration.yaml`, `outbox.yaml`, `events.yaml`; `docs/tickets/P0-I5/README-B.md`). Before that: P0-I2 workstream A (decisions A1 to A19 in `docs/tickets/P0-I2/README-A.md`). P0-I3 added the `core.Link`, numbering and workflow classes and the `tl:expects_link` annotation to `schema/core` (current-state tables `cur_links`, `cur_link_counts`, `cur_numbering`, `cur_workflow_state`). P0-I6 workstream A added `schema/core/feed.yaml` (`ActivityPost`, `EventCard`, `Hashtag`, `FeedItemRow`, the `Feed.*` payload classes; tables `cur_feed_items`, `cur_feed_tags`). P0-I6 workstream B added `schema/core/proposals.yaml` (`Proposal.Created|Accepted|Rejected|Failed` payload classes and `ProposalRow`; table `cur_proposals`). Known gaps: `class_filter` is parsed, not evaluated; waivers are declared in a package, not ledgered records.
