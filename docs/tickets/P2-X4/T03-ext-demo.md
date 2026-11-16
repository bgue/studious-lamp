# P2-X4-T03 — Fixture module `ext_demo`

Status: staged (dispatch after S4 merged; S4 fixes the marks rule this fixture must satisfy)
Tier: haiku
review: full
Labels: tests
Depends on: S4 merged. Disjoint from T02b (tests tree only).
Branch: `p2/x4-t03-ext-demo`
Worktree: `/home/user/wt/x4/t03`

## Goal
A tiny module that exists only under `tests/ext_demo/`, declared only through hooks, so the conformance run and the demo (T05) exercise a module nobody edited `tl-api`, `tl-mcp` or `tl-cli` for.
Package `tl_mod_ext_demo` (path `tests/ext_demo/src/tl_mod_ext_demo/`), record type `ext_demo.Note`, one command `ExtDemoAddNote` (access `user`, mark `excluded:reserved` in row `meta`, a handler like the
`record_type/handler.py.tmpl` pattern), one read route `GET /modules/ext_demo/notes/{key}` (record text: answers a hidden or missing key with the same 404), one tool `ext_demo_get_note` (same answer), one CLI group
`ext_demo`. A `conftest.py` fixture `ext_demo_spec` puts `tests/ext_demo/src` on `sys.path` and returns the spec for `use_modules`. The supervisor pastes the interfaces from the merged S4, T02a and T02b in
round 4; the ticket stays staged until then.
## Tests to add
`tests/ext_demo/test_ext_demo_conformance.py`: the S4 rules pass for `ext_demo` (word, mark in meta, row-or-exclusion by proposable row), five-reader walk of the route and the tool (hidden equals missing, phrase 140),
refused without the word, the tool closed until allowed.
## Acceptance
```
just check
just gate tests/ext_demo/test_ext_demo_conformance.py tests/services/test_module_conformance.py tests/tools/test_registry_by_hooks.py
```
Allowed paths: `tests/ext_demo/**` (create), `docs/reports/P2-X4/T03.md`. Not installed in the workspace, never an entry point: only tests load it.
