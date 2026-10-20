# P1-I8-S9 — Conformance dashboard: `conformance_dashboard()` and `tl schema conformance` (was T05b)

Status: ready
Tier: sonnet
Kind: piece
Review: full
Labels: schema-registry, cli, read-view
Depends on: P1-I8-S2, S5, T05a1, T05a2 and T05a3's stub wiring on `p1/i8` (waiver and drift views exist)
Branch: `p1/i8-s9-conformance-dashboard`
Builder worktree: `/home/user/wt/p1-i8-s9-conformance-dashboard`

## Goal
One read that tells a data manager how a project's records stand against the schema in force: for each record type how many records are `ok`, `warning`, `nonconformant`, and how many were checked against an older schema than the one in force now (stale); the approved waivers of the project with the days they have left; and the company packages the project is behind on. It is a read function in the schemareg module and one CLI command. It is a piece because it reads `cur_core_record` and must count as the viewer (ADR-0016): a count that includes a record the reader may not see tells them it exists.

## Brief references (pasted)
> **Brief 27.3 and 27.5.** Every record stores the hash of the effective schema it was last checked against and its conformance (`ok`, `warning`, `nonconformant`). A schema change makes records stale until they are written again or re-evaluated; a waiver relaxes one property until a date. *"A conformance dashboard by project and type: counts by status, waivers with expiry, drift against the company."*
> **Increment 8 decisions.** D5: waivers reach the evaluator through the effective schema; an approved waiver whose day has passed no longer relaxes anything and shows as expired. D10-style rule for any count: it is taken as the current viewer, a hidden record answers as one that never existed.
> **AGENTS.md.** Never read a module record, its history or the events that name it without the viewer's class filter (`tl_core.confidentiality`); the viewer defaults to the lowest clearance.

## Interfaces
New, in `packages/tl-modules/schemareg/src/tl_mod_schemareg/dashboard.py` (frozen pydantic models, same style as `views.py`):

```python
class TypeConformance(BaseModel):   # frozen
    type: str
    total: int
    ok: int
    warning: int
    nonconformant: int
    stale: int          # records whose effective_schema_hash is not the hash in force (NULL counts as stale)

class WaiverLeft(BaseModel):        # frozen
    key: str            # as WaiverView.key
    path: str
    expires: str
    days_left: int      # expires - today, never negative; expired waivers are not listed here

class ConformanceView(BaseModel):   # frozen
    project: str
    schema_hash: str    # EffectiveSchema.hash of scope project:<id>
    total: int
    by_type: list[TypeConformance]  # sorted by type
    waivers: list[WaiverLeft]       # state Approved and not expired, by expires then key
    expired_waivers: int            # approved and past their day
    drift: list[views.DriftView]    # only those with behind=True, by package

def conformance_dashboard(conn: Connection, project: str) -> ConformanceView: ...
```
Existing, read-only: `views.waiver_views(conn, project, state)`, `views.drift_views(project)`, `analysis.provider().effective(scope)` (scope is `f"project:{project}"`), `confidentiality.not_hidden("id") -> (clause, params)` as used in `views.sample_test`, the table `cur_core_record` (`id, type, scope, voided, conformance, effective_schema_hash`).

CLI, new file `packages/tl-cli/src/tl_cli/schema_conf.py`, registered in `tl_cli/schema.py` as `tl schema conformance --project P [--json]` (`--project` required; needs a signed-in person, `require_session`; read-only unit of work in `service_errors()`; `--json` prints `model_dump_json(indent=2)` and nothing else). Text output, fields separated by two spaces:
```
P123  schema <first 12 of hash>  records 40
<type>  total 12  ok 9  warning 2  nonconformant 1  stale 3        (one line per type)
waiver <key>  until <expires>  <n> days left                        (one line per live waiver)
expired waivers 1                                                   (only when > 0)
behind <package>  <project_version> < <company_version>             (one line per drifting package)
```
With no records: `P123  schema <12>  records 0` and nothing else under it.

## Context (read these, nothing else)
- `packages/tl-modules/schemareg/src/tl_mod_schemareg/views.py` (style, `sample_test`, `waiver_views`, `drift_views`)
- `packages/tl-modules/schemareg/src/tl_mod_schemareg/testing.py` (`RegistryWorld`, `make_record`)
- `packages/tl-modules/schemareg/tests/test_views.py` (how the module tests read views)
- `packages/tl-cli/src/tl_cli/schema_gov.py` (CLI style) and `packages/tl-cli/tests/test_cli_schema_gov.py`
- `packages/tl-core/src/tl_core/confidentiality.py` (`not_hidden`, `use_viewer`, `LOWEST`)

## Allowed paths
- `packages/tl-modules/schemareg/src/tl_mod_schemareg/dashboard.py` (create)
- `packages/tl-modules/schemareg/tests/test_dashboard.py` (create)
- `packages/tl-cli/src/tl_cli/schema_conf.py` (create), `packages/tl-cli/src/tl_cli/schema.py` (two lines: import and `register`)
- `packages/tl-cli/tests/test_cli_schema_conformance.py` (create)
- `packages/tl-modules/schemareg/README.md`, `docs/modules/schemareg/README.md` (one paragraph each on the dashboard)
- `docs/reports/P1-I8/P1-I8-S9.md` (create)
Not allowed: `schema/**`, `tl_core/**`, the evaluator, any existing view.

## Steps
1. Tests first: module tests on both adapters with `RegistryWorld`; CLI tests with the helpers of `test_cli_schema_gov.py`.
2. `dashboard.py`: one SQL `GROUP BY type, conformance` and one count of stale rows per type, over `cur_core_record WHERE NOT voided AND scope = :scope AND <not_hidden clause>`; no row-by-row evaluation (the stored `conformance` is read, not recomputed).
3. The CLI command and its two wiring lines. READMEs.
4. `just check`, then `just gate packages/tl-modules/schemareg packages/tl-cli/tests/test_cli_schema_conformance.py | tee .gate/summary.txt` (no `gate-pg` needed: no adapter code; run the module tests with `--adapters sqlite,postgres` once).

## Acceptance
Tests the builder writes must cover, at least:
- counts by type and status on a project with records of two types in each status; `total` equals the sum; types sorted;
- stale: a record checked against an older hash and a record whose hash is NULL are stale, one at the current hash is not; adopting a package version (or approving a waiver) changes the hash in force and makes the others stale;
- waivers: an approved one shows `days_left`; a requested or revoked one is absent; an approved one past its day is counted in `expired_waivers` and not listed; `days_left` is 0 on the last day;
- drift: only `behind=True` packages;
- **confidentiality walking test**: with one restricted record per status, the lowest viewer's counts do not include it (and the same view for a viewer of level 1 does); a restricted-only type does not appear for the lowest viewer;
- voided records and records of another project are never counted;
- CLI: exact text above, `--json` parses and equals the view, no signed-in person is refused as the other schema commands do, missing `--project` is a usage error.

## Mutation (builder runs it, reports 3 lines)
Sentinel: any one mutant the tests must kill (for example swap `ok` and `warning` in the sum). Targeted, at most 5: drop the `not_hidden` clause; drop `NOT voided`; stale compare `==` for `!=`; `<` for `<=` in the expiry; count NULL hash as not stale.

## Report requirements
`docs/reports/P1-I8/P1-I8-S9.md` (≤ 60 lines): deviations first, decisions, the output of the three commands above (≤ 5 lines each), mutation result, open questions. Return ≤ 15 lines in TL92.

## Escalation triggers
- The stored `conformance` or `effective_schema_hash` of a record is not what the text above says: stop, write *Blocked*.
- The view would need a change in `tl_core`: stop.
- A count cannot be taken as the viewer without a change to `confidentiality.py`: stop.

## Blocked
(builder writes here)

## Decision
(supervisor or orchestrator writes here)
