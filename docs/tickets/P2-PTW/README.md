# P2-PTW — Permit to work: permits, isolations, gas tests

Status: planning (r0 written by the orchestrator, 2026-11-15; nothing dispatched). 5 pieces, 16 tickets.
Sources: `docs/build-spec/module-designs/permits.md` (the design; its defaults are the decisions), brief §7.1 and §9
M3 (an IWP expects a permit; readiness "permits planned"), `docs/tickets/P2-I4B/` on branch `p2/i4b` (the newest
module built as its own package), P2-X4 S1 (hooks), ADR-0010, ADR-0016. Branch `p2/ptw` from the integration branch
`p2/ip`. Worktree `/home/user/wt/p2-ptw`. Piece branches `p2/ptw-s<n>-<slug>`, ticket branches
`p2/ptw-t<nn>-<slug>`, worktrees `/home/user/wt/ptw/<id>`. Board: `STATE.md` (round 1 writes it). Cross-increment
order: `docs/tickets/P2-QR/README.md`, last section.

## Objective
After this increment a new module `permits` (package `tl-mod-permits`) holds `permits.Permit`, `permits.Isolation`
and `permits.GasTest`. A foreman requests a permit of one of six types for a work package; a controller who is not
the requester approves; the permit authority issues it when the type's gas test, isolations and precautions are in
place; it is valid to the end of the shift and shows as Lapsed until revalidated; anyone can suspend it and only the
authority resumes; the holder hands it back and the authority closes it. Isolations are shared records that cannot be
removed under a live permit. The readiness check `permits_planned` answers for real. Reads and writes over CLI
(`tl permit`, `tl isolation`, `tl gastest`), API, client, terminal (register, record, board, isolation register) and
MCP reads plus `propose_permit`; CSV and JSONL exports; a status card for the QR scan page. Every surface is declared
through the ModuleSpec hooks from the module's own package. Out of scope: see the design §11.

## Demo
`dev/demos/P2-PTW.sh` (`just demo P2-PTW`, SQLite then Postgres): the eight clauses of the design §10. The clock is a
parameter of the lapse job and of the reads (as `today` is for the scaffold job); no clause sleeps.

## Checkpoints
C1: S1 merged to `p2/ip` (schema, words, settings, type table, projectors, module skeleton; APPROVALS). C2: S2, S3
merged (permit lifecycle; isolations and gas tests). C3: S4, S5 and every ticket merged or abandoned. C4: per-folder
gates, `gate-pg` on touched directories, demo on both adapters, tour shots, security review closed.

## Items
Tier B = builder piece (`kind: piece`); H = implementer ticket. Sec = a row for the wave's security review.

| ID | Title | Tier | Depends | Sec | Review |
|---|---|---|---|---|---|
| S1 | Schema and module skeleton: three classes, enums, events, two workflows, three numbering patterns, twelve words, nine settings, the type table fixture, projectors, `ModuleSpec`, pins (spec: `S1-schema-and-module.md`) | B | `p2/ip` | — | full |
| S2 | Permit lifecycle: the ten permit commands of the design §5 with guards (approver is not the requester, issue guards, validity to shift end, revalidate, suspend by any user, resume by the authority), pure `rules.py` (`shift_end`, `effective_state`, `issue_blockers`, `gas_result`; provided test), subject part in `confidentiality.py`, `PROPOSABLE` row `propose_permit`, exclusions, hooks declared; sentinel + ≤ 5 mutants | B | S1, P2-X4 C2 on trunk | yes | full |
| S3 | Isolations and gas tests: six commands (apply, verify by another person, remove with the dependency check and the "a permit you cannot see" text, link, unlink, record gas test with computed result and auto-suspend on a fail); sentinel + ≤ 5 mutants | B | S2 | yes | full |
| S4 | Readiness check `permits_planned` for real (design §6): `tl_mod_permits/checks.py`, entry point, the placeholder's entry-point line removed from the awp package, registry pin, contract test | B | S2, P2-INSP S3 merged (same awp file) | — | full |
| S5 | Job kind `permits.lapse`: flags each lapse once with `Permit.Lapsed`, clock as a parameter, reserved source, second run writes nothing | B | S2 | yes | full |
| T01 | Read views `views.py`: `permit_list`, `permit_detail`, `permit_counts`, `permit_board(area)`, `permits_for(record)`, `export_rows` | H | S2 | yes | full |
| T02 | Read views `iso_views.py`: `isolation_list`, `isolation_detail`, `gas_tests_for(permit)`, exports | H | S3 | yes | full |
| T03 | Generator: a `permits` section in the demo project (`dev/seed/demo_project/permits.py`), pins | H | S3 | — | full |
| T04 | CLI `tl permit` writes (request … cancel) through `cli_groups` | H | T01 | — | full |
| T05 | CLI `tl permit` reads (`ls`, `show`, `board`, `export`) | H | T01 | — | full |
| T06 | CLI `tl isolation` and `tl gastest` | H | T02 | — | full |
| T07 | API read router (seven GETs of the design §8) through `read_routers`; five-reader walk | H | T01, T02 | yes | full |
| T08 | MCP read tools and `propose_permit` through `tools`; closed until listed; walk | H | T01, T02 | yes | full |
| T09 | Scan card `permits.Permit` (`scan_card.py`, entry point) over the frozen card contract | H | T01, P2-QR C1 and QR T03 | yes | full |
| T10 | Client methods and fakes | H | T07 | — | full |
| T11 | Terminal: `permit_text.py`, permit register and record screen with actions | H | T10 | — | full |
| T12 | Terminal: permit board (`board_text.py`) | H | T10 | — | full |
| T13 | Terminal: isolation register and record (`isolation_text.py`) | H | T10 | — | full |
| T14 | Navigation and palette lines for the three screens (the shared one-line files) | H | T11, T12, T13 | — | lite |
| T15 | Demo `dev/demos/P2-PTW.sh` and driver | H | T03–T08, T14, S4, S5 | — | full |
| T16 | Tour shots (register, record, board, isolation register) and docs: module README and AGENTS, `docs/modules/permits/`, runbook `docs/runbooks/permits.md`, root `AGENTS.md` row | H | T15 | — | lite |

## Waves (implementer tickets in one wave have disjoint paths; gates name test files, never a whole package)
| Wave | Runs together | Notes |
|---|---|---|
| 1 | S1 | Alone on shared pins and generated files |
| 2 | S2 | The supervisor writes T01's provided test from S2's names while it builds |
| 3 | S3 ∥ T01 | S3 in `handlers/isolation*.py`, T01 in `views.py` |
| 4 | S4 ∥ S5 ∥ T02 ∥ T03 ∥ T04 ∥ T05 | Two small pieces and four tickets, six different files; gate runs two at a time |
| 5 | T06 ∥ T07 ∥ T08 ∥ T09 | CLI file, routes file, tools file, card file |
| 6 | T10, then T11 ∥ T12 ∥ T13 | Three new widget files and their text modules |
| 7 | T14, then T15, then T16 | |
Wave 4 holds six items but only two builders; with the supervisor round that is the three-slot cap, so the four
tickets go as one ticket workflow.

## APPROVALS lines needed before merge (the orchestrator never self-approves; the owner or a delegation does)
- S1 · schema merge `schema/modules/permits/**` (new module), two workflow fixtures, three numbering patterns,
  `schema/fixtures/permits/types.yaml`.
- S1 · settings: the nine `permits.*` keys (shift pattern, gas-test age, gas limits, `required_for_iwp`); twelve access
  words `permits.*`. The gas limits are safety values: the owner or the safety lead confirms the defaults.
- S2, S3 · security: `tl_core/confidentiality.py` subject part for `permits.Permit` and `permits.GasTest`;
  access-worded commands; separation of approver, issuer and verifier.
- S4 · core interface: readiness registry: `permits_planned` moves from `tl_mod_awp.checks_na` to the permits package.
- S5 · job kind and reserved source `job:permits.lapse`.

## Security rows (one review at C4, range `p2/ip` base..head)
S2 subject join; approver differs from requester; actor fields from the context, never an input; issue and resume run
the same guards; S3 verifier differs from applier; the removal refusal never names a hidden permit; gas result
computed server-side from settings; S5 the job writes only the flag event, once; T01 and T02 `viewer=` defaults to the
lowest clearance, filter before LIMIT and counts (the board's counts included); T07 and T08 walks and no agent write
beyond the proposal; T09 card answers `None` for a hidden record.

## Risks and escalation triggers
- First module built wholly on the hooks: S2 follows `docs/runbooks/new-module.md` (P2-X4 T04) and the `ext_demo`
  fixture (X4 T03). If X4 C2 is not on the trunk, S2 waits; S1 can still be built and merged.
- S1 and P2-I4B S1 both add a module to the same pinned lists; the second to merge regenerates and re-adds its counts.
- S4 and P2-INSP S3 edit neighbouring lines of `packages/tl-modules/awp/pyproject.toml`: S4 merges after INSP S3.
- T11 to T13 are implementer tickets only because their logic is in Textual-free text modules first (L-P2-WEB1-1).
- Gas limits and shift rules differ by site and by law. They are settings with conservative defaults; a refusal text
  names the setting. No ticket hard-codes a limit.
- Escalate: a frozen contract must change; a word the table lacks; a piece failing twice; a guard that would need to
  read another module's tables directly (scaffold tag: use that module's `api` after P2-I4B, as a later piece).

## Plan check
Pending (`4 PLANCHK docs/tickets/P2-PTW/README.md`): over 10 items. S1 may be built while it runs; no merge and no
ticket dispatch before each finding is answered here.

## Blocked / Decision
(none yet)
