# P2-PTW — Permit to work: permits, isolations, gas tests

Status: plan check answered (r1b, 2026-11-15; nothing dispatched). 5 pieces, 17 tickets (T00 added): 12 in the first
slice, 5 in the follow-up slice. **today** marks today's slice (S1 and T00).
Sources: `docs/build-spec/module-designs/permits.md` (the design; its defaults are the decisions), brief §7.1 and §9
M3 (an IWP expects a permit; readiness "permits planned"), `docs/tickets/P2-I4B/` on branch `p2/i4b` (the newest
module built as its own package), P2-X4 S1 (hooks), ADR-0010, ADR-0016. Branch `p2/ptw` from the integration branch
`p2/ip`. Worktree `/home/user/wt/p2-ptw`. Piece branches `p2/ptw-s<n>-<slug>`, ticket branches
`p2/ptw-t<nn>-<slug>`, worktrees `/home/user/wt/ptw/<id>`. Board: `STATE.md` (round 1 writes it). Cross-increment
order: `docs/tickets/P2-QR/README.md`, last section.

S2 (r2, P2-IP): spec `S2-permit-lifecycle.md` with `../P2-IP/S2-common.md`; S2 declares its module hooks (X4 is complete on `p2/x4`), which supersedes every "no hook fields" line below; the S2 branch needs `p2/ip` merged with `p2/x4` and waits for X4 on trunk to merge.

## Objective
After this increment a new module `permits` (package `tl-mod-permits`) holds `permits.Permit`, `permits.Isolation`
and `permits.GasTest`. A foreman requests a permit of one of six types for a work package; a controller who is not
the requester approves; the permit authority issues it when the type's gas test, isolations and precautions are in
place; it is valid to the end of the shift and shows as Lapsed until revalidated; anyone can suspend it and only the
authority resumes; the holder hands it back and the authority closes it. Isolations are shared records that cannot be
removed under a live permit. The readiness check `permits_planned` answers for real. Reads and writes over CLI
(`tl permit`, `tl isolation`, `tl gastest`), API, client, terminal (register, record, board, isolation register) and
MCP reads plus `propose_permit`; CSV and JSONL exports; a status card for the QR scan page. The surfaces live in the
module's own package; the ModuleSpec hook declaration follows after P2-X4 C2 (see risks). Out of scope: see the design §11.

## Demo
`dev/demos/P2-PTW.sh` (`just demo P2-PTW`, SQLite then Postgres): the eight clauses of the design §10. The clock is a
parameter of the lapse job and of the reads (as `today` is for the scaffold job); no clause sleeps.

## Checkpoints
C1: S1 merged to `p2/ip` (schema, words, settings, type table, projectors, module skeleton; APPROVALS). C2: S2, S3
merged (permit lifecycle; isolations and gas tests; no hook fields yet). C3: S4, S5 and every ticket merged or abandoned. C4: per-folder
gates, `gate-pg` on touched directories, demo on both adapters, tour shots, security review closed.

## Items (first slice)
Tier B = builder piece (`kind: piece`); H = implementer ticket. Sec = a row for the wave's security review.
Module-package surfaces (T04 to T08 routes, CLI and tools) need `fastapi`, `typer`, `mcp`: the S2 builder adds the
dependencies and stub registrars and checks there is no `tl-api` to `tl-mod-permits` cycle.

| ID | Title | Tier | Depends | Sec | Review | Slice |
|---|---|---|---|---|---|---|
| S1 | Schema and module skeleton: three classes, enums, events, two workflows, three numbering patterns, twelve words, nine settings, the type table fixture, projectors, `ModuleSpec`, pins (spec: `S1-schema-and-module.md`) | B | `p2/ip` | - | full | today |
| T00 | Pure `tl_mod_permits/rules.py` (`shift_end`, `effective_state`, `gas_result`, `issue_blockers`); ticket `T00-ptw-rules.md`, provided test | H | S1 | yes | full | today |
| S2 | Permit lifecycle as services and handlers with no hook fields: the ten permit commands of the design §5 with guards (approver is not the requester, issue guards via `issue_blockers`, validity to shift end, revalidate, suspend by any user, resume by the authority), subject part in `confidentiality.py`, `PROPOSABLE` row `propose_permit`, exclusions, error types that raise core error classes, deps and stub registrars, the provided test of T01; sentinel + at most 5 mutants | B | S1, T00 | yes | full | later |
| S3 | Isolations and gas tests: six commands (apply, verify by another person, remove with the dependency check and the "a permit you cannot see" text, link, unlink, record gas test with computed result via `gas_result` and auto-suspend on a fail); sentinel + at most 5 mutants | B | S2 | yes | full | later |
| S4 | Readiness check `permits_planned` for real (design §6), a `t` with full review inside a workflow: `tl_mod_permits/checks.py`, entry point, the placeholder's entry-point line removed from the awp package, registry pin, contract test; paths include `dev/accept/P2-I2/T06b.py` | t | S2, INSP S3 merged (same awp file) | - | full | later |
| S5 | Job kind `permits.lapse`: flags each lapse once with `Permit.Lapsed`, clock as a parameter, reserved source, second run writes nothing | B | S2 | yes | full | later |
| T01 | Read views `views.py`: `permit_list`, `permit_detail`, `permit_counts`, `permit_board(area)`, `permits_for(record)`, `export_rows` | H | S2 | yes | full | later |
| T02 | Read views `iso_views.py`: `isolation_list`, `isolation_detail`, `gas_tests_for(permit)`, exports | H | S3 | yes | full | later |
| T03 | Generator: a `permits` section in the demo project (`dev/seed/demo_project/permits.py`), pins | H | S3 | - | full | later |
| T04 | CLI `tl permit` writes (request ... cancel) in the module package | H | T01 | - | full | later |
| T05 | CLI `tl permit` reads (`ls`, `show`, `board`, `export`) | H | T01 | - | full | later |
| T06 | CLI `tl isolation` and `tl gastest` | H | T02 | - | full | later |
| T07 | API read router (seven GETs of the design §8) in the module package; five-reader walk | H | T01, T02 | yes | full | later |
| T08 | MCP read tools and `propose_permit` in the module package; closed until listed; walk | H | T01, T02 | yes | full | later |
| T09 | Scan card `permits.Permit` (`scan_card.py`, entry point) over the frozen card contract | H | T01, QR C1 and QR T03 | yes | full | later |
| T10 | Client methods and fakes | H | T07 | - | full | later |
| T11 | Terminal: `permit_text.py`, permit register and record screen with actions | H | T10 | - | full | later |
| T15 | Demo `dev/demos/P2-PTW.sh` and driver | H | T03-T08, T11, S4, S5 | - | full | later |
| T16 | Tour shots (register, record) and docs: module README and AGENTS, `docs/modules/permits/`, runbook `docs/runbooks/permits.md`, root `AGENTS.md` row | H | T15 | - | lite | later |

### Follow-up slice (not scheduled; each waits for the first slice to merge and for a fresh plan round)
| ID | Title | Why it waits |
|---|---|---|
| T12 | Terminal: permit board (`board_text.py`) | The board is readable over CLI (`tl permit board`) first |
| T13 | Terminal: isolation register and record (`isolation_text.py`) | Isolations are readable over CLI, API and MCP first |
| T14 | Navigation and palette lines for the screens | Nav work waits for the screens |
| - | Hook declaration of the module (`commands`, `read_routers`, `cli_groups`, `tools`) | Needs P2-X4 C2 in `p2/ip` |

## Waves (workflows of at most 3 items; gates name test files, never a whole package)
| Wave | Runs together | Notes |
|---|---|---|
| 1 | S1 (starts when QR S1 or INSP S1 ends: at most 2 heavy runs), then T00 | **today**; T00 as a ticket in a workflow with the other today tickets |
| 2 | S2 | Writes the provided test of T01 under `provided/` while it builds (F8) |
| 3 | S3 and workflow {T01} | S3 in `handlers/isolation*.py`, T01 in `views.py` |
| 4 | S5 (builder) and workflow {S4 as `t`, T02, T03} | S4 needs INSP S3 merged |
| 5 | workflow {T04, T05, T06}, then {T07, T08, T09} | CLI files, routes file, tools file, card file |
| 6 | T10, then T11 | |
| 7 | T15, then T16 | |
At most two heavy test runs on the box at once.

## APPROVALS lines needed before merge (the orchestrator never self-approves; the owner or a delegation does)
Approvers: the owner for the schema merge, security lines and core interfaces; the safety lead for the gas limits.
- S1 - schema merge `schema/modules/permits/**` (new module), two workflow fixtures, three numbering patterns,
  `schema/fixtures/permits/types.yaml` (owner).
- S1 - settings: the nine `permits.*` keys (owner); twelve access words `permits.*` (owner). The gas limits are
  safety values: the safety lead signs them, and the default values stand until signed.
- S2, S3 - security: `tl_core/confidentiality.py` subject part for `permits.Permit` and `permits.GasTest`;
  access-worded commands; separation of approver, issuer and verifier (owner).
- S4 - core interface: readiness registry: `permits_planned` moves from `tl_mod_awp.checks_na` to the permits package.
- S5 - job kind and reserved source `job:permits.lapse`.

## Security rows (one wave review over `d4e92ffc..<p2/ip head>` with the union of the Sec rows of the three increments)
T00 the pure rules (fail-closed Lapsed, newest gas test decides, limits inclusive and caller-supplied); S2 subject
join; approver differs from requester; actor fields from the context, never an input; issue and resume run the same
guards; S3 verifier differs from applier; the removal refusal never names a hidden permit; gas result computed
server-side from settings; S5 the job writes only the flag event, once; T01 and T02 `viewer=` defaults to the lowest
clearance, filter before LIMIT and counts (the board's counts included); T07 and T08 walks and no agent write beyond
the proposal; T09 card answers `None` for a hidden record.

## Risks and escalation triggers
- First module built wholly in its own package: S2 follows `docs/runbooks/new-module.md` (P2-X4 T04) and the `ext_demo`
  fixture (X4 T03) as far as they exist; without X4 C2 it declares no hook fields (F2) and the hook declaration is a
  later small ticket. Module error types raise core error classes (errors hook DEFERRED).
- S1 and P2-I4B S1 both add a module to the same pinned lists; the second to merge regenerates and re-adds its counts.
- S4 and INSP S3 edit neighbouring lines of `packages/tl-modules/awp/pyproject.toml`: S4 merges after INSP S3.
- T11 is an implementer ticket only because its logic is in a Textual-free text module first (L-P2-WEB1-1).
- Gas limits and shift rules differ by site and by law. They are settings with conservative defaults; a refusal text
  names the setting. No ticket hard-codes a limit (T00 takes them as arguments).
- Escalate: a frozen contract must change; a word the table lacks; a piece failing twice; a guard that would need to
  read another module's tables directly (scaffold tag: use that module's `api` after P2-I4B, as a later piece); a
  `tl-api` to `tl-mod-permits` dependency cycle.
- Fan-out rules (merge order, shared files, heavy runs, today's slice): P2-QR README, last section.

## Blocked / Decision
(none yet)

## Plan check
Answered 2026-11-15 (r1b); the orchestrator accepted every finding.
| F | Sev | Finding | Answer here |
|---|---|---|---|
| F1 | HI | QR URL under `/web` | QR only; the permit card's `open_path` starts with `/web/` |
| F2 | HI | Hooks need X4 C2 | S2 has no hook fields; hook declaration later; errors hook DEFERRED |
| F3 | HI | At most 2 heavy runs | PTW S1 starts after QR S1 or INSP S1 finishes |
| F4 | HI | Shared files beyond the pins | Owner rule extended (QR README fan-out); PTW appends its lines last |
| F5 | MD | S1 merge order | First signed S1 merges first; later ones merge `p2/ip`, `just gen`, re-pin |
| F6 | MD | Module-package surfaces need deps | S2 adds `fastapi`, `typer`, `mcp` and stub registrars, checks the cycle |
| F7 | MD | Pure rules out of S2; tiers | `rules.py` is T00 (Haiku, full, provided test); S4 is a `t` with full review |
| F8 | MD | Provided tests | S2 builder writes T01's provided test under `provided/`; T00's test exists now |
| F9 | MD | Scope | T12, T13 and the nav work (T14) moved to the follow-up slice |
| F10 | MD | Workflows of 3 | Waves above; S4 as a `t` inside a workflow |
| F11 | MD | Today's slice | S1 and T00 |
| F12 | MD | QR label rule and rate limit | QR only |
| F13 | LO | Approvers | Owner for schema, security, interfaces; safety lead for gas limits (defaults stand until signed); one wave security review |
| F14 | LO | Demo clauses; T06b | QR demo clause 8 covers the permit card; `dev/accept/P2-I2/T06b.py` added to S4's paths |
