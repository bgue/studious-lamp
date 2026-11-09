# P2-REL-S1 — Installable wheels: one resource locator, data inside the wheels

Status: ready
Tier: builder
Kind: piece
Review: full
Labels: core, packaging
Depends on: trunk
Branch: `p2/rel-s1-wheels`   (from claude/wizardly-allen-m2v96s)
Wave 2: no (touches no IWP or constraint CLI)

## Goal
After this piece `uv build --wheel` of `tl-schema`, `tl-core`, `tl-cli` and the module packages gives wheels that work
outside a checkout: the schema directories and the settings and access-word tables are inside the wheels and found
through one function. A checkout behaves exactly as before.

## Why (facts, from the code)
`Path(__file__).resolve().parents[4|5]` is how these find repository data (cite, do not paste):
`packages/tl-schema/src/tl_schema/registry.py:25` (`DEFAULT_SCHEMA_DIR`, `schema/fixtures`), `linkml_render.py:39` and
`generate.py:18` (`schema/core`), `packages/tl-core/src/tl_core/auth/access_words.py:29` (`schema/settings/access-words.yaml`),
`auth/module_roles.py:49` and `settings/registry.py:34` (`_REPO_ROOT`). No `pyproject.toml` ships data. Each module package
may also read `schema/modules/<m>` and `schema/fixtures`: grep `schema/modules` under `packages/` and list every hit in
the report before changing any.

## Requirements
1. New module `tl_schema.resources` (the only new public name): `schema_root() -> Path` returns `<repo>/schema` when that
   directory exists next to the source tree (a checkout, editable install), else the packaged copy under
   `tl_schema/_data/schema` (use `importlib.resources.files`). `TL_SCHEMA_DIR` keeps its meaning and still wins for the
   fixtures directory (`default_schema_dir`).
2. The five constants above (and any further hit your grep finds) use `schema_root()`. No behaviour change in a checkout;
   `just gen` drift check stays clean (generated code is not edited).
3. `packages/tl-schema/pyproject.toml` ships `schema/` into the wheel as `tl_schema/_data/schema` (hatch
   `force-include`, source path relative to the workspace root; make sure an sdist build also works, or say it is not
   supported and why). Only YAML and text: no `*.db`, no `dev/data`. If a module package needs its own schema directory
   at run time, ship it the same way and list it.
4. Tests (new, in `packages/tl-schema/tests/test_resources.py`): (a) in a checkout `schema_root()` is the repository
   `schema/`; (b) with the repo-relative lookup forced off (monkeypatch the probe), it returns the packaged path; (c) a
   built wheel of `tl-schema` (`uv build --wheel --out-dir <tmp_path>`, offline) lists `tl_schema/_data/schema/core/core.yaml`
   and `.../settings/access-words.yaml` and contains no file ending `.db`, `.sqlite` or `tokens.json`. Mark (c) with the
   repository's slow marker if one exists; otherwise keep it, it builds one small wheel.
5. Proof outside a checkout, run once and quoted in the report: build the wheels of `tl-schema` and `tl-core`, install both
   into a temporary venv created outside the repository (`uv venv`, `uv pip install --no-deps`, plus whatever imports
   need), and from `/tmp` run `python -I -c "from tl_core.auth.access_words import ...; from tl_schema.registry import default_schema_dir; print(default_schema_dir().exists())"`.
   Expected `True`. If a further dependency stops the import, say which and stop; that is a finding, not a reason to widen.

## Constraints
- No schema (`schema/**`) edit, no generated-code edit, no new dependency. The interface line for the orchestrator:
  `tl_schema.resources.schema_root` (new, additive).
- Dialect-neutral rules and AGENTS.md "Never" list apply. Do not touch `tl-api`, `tl-tui`, `tl-cli`.

## Allowed paths
- `packages/tl-schema/src/tl_schema/resources.py` (create), `registry.py`, `linkml_render.py`, `generate.py`
- `packages/tl-schema/pyproject.toml`, `packages/tl-schema/tests/test_resources.py` (create)
- `packages/tl-core/src/tl_core/auth/access_words.py`, `auth/module_roles.py`, `settings/registry.py`
- any further file your grep lists, each named in the report's first lines as a deviation
- `docs/reports/P2-REL/S1.md` (create)

## Acceptance (run once each)
```
just check
just gate packages/tl-schema packages/tl-core/tests/auth packages/tl-core/tests/settings
```
Expected: `gate: PASS`; the step 5 proof prints `True`.
Mutation (builder, own worktree, 3 lines in the report): one sentinel plus at most 3 mutants: probe returns repo path
always (test b must fail), packaged path wrong (test c or the step 5 proof must fail), wheel config drops settings (test c must fail).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), ≤ 60 lines: the grep list of data paths and what you did with each,
the step 5 output, the wheel file count, the mutation lines. Candidate learnings go in the report.

## Escalation triggers
- A package whose runtime data lives outside `schema/` (templates, fixtures under `dev/`): list it, stop on that one.
- `just gen` shows drift after the move.
- The wheel exceeds 20 MB.

## Blocked
(builder writes here)

## Decision
(supervisor or orchestrator writes here)
