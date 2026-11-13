# P2-PUNCH — Punch list (module M5, minimal slice), brought forward

Status: r1, plan written; nothing dispatched. 2 pieces, 9 tickets, about 4 weekly points (roadmap row 4a: 3-4). Sources:
`docs/build-spec/roadmap-2026-11-07.md` (row 4a, "Punch list brought forward: cost"), `docs/build-spec/09-phase3-plan.md`
Increment 2 (`Deficiency`, `kind` punch), `module-designs/quality.md`, ADR-0010 (module records), ADR-0016 (confidentiality),
ADR-0024 (constraints on any record), ADR-0027 (agent-first layer). Board: `STATE.md`. Branch `p2/punch` from the trunk @bb6f855b.
Worktree `/home/user/wt/p2-punch`. Shape copied from `docs/tickets/P2-I4A/` (branch `p2/i4a`).

## Objective
After this increment a new module `quality` (package `tl-mod-quality`, `packages/tl-modules/quality`, `schema/modules/quality`)
holds one record type, `quality.PunchItem`, numbered `P123-PUN-0001`. A person raises a punch item (optionally from any record: an
IWP, a document, an RFI, a tag), gives it an area, a system, a due date, a category (A, B, C) and an assignee; the assignee
clears it with a note; a controller verifies it (never the person who cleared it); a controller can reopen a cleared or verified
item with a reason or void an open or cleared one. Reads over CLI (`tl punch`), API, client, TUI (punch log and record screen) and
MCP (`list_punch_items`, `get_punch_item`, `propose_punch_item`). The generator's `quality` section is switched on.
Out of scope (each a `DEFERRED.md` line, STATE): web pages; the walkdown fast-entry screen and the `d` key; photos; thread
target `/raise punch`; feed cards; inspections, deficiencies, ITPs and the Issue engine (Phase 3); a certificate or test-package
check that reads punch A (Phase 3/4); systems and subsystems as records (Phase 4: `system` and `area` are text here).

## Record shape and Phase 3 compatibility
`quality.PunchItem` (table `cur_quality_punch_item`; title is the subject, envelope description is the detail):
`area`, `system` (text <= 64, indexed), `due_on`, `category` (A, B, C; default B), `assignee` (actor or text <= 120), `raised_by`,
`source_id` (the record it was raised from, null ok, indexed; the confidentiality subject), `cleared_by`, `cleared_on`,
`clear_note`, `verified_by`, `verified_on`, `reopen_count`, `last_reopen_reason`, `void_reason`. A `raised_against` link runs from
the item to its source (the relation Phase 3 uses for `Issue` and `Deficiency`).
How Phase 3 takes it over (roadmap: rework under one point). The Phase 3 Issue engine adds `kind` (`punch`), `response_cycle` and
`escalation_level` as additive columns on the same table and registers `punch` as a kind whose numbering pattern is the existing `PUN`.
Nothing here is renamed:
| Here | Phase 3 (`09-phase3-plan.md` I1/I2, `quality.md`) |
|---|---|
| states `Open`, `Cleared`, `Verified`, `Void` | Deficiency `Open`/`Cleared`; Issue `Verified`; `Void` is the Deficiency's `Cancelled`. Same words, no migration; `Assigned` and `Fixed` stay fields, not states (an assignment is an event, as `Issue.Assigned` is) |
| `assignee`, `due_on`, `source_id` + `raised_against` link | Issue `owner`, `due_on`, `raised_against` links |
| `category` A/B/C | Deficiency `category` (Phase 4 "punch A closed" checks) |
| events `PunchItem.Raised/Edited/Cleared/Verified/Reopened/Voided` | `Issue.Raised/Assigned/Dispositioned/Reopened/Closed`: the Issue engine emits its own events beside these; a rule or projector maps by record type |
| `quality.punch.*` access words | the Issue engine's words; the punch words stay |
| `area`, `system` text | Phase 4 links to `System` and `Subsystem` records; the text stays as the display code |
The module is `quality`, so Phase 3 adds its classes to the same schema directory and the same `ModuleSpec`.

## Owner questions applied (defaults, no wave blocked)
- Who verifies: the module superuser (word `controller`), and never the person who cleared the item (fixed message). Reopen and void are controller acts too. A project can move a word later (Phase 3).
- A verified item can be reopened (controller, with a reason); `Void` is the only terminal state.
- Category is A, B or C, default B; A means it blocks a later completion step (Phase 4 reads it).

## Demo clauses (`dev/demos/P2-PUNCH.sh`, SQLite then Postgres; `just demo P2-PUNCH`; clause 7 is SQLite only)
A `PASS clause N: ...` line is printed only after a real check returned success. Project `P123`; `uma` a plain user,
`rob` and `sue` hold the module superuser role on `quality` (rob so that his verify meets the clearer rule, not `forbidden`), `dora` is the document controller. Each verb below has its owning ticket.
| # | Clause and exact verbs | Owners |
|---|---|---|
| 1 | Raise to verify. `tl punch raise --subject S --area A1 --system 47-01 --due D --category A --assignee user:rob --from <IWPNUMBER>` as uma prints `raised P123-PUN-0001  version <v>`; `tl punch ls --state Open` lists it; `tl punch clear P123-PUN-0001 --note N` as rob prints `cleared ...`; `tl punch verify P123-PUN-0001` as rob is refused (fixed message), as uma `error: forbidden`, as sue prints `verified ...`; `tl punch show P123-PUN-0001` prints `state  Verified`, who cleared and who verified | T02 verbs; S1 words; S2 rules |
| 2 | Reopen, void, terminal. `tl punch clear` then `tl punch reopen P123-PUN-0002 --reason R` as sue returns it to `Open` with `reopened  1`; `tl punch void P123-PUN-0003 --reason R`; `clear` on the void item is refused with the fixed message; `reopen` without `--reason` exits 2; a stale `--expected-version` is refused | T02, S2 |
| 3 | Raised from any record. Items raised `--from` an IWP number, a tag number and a document number print `raised from <key>`; `tl punch ls --from <key>` lists only that record's items; `--from` an unknown key prints `error: no record <key>` and writes nothing; `tl link list` (the `raised_against` link) names the source | T02, T01, S2 |
| 4 | Numbering. Two background loops of ten `tl punch raise` give 20 distinct keys, `-0001..-0020` with no gap (counted by the script) | S1 pattern, S2 allocation, T08 |
| 5 | Hidden source. Dora receives a correspondence item (`tl corr receive`), sets it restricted (`tl corr class set <NUMBER> --to restricted --reason R`) and raises `tl punch raise --from <NUMBER>`; uma gets `error: no punch item <key>` from `tl punch show`, the same text as a key that never existed, no row in `tl punch ls`, `total` unchanged, API 404 and MCP error with the same text; sue and dora see it | S2 join, T01, T02, T03, T05 |
| 6 | One state over API, TUI, MCP. `ApiClient.get_punch_item` equals `tl punch show`; the TUI reached by palette id `punch` at 170x44 shows the key and state; MCP `list_punch_items` agrees; an agent's `propose_punch_item` is pending and no `tl punch ls` row appears until uma accepts, then the next key exists with `raised by  user:uma`; no MCP tool clears or verifies (`mcp.clear_punch_item` is not in `MCP_ACTIONS`); a person without `quality.view` is refused by CLI, API (403) and MCP | T02, T03, T04, T05, T06 |
| 7 | Generator. `just demo-project <db> --sections core,engineering,awp,constraints,quality` prints a `quality: <n> records, <m> events` line (not `quality: skipped`), and `tl punch ls` on that ledger shows at least one item in each of `Open`, `Cleared`, `Verified`, `Void`, one overdue (`--overdue`), one reopened (`reopened` count 1 in `show`), items raised from IWPs and tags, and every item raised from a record that exists | T07 |
Hidden-source (clause 5) is possible by commands because a restricted correspondence item exists; no projection write is used anywhere.

## Pieces (builder, `kind: piece`, review full)
| Id | Piece | Spec | Depends | Gate |
|---|---|---|---|---|
| S1 | Schema and module spec: `schema/modules/quality/` (`module.yaml`, `punch_item.yaml`, `events.yaml`), workflow, numbering pattern, seven access words, offline class, valid-time tags, package skeleton and `ModuleSpec`, consumer dependency lines, pins, tests | `S1-schema-and-module.md` | trunk | human (schema): orchestrator APPROVALS line |
| S2 | Commands and engine: six commands with guards, `actions.py`, `api.py` (`open_punch_for`), `punch_world.py` helper, subject join in `confidentiality.py`, `PROPOSABLE` row `propose_punch_item`, exclusions, intent round-trip, tests, sentinel + <= 5 mutants | `S2-commands-and-engine.md` | S1 | human (access words, confidentiality): orchestrator APPROVALS line |

## Tickets (Haiku; tests ride in each ticket; the provided test of T01 is committed by the supervisor after S2 merges, state by commands only)
| Id | Title | Rev | Depends | Pins it updates |
|---|---|---|---|---|
| T01 | Read views `punch_list`, `punch_detail`, `punch_counts` | full | S2 | none expected |
| T02 | CLI group `tl punch`: raise, edit, clear, verify, reopen, void, ls, show | full | T01 | CLI group list, if pinned |
| T03 | API routes (3 GETs) and the command door registration of `PUNCH_COMMANDS` | full | T01 | `tl-api/tests/test_commands.py`, `test_api_document_controller.py`, `test_api_proposals.py`, `docs/reference/openapi.json`, `test_confidentiality_walk.py` |
| T05 | MCP reads and `propose_punch_item` (`punch_tools.py`) | full | T01 | `tl-mcp` `test_mcp_server.py`, `test_mcp_identity.py`, `test_intent_param.py`, `test_mcp_write_tools.py`, walk candidates |
| T04 | Client methods, `quality_command` door, fake | full | T03 | `tests/api/test_client_roundtrip.py`, `tl-tui/tests/test_remote_client.py` |
| T06 | TUI: `punch_text.py`, punch log, record screen with `c`/`v`/`o`, palette glue | full | T04 | `test_palette.py`, `test_awp_nav.py` |
| T07 | Generator `quality` section on, roster grant, demo-project pins | full | S2 | `tests/tools/test_demo_project*.py` counts, runbook `demo-project.md` |
| T08 | Demo `dev/demos/P2-PUNCH.sh` and driver | full | T02 T03 T04 T05 T06 T07 | none |
| T09 | Docs: module README and AGENTS, root `AGENTS.md` row, `docs/modules/quality/`, runbook, reference page | lite | T08 | none |
9 tickets (one over the guide: T07 and T09 are small). Cheapest cut if the slice runs long: the TUI keys `c`/`v`/`o` in T06 (the CLI writes stay), then T07.

## Order of work and checkpoints
r1 plan (this) -> r2 S1 alone (human gate) -> r3 S2 -> r4 T01 beside T07 -> r5 T02, T03, T05 (disjoint folders) -> r6 T04 -> r7 T06 -> r8 T08 -> r9 T09.
- C1: S1 merged. C2: S2 merged. C3: every ticket merged or abandoned. C4: per-folder gate on touched packages, `just demo P2-PUNCH` on both adapters, `just gate-pg` on the touched directories, tour not needed.
Merge order: S1, S2, then tickets. The shared one-line files (`tl_api/app.py`, `tl_tui/app.py`, `commands.py`, `server.py`, `identity.py`, `uv.lock`, `openapi.json`) are touched by one ticket per wave; `just gen` runs last after each merge.

## Process lessons applied
Provided tests and acceptance scripts change state only through real commands (the module's `punch_world.py`), never projection writes; every named test path exists or sits under "Tests to add"; each demo clause's verb has an owning ticket (table above; P2-I5 demo gap: a missing MCP propose tool file and a settings-layer rule; here `punch_tools.py` is T05 and no setting is added); a new setting or access word is pinned by count in several test files, each ticket lists the pins it updates (union form); gates name test files or one package; write options take the key a read prints (L-P2-I3-3); every screen ticket needs its Textual-free text module in the ticket (L-P2-WEB1-1); new MCP tools stay closed until listed in `MCP_ACTIONS`.

## Security rows (one wave review, with the next wave's, owner-optional)
Scope when run: `bb6f855b..` head, <= 450k tokens, `F<n> <HI|MD|LO> file:line`. S2 subject join (`SUBJECT_LINKS` row: a punch item of a hidden source is hidden whole and answers as missing; `viewer=` defaults to the lowest clearance on every read); S2 verifier differs from clearer; S2 `expected_version`; S2 raiser taken from the context actor, never an input; T03 routes and the five-reader walk; T05 `propose_punch_item` resolves `from_key` under the agent's viewer and no tool clears or verifies; T02 takes no password or token.

## Risks and escalation
- Merge with `p2/i4a`: that branch also adds `SUBJECT_LINKS` (and `tests/tools/proposable_exclusions.toml`) to `confidentiality.py`; S2 uses the same shape with the punch row only, so the later merge is a union of tuple rows. A chain longer than two hops (constraint on a punch item raised from a requisition of a hidden IWP) is not claimed (`_HOPS` = 2); S4 closes it at the punch end: a punch item is raised only from a record that names no subject (not a constraint, and no `SUBJECT_LINKS` type), so every chain stays within two hops.
- An IWP is not confidential, so a hidden source needs a restricted correspondence item or document: the demo and tests use that.
- A core pinned list (`POLICY_EVENT_TYPES` in `tl_core/feed/cards.py`) may reject new quiet events: S1 stops and says so; it does not edit core.
- Escalate: a frozen contract change; an access word the table lacks; a piece failing twice; S2 needing a `tl_core` change beyond the join.
