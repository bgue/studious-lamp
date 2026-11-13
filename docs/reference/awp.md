# Reference — awp read surfaces: IWPs, constraints, readiness

Purpose: list every read of interim work packages (IWP), constraints and readiness, on each surface, with its
address or key. Commands and rules: `packages/tl-modules/awp/README.md`; procedures: `docs/runbooks/iwp-readiness.md`.

Examples use project `P123` and IWP `P123-IWP-PIP-0001`.

## Read surfaces

| Surface | IWP | Constraints | Readiness |
|---|---|---|---|
| CLI | `tl awp iwp ls`, `tl awp iwp show <number>`, `tl awp iwp scope <number>`, `tl awp iwp hash <number>` | `tl constraint ls`, `tl constraint show <key>`, `tl constraint groups` | `tl awp readiness ls`, `tl awp readiness show <number>` |
| CLI reports | `tl awp report iwp_status`, `tl awp report iwp_readiness` | `tl awp report constraint_log`, `constraints_by_category`, `constraints_by_owner`, `constraints_by_age` | `tl awp report iwp_readiness` |
| API (GET) | `/projects/{project}/awp/iwps` (`list_iwps`), `/projects/{project}/awp/iwps/{number}` (`get_iwp`), `/projects/{project}/awp/iwps/{number}/scope` (`list_iwp_scope`), `/projects/{project}/awp/iwps/counts` (`list_iwp_counts`), `/projects/{project}/awp/iwps/{number}/progress` (`get_iwp_progress`), `/projects/{project}/awp/iwps/{number}/hash` (`get_iwp_hash`), `/projects/{project}/awp/progress/rollup` (`get_progress_rollup`), `/projects/{project}/awp/kpis` (`list_kpis`), `/projects/{project}/awp/weeks` (`list_weekly_plans`), `/projects/{project}/awp/weeks/{week}` (`get_weekly_plan`), `/projects/{project}/awp/miss-reasons` (`list_miss_reasons`), `/projects/{project}/awp/look-ahead` (`get_awp_look_ahead`) | `/projects/{project}/constraints` (`list_constraints_api`), `/projects/{project}/constraints/groups` (`constraint_groups`), `/projects/{project}/constraints/{key}` (`get_constraint_api`) | `/projects/{project}/awp/iwps/{number}/readiness` (`get_iwp_readiness`) |
| TUI | IWP log (palette `iwps`); IWP screen (Enter on a row); weekly cycle (palette `week`, keys `1` to `5`) | constraint log (palette `constraints`); constraints of one IWP (`c` on the IWP screen) | readiness screen (`r` on the IWP screen) |
| Web | `/web/p/{project}/iwps` | `/web/p/{project}/constraints`, and `/web/p/{project}/constraints?subject=<subject key>` for one subject | `/web/p/{project}/readiness?number=<IWP number>` |
| MCP | `list_iwps`, `get_iwp`, `list_iwp_scope`; weekly and progress reads `list_weekly_plans`, `get_weekly_plan`, `get_iwp_progress`, `get_progress_rollup`, `list_kpis`; proposals `propose_progress`, `propose_week_commitment` (not writes) | none (the agent holds no `core.constraint.*` word, D37) | `get_iwp_readiness` |

Weekly cycle and rules of credit, CLI (P2-I5; every verb takes `--project P`): `tl awp look-ahead [--weeks N]`; `tl awp week open [--date D]`, `commit WEEK NUMBER --hours H [--foreman user:X] [--expected-version V]`, `outcome WEEK NUMBER done|missed [--reason KEY]`, `close WEEK`, `ls`, `show WEEK`, `ppc [--weeks N]`, `reasons`; `tl awp roc ls`, `roc show [--edition E]`, `roc set EDITION [--reason R]`; `tl awp iwp progress NUMBER`, `step NUMBER ITEM STEP [--undo]`, `item-move ITEM install|verify|return`, `start-work NUMBER [--date D]`, `complete-field NUMBER [--date D]`. Runbooks: `docs/runbooks/weekly-cycle.md`, `docs/runbooks/rules-of-credit.md`. Command routes: `POST /commands/<Name>` for `OpenWeeklyPlan`, `CommitIwpToWeek`, `RecordWeekOutcome`, `CloseWeek`, `RecordManualProgress`, `InstallScopeItem`, `ReturnScopeItem`, `VerifyScopeItem`, `StartIwpWork`, `CompleteIwpField` (bodies in `docs/reference/openapi.json`). Word of each: `packages/tl-modules/awp/README.md`, *Commands and access words*.

KPI tiles (weekly cycle, P2-I5-T09): `tl awp report kpi_ppc` (PPC over the last 4 closed weeks) and `tl awp report kpi_constraint_free` (share of live IWPs with no open blocking constraint), one row each.
Weekly-plan MCP reads (P2-I5-T11c, agent reads only): `list_weekly_plans`, `get_weekly_plan` (week `YYYY-Www`), `get_iwp_progress`, `get_progress_rollup`, `list_kpis`. Code: `tl_mcp/awp_week_tools.py`; each needs its `mcp.<tool>` action (`WEEK_MCP_ACTIONS`). The look-ahead is not on MCP this increment (D29).
Work pack: `tl awp iwp pack NUMBER [--out FILE] [--attach]` writes one printable HTML file of an IWP (QR codes need the `pack` extra); `--attach` stores it in the IWP's `pack` file slot. Code: `tl_mod_awp/pack.py`, `tl_cli/awp_pack.py`.

Export: `tl awp export progress --project P --period YYYY-Www [--out FILE]` prints earned progress by cost code as CSV
(`period,scope,cost_code,earned_hours,budget_hours,earned_pct,as_of_seq`; the `Unallocated` line last; an empty cell is no budget).
It is computed on read from the stored IWP progress, stores nothing and writes no event. Cells that start with
`=`, `+`, `-` or `@` get a leading apostrophe; `--out` writes mode 0600. A reader sees only what they can open (budgets
computed from that too); earned hours reaching no node are the `Unallocated` line. Code: `tl_mod_awp/progress/{rollup,export}.py`, `tl_cli/awp_export.py`.

The API routes are in `docs/reference/openapi.json`. The web routes are not in it (`packages/tl-web/README.md`).
The MCP tools are in `packages/tl-mcp/src/tl_mcp/iwp_tools.py`; each needs `mcp.<tool>` in the agent's identity.

## Access

Every read names its check per surface. A route's `Depends(guard(...))` is the API check; the web client runs the
same check as the route (`tl_web/reads.py`, `guard_action`).

| Surface | IWP reads (list, show, scope) | Readiness reads | Constraint reads (`ls`, `show`, `groups`) | Reports (`tl awp report`) |
|---|---|---|---|---|
| CLI | class filter; no access word checked (`tl_cli/awp_iwp_read.py`) | class filter; no access word checked (`tl_cli/awp_readiness_read.py`) | `core.constraint.view` (`tl_cli/constraint_read.py`) | class filter; no access word checked (README) |
| API | `document.read` (`tl_api/routes/awp.py:34`; routes at lines 238, 263, 274) | `document.read` (`routes/awp.py:314`) | `core.constraint.view` (`tl_api/routes/constraints.py:42`) | not checked in this page |
| TUI | not checked in this page | not checked in this page | not checked in this page | not applicable |
| Web | `document.read` (`tl_web/reads.py`, `_call`) | `document.read` (`tl_web/reads.py`, `_call`) | `core.constraint.view` (`tl_web/reads.py`, `_call_viewed`) | not applicable |
| MCP | `document.read` per tool through `guarded` (`tl_mcp/iwp_tools.py`; action per the awp README) | `get_iwp_readiness`, same | none (no constraint tools, D37) | not applicable |

A record the viewer may not see is absent from every list, and its page answers as a missing record. The default
viewer is the lowest clearance (ADR-0016).

## TUI keys

Palette ids are keyless entries in `packages/tl-tui/src/tl_tui/commands.py`, opened with `Ctrl+P`.

### IWP log (`iwps`)

| Key | Action |
|---|---|
| `/` | filter |
| `s` | next state, then all |
| `d` | next discipline, then all |
| `m` | only the IWPs whose foreman is you (again: all) |
| `r` | only the Ready IWPs (again: all) |
| `Enter` | open the IWP screen for the highlighted row |
| `F5` | reload |
| `Esc` | back |

### IWP screen (opened from the IWP log)

One IWP in full: identity, state, summary, scope, sign-offs, drawings and constraints. Text only.

| Key | Action |
|---|---|
| `r` | readiness screen for this IWP |
| `c` | constraint log for this IWP |
| `F5` | reload |
| `Esc` | close |

### Readiness screen (opened by `r` on the IWP screen)

| Key | Action |
|---|---|
| `Enter` | open the row's record |
| `F5` | reload |
| `Esc` | back |

### Constraint log (`constraints`)

| Key | Action |
|---|---|
| `/` | filter |
| `o` | group by owner (again: key order) |
| `t` | group by type (again: ungroup) |
| `a` | group by age band (again: ungroup) |
| `s` | next state, then all |
| `b` | blocking constraints only (again: all) |
| `F5` | reload |
| `Esc` | back |

The constraint log opened from the IWP screen (`c`) shows the same constraints, filtered to that IWP.

### Weekly cycle (`week`, P2-I5)

Five steps; keys `1` to `5` switch between them. Actions are keys on the highlighted row.

| Step | Key | Action |
|---|---|---|
| 1 Look-ahead | | read only |
| 2 Constraints | `x` | waive the highlighted check-raised constraint (asks for a reason) |
| 3 Release | `s` / `i` | sign off the highlighted Ready IWP / issue it to its foreman |
| 4 Commitments | `o` | open this week (when none is open; a screen key) |
| 4 Commitments | `c` / `d` / `m` / `z` | commit an IWP (IWP, hours, foreman) / record done / record missed (asks the reason) / close the week after a confirm |
| 5 Progress | `w` / `f` | start work on an Issued IWP / complete field work on an In progress IWP |

### Backlog (`backlog`)

| Key | Action |
|---|---|
| `b` | backlog view |
| `z` | sizing view |
| `F5` | reload |
| `Esc` | back |

## IWP reads

- `number`: the IWP number, `<project>-IWP-<discipline>-<sequence>`.
- List filters: `state`, `discipline`, `foreman` (CLI `tl awp iwp ls`; MCP `list_iwps` takes `state`, `discipline`, `foreman`).
- Detail: the IWP's crew, its scope by type, its pins, its open constraints and its sign-offs.
- `hash` returns the record hash, the value a sign-off or an issue carries (`record hash <sha256>`).

## Constraint reads

- `key`: the constraint key; `subject`: the record it sits on (the IWP number for an IWP).
- `tl constraint ls` filters: `--subject`, `--state`, `--category`, `--phase`, `--blocking` or `--advisory`, `--owner`.
  `tl constraint groups` groups the filtered list by `owner`, `category` or `age`.
- The total counts only the constraints the viewer may see.

## Readiness reads

- One evaluation per IWP: the last of the nine checks (`documents_current`, `rfis_answered`, `materials_reserved`,
  `constraints_cleared`, `permits_planned`, `inspections_planned`, `labour_requested`, `predecessors_handed_over`,
  `model_slice_available`).
- A check answers `ok`, `blocked`, `pending`, `n_a` or `unknown`. `ok` and `n_a` pass (D9).
- `readiness ls` lists each IWP with its last evaluation. Counts per IWP row on the IWP log are a follow-up (D33).
- The web readiness page takes `number` as a query value and shows that IWP's evaluation.

## Known limits

- A blocking constraint raised on an Issued IWP puts it On hold when `tl awp worker` runs (P2-I5; `readiness/hold_rule.py`).
- Agents hold no constraint word (D37).
- WBS constraint opt-in is deferred (`docs/build-spec/DEFERRED.md`).
