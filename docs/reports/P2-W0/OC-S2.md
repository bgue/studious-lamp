# Report — P2-W0-OC-S2 (offline capture hook, module-load validation, node-kind start-up check)

Branch: `p2/w0-oc-s2`   Commit(s): see `git log p2/w0..p2/w0-oc-s2` (one build commit, this report included)

## Deviations
1. **Extension class is the annotation `tl:offline`, not a bare `offline` key.** LinkML rejects an unknown class-level key;
   the sibling `tl:storage_mode` is an annotation, so `tl:offline` sits under `annotations:` (same name as the core schema).
2. **Load checks are one function, `check_offline(spec)`, called from `_discover`** (not in `ModuleSpec.__post_init__`):
   stand-in specs in existing tests (`use_modules`) keep working. Two extra messages beyond the three: a key the module does
   not own, and a drafting command missing from `command_words`.
3. **`tl tui` calls `tl_tui.main.run` directly**, so the check is in `run`: it prints `error: ...` and `raise SystemExit(2)`
   (a `ServiceError` would escape the `(ValueError, BackendUnavailableError)` catch of `tl_cli/tui.py`, which I may not edit).
4. **API row for `NodeKindNotBuiltError`: 503 `node_kind_not_built`** (the spec names no status; `test_error_table` needs a row).
5. Empty modules get an explicit `offline_drafts={},` line (spec: "one line each"); documents and correspondence are
   multi-line after `ruff format`. `conn` was not needed.

## Changed files
- `tl_core/offline.py` (new) — `NodeKind`, `OfflineDecision`, `offline_class`, `stream_class`, `capture_allowed`,
  `require_capture_allowed`, `node_kind`, `is_authority`, `require_node_built`, `OnlineOnlyError`, `NodeKindNotBuiltError`
- `tl_core/modules.py` — `ModuleSpec.offline_drafts`, `check_offline`, one call in `_discover`
- `tl_core/extypes/{model,compile,provider}.py` — `CompiledType.offline`, annotation read, source cache and accessor
- 7 `module.py` — the `offline_drafts` line; `tl_api/{main,errors}.py`, `tl_tui/main.py` — start-up check, two rows
- `dev/accept/P2-W0/OC-S2.py` — acceptance (43 PASS)

## How the extension class is read
`compile._compile` reads `tl:offline` (missing = `none`, bad value = `TypeIssue(kind="compile")`) into `CompiledType.offline`
(not in `schema_hash`). `LedgerExtensionSource.documents()` records `{type_name: offline}` for each loaded type as it hands
the provider its documents; `attach()` stores the source; `offline_class` asks `attached_offline_class()`: no IO, no `conn`,
no new table. Limit: a process answers `unknown_type`/`none` for an extension type until the provider has read once.
A registered type without the key is `none` (`online_only`), an unregistered one is `unknown_type`.

## Decision-table summary (2604 rows = every type x its module's `command_words` + 4 generic, x 3 nodes; oracle written apart)
authority allowed 868; site and device each allowed 24 (12 draft, 12 full), refused 844 (central_act 391, online_only 323,
not_drafting 130). A command with no declared word (core or generic) is not central: it follows the type class.

## Commands and output
```
$ just check                       -> ruff, format, pyright 0 errors, generated + openapi up to date, licences ok
$ uv run python dev/accept/P2-W0/OC-S2.py   -> 43 PASS, exit 0 (table + 6 sample rows printed)
$ TL_NODE_KIND=device uv run tl serve   -> error: offline replicas arrive in Phase 3   (exit 2)
$ TL_NODE_KIND=site uv run tl tui       -> error: offline replicas arrive in Phase 3   (exit 2)
```
Also: `TL_NODE_KIND=moon tl serve` -> `error: TL_NODE_KIND must be one of authority, site, device` (exit 2). One sentinel
mutant (central_act check disabled) made the acceptance script FAIL; restored.

## Guard sites for TB's mutants (`packages/tl-core/src/tl_core/offline.py`)
`authority` short-circuit :125; unknown type refused :128; `central_act` before the class :130; `draft_only` without
listing refused :136 (the `not_drafting` return after it). Load checks: `modules.py` `check_offline` (:281), call :350.

## Tests added
none (end run: `packages/tl-core/tests/test_offline_capture.py`, `tests/services/test_modules_offline.py`,
`tests/extypes/test_extype_offline.py`). No pytest, no `just gate`, per the piece spec.

## Learnings (proposed)
`tl tui` wraps `tl_tui.main.run`, not `main`; a start-up refusal there must exit itself or be a `ValueError`.

## Open questions / Blocked
none
