# P2-INSP-T14 - Demo `dev/demos/P2-INSP.sh`: seven clauses, SQLite then Postgres

Status: staged (r6; dispatch after INSP-T10 merges; base `p2/ip-r3` head at dispatch)
Tier: haiku
Kind: ticket
Review: full
Labels: demo, tests
Depends on: P2-INSP-T03, T04, T05, T06, T07, T10, S3 (all merged)
Branch: `p2/insp-t14-demo`
Worktree: `/home/user/wt/insp/t14` (from `p2/ip-r3`)

## Goal
`just demo P2-INSP` runs clauses 1-7 of `docs/build-spec/module-designs/inspections.md` section 10 once on SQLite and once on Postgres (clause 8, the inspection's QR card, lives in the P2-QR demo), one `PASS clause N: ...` line each. **A PASS line is printed only after a real check returned success**; a miss prints `DEMO FAILED` and exits non-zero; no `echo PASS` on a path that checked nothing. Same method and helpers as `docs/tickets/P2-QR/T11-demo.md` and `dev/demos/P2-PUNCH.sh` (read the header comment of the .sh and one driver mode of each kind: API, TUI through the palette, MCP session). Clause verbs come from the merged CLI and these reports (the merged CLI wins; a difference is the first line of your report): `docs/reports/P2-IP/{INSPT05,INSPT06,INSPT07,INSPT08,INSPT10,INSPS3}.md`, `packages/tl-cli/tests/test_cli_insp.py`, `test_cli_checklist.py`.

## Clauses
Setup by commands: project `P123`; `sue` and `rob` quality superuser (`tl admin roles grant ... --module quality --role superuser`, as the P2-PUNCH demo line 123 does; rob so that his verify reaches the verifier rule); `uma` a plain user; `dora` the controller of correspondence (for the restricted record); one IWP made as `P2-I2.sh` makes it.
1. Checklist: `tl checklist create` (a questions file), `publish`; `edit` of the published one is refused (text from the S2 report); `revise` gives version 2 and the first becomes Retired (`tl checklist ls`).
2. Hold point: `tl insp plan` for the IWP (point hold), `schedule`, `record` with answers (one required question failed): result `reject`, one punch item category A exists and `tl punch ls` shows it linked; `verify` by the recorder is refused (S2 text), by `sue` passes.
3. Reinspect: `tl insp reinspect`, schedule, record all-pass: result `accept`; `show` names the first inspection.
4. Readiness (`tl awp readiness show <IWP> --project P123`, the line of `inspections_planned`): `n_a` before the plan; `blocked` Planned; `ok` once Scheduled; `blocked` after the reject; `ok` after the reinspection is scheduled.
5. Hidden subject: an inspection planned on a record restricted by `dora` (a correspondence item as P2-PUNCH clause 5) answers `uma` exactly as `tl insp show P123-INS-9999` does (byte for byte), `ls` lacks it and its total equals the data lines; the driver reads API (404, same text) and MCP (`get_inspection` error, same text, list lacks it) as `uma` and as an agent; `sue` sees it.
6. One state over CLI, API, TUI and MCP: `ApiClient.get_inspection` equals the fields `tl insp show` prints; the TUI at 170x44 reached by the palette id `inspections` (never `action_*`) shows the key and its state; MCP `list_inspections` and `get_inspection` agree; an agent's `propose_inspection` is pending and no new `tl insp ls` row appears until `uma` accepts it (as `p2_punch_demo.py` accepts a proposal); no tool named `record_*` or `verify_*` is in `MCP_ACTIONS`.
7. Export: `tl insp export --format csv` and `jsonl` have the same rows as `tl insp ls` (field by field).
The generator section of the demo project (INSP-T03) is checked on SQLite only as a tail clause 7b: `just demo-project <fresh db> --sections core,engineering,awp,constraints,quality` prints a `quality:` line without `skipped` and `tl insp ls` is non-empty (the P2-PUNCH clause 7 pattern; the Postgres run does not repeat it). Print it as `PASS clause 7b`.

## Context (read these, nothing else)
- `docs/build-spec/module-designs/inspections.md` section 10, `dev/demos/P2-PUNCH.sh`, `dev/demos/p2_punch_demo.py` (abridged), the reports listed above
may explore: `packages/tl-modules/quality/tests/insp_world.py`

## Allowed paths
- `dev/demos/P2-INSP.sh` (create, executable), `dev/demos/p2_insp_demo.py` (create), `docs/reports/P2-IP/INSPT14.md` (create)

## Acceptance
```
uv run ruff format --check dev/demos/p2_insp_demo.py
uv run ruff check dev/demos/p2_insp_demo.py
uv run pyright dev/demos/p2_insp_demo.py
just demo P2-INSP
```
Expected: clauses 1-7 on both backends plus 7b on SQLite, no `DEMO FAILED`, exit 0, no leftovers. Run once; Postgres down means `ge` and stop. No pytest, no `just gate`, no `just check`. The report names, per clause, the comparison that would fail if the feature broke.

## Escalation triggers
A clause cannot pass without a change in `packages/`, `schema/` or `dev/seed` (name it); a verb above differs from the merged CLI beyond a name; the demo needs more than the two files.

## Report requirements
`docs/reports/P2-IP/INSPT14.md` <= 60 lines: PASS lines per backend (<= 5 decisive lines), one line per clause naming its surface. Standard report (`docs/templates/haiku-report.md`), deviations first. Commit subjects `P2-INSP-T14: ...` with the trailers the dispatch message names; no model names.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
