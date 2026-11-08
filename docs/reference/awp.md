# Reference — awp read surfaces: IWPs, constraints, readiness

Purpose: list every read of interim work packages (IWP), constraints and readiness, on each surface, with its
address or key. Commands and rules: `packages/tl-modules/awp/README.md`; procedures: `docs/runbooks/iwp-readiness.md`.

Examples use project `P123` and IWP `P123-IWP-PIP-0001`.

## Read surfaces

| Surface | IWP | Constraints | Readiness |
|---|---|---|---|
| CLI | `tl awp iwp ls`, `tl awp iwp show <number>`, `tl awp iwp scope <number>`, `tl awp iwp hash <number>` | `tl constraint ls`, `tl constraint show <key>`, `tl constraint groups` | `tl awp readiness ls`, `tl awp readiness show <number>` |
| CLI reports | `tl awp report iwp_status`, `tl awp report iwp_readiness` | `tl awp report constraint_log`, `constraints_by_category`, `constraints_by_owner`, `constraints_by_age` | `tl awp report iwp_readiness` |
| API (GET) | `/projects/{project}/awp/iwps` (`list_iwps`), `/projects/{project}/awp/iwps/{number}` (`get_iwp`), `/projects/{project}/awp/iwps/{number}/scope` (`list_iwp_scope`) | `/projects/{project}/constraints` (`list_constraints_api`), `/projects/{project}/constraints/groups` (`constraint_groups`), `/projects/{project}/constraints/{key}` (`get_constraint_api`) | `/projects/{project}/awp/iwps/{number}/readiness` (`get_iwp_readiness`) |
| TUI | IWP log (palette `iwps`); IWP screen (Enter on a row) | constraint log (palette `constraints`); constraints of one IWP (`c` on the IWP screen) | readiness screen (`r` on the IWP screen) |
| Web | `/web/p/{project}/iwps` | `/web/p/{project}/constraints`, and `/web/p/{project}/constraints?subject=<subject key>` for one subject | `/web/p/{project}/readiness?number=<IWP number>` |
| MCP | `list_iwps`, `get_iwp`, `list_iwp_scope` | none (the agent holds no `core.constraint.*` word, D37) | `get_iwp_readiness` |

The API routes are in `docs/reference/openapi.json`. The web routes are not in it (`packages/tl-web/README.md`).
The MCP tools are in `packages/tl-mcp/src/tl_mcp/iwp_tools.py`; each needs `mcp.<tool>` in the agent's identity.

## Access

| Read | Access |
|---|---|
| IWP reads (CLI, API, TUI, web, MCP) | the module's class filter applies; the CLI checks no access word |
| Readiness reads (CLI) | the class filter applies; the CLI checks no access word (API and web: not checked in this page; see the sources) |
| `tl awp report` (IWP and constraint names) | the class filter applies; no access word is checked by the CLI |
| Constraint reads (CLI `tl constraint ls|show|groups`, web constraint log) | `core.constraint.view` |

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

- A new blocking constraint on an Issued IWP does not put it On hold (Q1, `docs/tickets/P2-I2/STATE.md`).
- Agents hold no constraint word (D37).
- WBS constraint opt-in is deferred (`docs/build-spec/DEFERRED.md`).
