# P2-W0-OC-T3 — `tl new record-type` scaffolds `tl:offline: none`

Status: ready
Tier: haiku
Kind: ticket
Review: lite
Labels: cli
Depends on: OC-S1 (merged)
Branch: `p2/w0-t06-scaffold-offline`

## Goal
A record type made with `tl new record-type <module>.<Class>` carries `tl:offline: none` and a comment asking its author for
the reason, so a scaffolded type passes `just gen` (a record type without a class fails it) and the author decides on purpose.

## Brief references (pasted)
> offline-classes spec 5.1: "`tl new record-type` scaffolds `tl:offline: none` with a comment asking for a reason." Fail closed:
> `none` is online only.

## Interfaces (verbatim from repo at the branch point)
```yaml
# packages/tl-cli/src/tl_cli/scaffold/templates/record_type/schema.yaml.tmpl (lines 17-26, existing)
classes:
  ${cls}:
    is_a: RecordEnvelope
    description: >-
      TODO: what a ${cls} is.
    annotations:
      tl:current_state: true
```
Change: add, as the first two lines of that `annotations:` block (same indent as `tl:current_state`):
```yaml
      # TODO: why this class? full = edited offline and merged; draft_only = drafted offline, issued online; none = online only.
      tl:offline: none
```
Do not touch `record_type.py`, `new.py` or the other templates.

## Context (read these, nothing else)
- `docs/templates/haiku-report.md`
- `packages/tl-cli/src/tl_cli/scaffold/templates/record_type/schema.yaml.tmpl`
- `packages/tl-cli/tests/expected/record_type/weld_inspection.yaml` (the pinned output; `test_cli_new_record_type.py` compares byte for byte)
- `schema/modules/documents/document.yaml` (lines 28-36: how a real class writes the annotation)
may explore: (none)

## Allowed paths
- `packages/tl-cli/src/tl_cli/scaffold/templates/record_type/schema.yaml.tmpl` (modify)
- `packages/tl-cli/tests/expected/record_type/weld_inspection.yaml` (modify: consequential pin, rule 12; the same two lines with `inspection`/`WeldInspection` filled in; keep the rest byte-identical)
- `docs/reports/P2-W0/OC-T3.md` (create)

## Acceptance (run these, once; do NOT run pytest, tests are deferred to the increment's end run)
```
just check
T=$(mktemp -d); uv run tl new module demo --root $T && uv run tl new record-type demo.Weld --root $T
grep -n -B1 "tl:offline" $T/schema/modules/demo/weld.yaml
diff <(sed 's/Weld/WeldInspection/g;s/demo/inspection/g;s/weld/weld_inspection/g' $T/schema/modules/demo/weld.yaml) packages/tl-cli/tests/expected/record_type/weld_inspection.yaml | head
```
Expected: `just check` clean; the grep prints the comment line then `tl:offline: none`; the diff is empty or only differences you can name (paste it; the `sed` is a rough check, not a gate).

## Tests to add
None (the provided `test_cli_new_record_type.py` is not edited and runs in the end run against the updated expected file).

## Report requirements
Standard report plus the pasted grep and diff output, and a line that no pytest was run.

## Escalation triggers
- Stop and report *Blocked* if the new line makes `ruff`/`just check` fail on the template, or the expected file differs elsewhere than these two lines.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
