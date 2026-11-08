# P2-INT-T01 — World-date annotation `tl:valid_time`, the module-standard rule, and its lint (ADR-0026 F5)

Status: ready
Tier: haiku
Review: full
Labels: schema, docs, tests
Depends on: —
Branch: `p2/int-t01-valid-time-tag`
Approver (schema tickets only): orchestrator, with an APPROVALS line (touches `schema/core/annotations.yaml`; defines no class, no generated output changes)

## Goal
Wave 3 event payloads can say which field is the world date. After this ticket: `tl:valid_time` (slot-level; value `at`, `from` or `to`) is declared in `annotations.yaml`;
one rule line is in the module standard; a test fails when a module event payload class under `schema/modules/**` has no tagged slot and no baseline entry. No class is tagged here
(back-tagging the ~47 core classes is the Phase 3 projector's, ADR-0026 F5).

## Brief references (pasted)
> ADR-0026 d1: "Valid time comes from payload fields tagged `tl:valid_time` in the schema; an untagged fact has valid time unknown and says so. Envelope `effective_at` is never read as world time."
> F4: `tl:valid_time` takes `at`, `from` or `to` and marks only when-it-happened fields; deadlines and plans (`due_date`, `promised_date`, `forecast_date`, `expires_at`, `data_date`) are values, not valid time.
> F5: the stub is the annotation declared in `annotations.yaml`, one rule in the module standard, 1 lint ticket so wave 3 events carry the tag. An annotation applies to old events without upcasting.
> Rule text (use verbatim, one line, in each module README template): *every event payload class names its world-date field with `tl:valid_time` (`at` for a moment, `from`/`to` for a span), or the class is listed with a reason in `tests/tools/valid_time_baseline.toml`; deadlines, forecasts and expiry dates are never tagged.*

## Interfaces (verbatim from repo at the branch point)
`schema/core/annotations.yaml` description block lists tags by level; add under "Slot-level tags":
```
  - `tl:valid_time` (`at` | `from` | `to`): this payload slot is the world date of the fact the event records
    (ADR-0026). `at`: the moment it happened; `from` / `to`: the start / end of a span. Never a deadline, forecast or
    expiry. At most one `at`, or one `from` and one `to`, per payload class. No generator reads it yet.
```
Baseline file format (create; generated once by a script in the test module, `--write-baseline` flag, then committed):
```toml
# class = reason; generated from schema/modules/** at P2-INT; new classes must tag a slot or be added with a reason
["tl_mod_x.SomeEvent"] = "pre-wave-3, untagged"
```

## Context (read these, nothing else)
- `schema/core/annotations.yaml` (description block, slot-level tags)
- `packages/tl-schema/AGENTS.md` (rule: a tag is read only if the file names it)
- `packages/tl-schema/tests/test_linkml_render.py` (how tests load schema files and read annotations)
- `docs/templates/package-readme.md` (module README template)
may explore: `schema/modules/materials/*.yaml` (a module event payload class with `tl:event_type`)

## Allowed paths
- `schema/core/annotations.yaml` (description text only)
- `docs/templates/package-readme.md` (the rule line, under the module standard section; create the section if missing)
- `packages/tl-schema/tests/test_valid_time_tag.py` (create), `tests/tools/valid_time_baseline.toml` (create)
- `docs/reports/P2-INT/T01.md` (create)

## Steps
1. Add the annotation text and the rule line.
2. Test: load every schema under `schema/modules/**`; (a) every `tl:valid_time` value is `at`, `from` or `to`; (b) per class, one `at`, or at most one `from` and one `to`, never mixed; (c) the slot is of a date or datetime range; (d) every class with `tl:event_type` has a tagged slot or is in the baseline; (e) a baseline key naming a class that no longer exists, or one that now has a tag, fails (the baseline only shrinks).
3. `--write-baseline` writes the file from the current schema; run it once, commit the result.
4. `just gen`; it must report no drift.

## Acceptance
```
just check
uv run pytest packages/tl-schema/tests/test_valid_time_tag.py -q
```
Expected: all pass; no generated file changes.

## Tests to add
`packages/tl-schema/tests/test_valid_time_tag.py` as in Steps 2; include a synthetic schema in `tmp_path` for each failure case (bad value, mixed, untagged event class, stale baseline entry).

## Report requirements
Standard (`docs/templates/haiku-report.md`) plus the count of baseline entries.

## Escalation triggers
- Stop and report *Blocked* if any generator or existing test reacts to an unknown annotation, or if a core class needs a tag to pass.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
