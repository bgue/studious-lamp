# P2-W0-W0-B2 — Load and publish targets found by entry point

Status: ready
Tier: sonnet
Kind: piece
Review: full
Labels: core, legacy, documents
Depends on: —
Branch: `p2/w0-b2`

## Goal
After this piece the legacy loader's targets (`tags`, `documents`) and the documents publish targets are registered names
found through entry-point groups, so a wave-1 module adds its own target by adding a line to its own `pyproject.toml`.
Phase 1 behaviour is unchanged: the P1-I3 and P1-I8 demos give the same results.

## Brief references
`specs/wave0.md` §4 (authoritative; plan check F4):
- **Load** (`tl_mod_legacy`): `TargetKind` (`model.py:15`, a `Literal["tags","documents"]`) becomes a registered name.
  Group `throughline.load_targets`; each entry point returns a `Target` (see `targets.py`; `target_for(kind)` at
  `targets.py:491` becomes a registry lookup). Built-ins `tags` and `documents` are registered by **the legacy package's own
  `pyproject.toml`** (like `throughline.loaders`, `pyproject.toml:21`). A target declares `scope: project | company`;
  `tl load open --company` opens a run for a company target (a company target refused without `--company`, and the
  reverse). **Loads stay admin-only** (owner answer 12; do not change who may run `LoadRun` commands). A generic
  column-mapping form for module targets: a `Target` may be built from a declarative mapping (record type, key column,
  column -> field map) without a handler class; `tags` and `documents` stay explicit. A duplicate target name, a target
  that fails to load, or a name outside `^[a-z][a-z0-9_]*$` is a `ModuleLoadError`-style error naming the group and entry
  point. `tl load targets` lists `name  module  scope`, sorted, one line each, plain words (no ids).
- **Publish** (`tl_mod_documents.derivation.publish`): targets found by group `throughline.publish_targets`, same shape,
  built-ins `tags` and `documents` registered in the documents package's `pyproject.toml`. `PublishDerivedTags` and
  `PublishDerivedDocuments` keep their names, fields and events (a derived row never changes, ADR-0014); create-only
  and exact compensation unchanged. An unknown target is a 422-class error naming the known ones.
- **F4: do not touch `packages/tl-modules/legacy/src/tl_mod_legacy/module.py`** (RM-S2 owns its `command_words` line,
  in parallel). If the registry needs to be reachable from `module.py`, expose it from `model.py`/`targets.py` and say so.
- Entry-point metadata of an editable install is read at install time: run `uv sync` once after editing `pyproject.toml`
  (environment step, no dependency added). Do not add a dependency.
- The demos (`dev/demos/P1-I3.sh`, `P1-I8.sh`) are not edited; they exercise the unchanged CLI.

## Context (<= 10 files)
- `specs/wave0.md` §4; `packages/tl-modules/legacy/src/tl_mod_legacy/{model.py,targets.py,service.py}` (service.py around the `target_for` calls only), `loaders/__init__.py`, `pyproject.toml`
- `packages/tl-cli/src/tl_cli/load.py`; `packages/tl-modules/documents/src/tl_mod_documents/derivation/publish.py` (lines 83-150, 423-600), `documents/pyproject.toml`
may explore: `dev/demos/P1-I3.sh`, `P1-I8.sh`, `packages/tl-core/src/tl_core/readiness/registry.py` (the entry-point loading style of W0-B1, to copy)

## Allowed paths
- `packages/tl-modules/legacy/**` **except** `src/tl_mod_legacy/module.py` (includes its `pyproject.toml`)
- `packages/tl-modules/documents/src/tl_mod_documents/derivation/**`, `packages/tl-modules/documents/pyproject.toml`
- `packages/tl-cli/src/tl_cli/load.py`
- consequential pins (rule 12): a pinned list or help text that changes only because `tl load targets` or the open
  option now exists (e.g. a CLI command-list test); list each in the report
- `dev/accept/P2-W0/W0-B2.py` (create), `docs/reports/P2-W0/W0-B2.md` (create)
Not allowed: `module.py` of any module, `tl_core/**`, `schema/**`, any other CLI file, the demo scripts.

## Acceptance (run these, once; no pytest, no `just gate`)
```
uv sync
just check
uv run tl load targets
just demo P1-I3
just demo P1-I8
uv run python dev/accept/P2-W0/W0-B2.py
```
`uv run tl load targets` prints `documents  legacy  project` and `tags  legacy  project` (two lines, sorted).
`dev/accept/P2-W0/W0-B2.py` (SQLite, exit 0, one `PASS <check>` per check): both built-ins listed with module and scope;
`tl load open` through `tags` and a publish through both publish targets give the same rows/events as before (compare
with the demos' own expectations, do not re-derive); injected extra entry points (pass the iterable like
`load_checks(entry_points=...)`): a duplicate name, a failing import, a bad name and an unknown target each raise with
the named message; a company-scope stand-in target needs `--company` and a project target refuses it; a mapping-form
target loads two rows. **P1-I3 and P1-I8 are the demos the end run repeats on both adapters** (SQLite then Postgres:
`just demo P1-I3`, `just demo P1-I8` with `TL_PG_URL` set as the demo scripts document).

## Tests for the end run (TB writes them; this piece writes none)
`packages/tl-modules/legacy/tests/test_load_targets.py` (registry, duplicate, unknown, scope, mapping form),
`packages/tl-modules/documents/tests/test_publish_targets.py`. Mutants: duplicate target name accepted; unknown target
falls back to `tags`; company target runs without `--company`. Report where each guard sits (file:line).

## Report requirements
Standard piece report (<= 60 lines): deviations first; entry-point names added; pins updated; acceptance output
(<= 5 lines per command; the two demo summary lines).

## Escalation triggers
- *Blocked* if: the registry cannot be built without editing `module.py`; a demo output changes; `LoadRun` command or
  event shapes would have to change (that is a schema change; this piece makes none).

## Blocked
(builder writes here)

## Decision
(supervisor or orchestrator writes here)
