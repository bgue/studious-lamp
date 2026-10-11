# Report — P0-I8 workstream A: about:config settings v1

Branch: `p0/i8a` (base `p0/i8`, merged in twice; the last merge is 2a819c6). Plan and decisions A1 to A21: `docs/tickets/P0-I8/README-A.md`. Demo: `just demo P0-I8-A`. Runbook: `docs/runbooks/settings.md`.

## Outcome
Objective met: yes. The platform has layered settings (platform default, company, project, user for UI keys) with the brief's §30 behaviour: the effective value shows its origin and the `●` marks a value set at the layer you look at; a company can lock a key or bound the values projects may use; every change is a `Setting.Changed` event with old and new value, actor, reason and effective time; `advanced` and `dangerous` keys need a reason and `dangerous` ones the risk accepted; changes can be scheduled; the history is complete and the latest change at a layer can be undone; a layer exports to and imports from YAML. It is reachable from the CLI (`tl config`), the REST API (`/settings`), MCP (`get_settings`, `propose_setting_change`) and the TUI (`F9`). An agent never sets a value: the API and the CLI refuse an `agent:` actor, the embedded TUI client refuses one when it is made, and MCP has only a proposing tool. Four consumers read their settings live: the feed (`feed.reactions.enabled`, `feed.signal_tags`), the webhook worker (`webhooks.egress.allowlist`, `webhooks.retry.max_hours`) and `tl lake sync --watch` (`lake.sync.interval`).

Demo verified (`just demo P0-I8-A`, "P0-I8-A demo ok"): defaults, set at company and project (origin and `●`), refusals for a bad value, a missing reason and an unaccepted risk, allow-list entries that are too wide or tunnel (refused even with the risk accepted), a dangerous key set with both, a lock that makes a project value inert, a scheduled change, history with undo of the latest only, diff, export and import into a second project, an MCP agent that reads and proposes (nothing changes), a person who accepts (a dangerous proposal only with the risk accepted, and it stays pending without), an agent token refused every write over HTTP, `tl lake sync --watch` waiting the interval, and the TUI screen saved as an SVG.

## Tickets
| ID | Outcome | Review rounds | Notes |
|---|---|---|---|
| T01 `tl config ls\|get\|history\|set\|reset\|lock\|revert` | merged 5fba5de | 1 | 26 tests. Docstrings rewritten as user help in S20 |
| T02 `tl config diff\|export\|import` | merged 1922851 | 1 | 14 tests. Coordinator ruling folded in (S13): an unreadable or non-UTF-8 file is an error line |
| T03 `/settings` routes | merged 18cd9cc | 1 | 18 tests. The provided test changed after the ticket ran (S8, S10) |
| T04 MCP `get_settings` | merged 9235f2a | 1 | 7 tests (the ticket said 8) |
| T05 feed settings | merged 44de0d7 | 1 | 5 tests (the ticket said 6). The two implementers died before committing; the coordinator re-ran them |
| T06 webhook settings wiring | merged 9fe5587 | 1 | 9 tests. `egress.py` unchanged |
| T07 `tl lake sync --watch` | merged fb25d32 | 1 | 9 tests. Missing ledger is fatal (A21) |
| T08 `ApiClient` settings methods | merged e86f9ea | 1 | 10 tests |
| T09 embedded TUI client settings | merged 4c4feea | 1 | 10 tests |
| T10 about:config screen | supervisor (S19) | review x2 | Not Haiku-able: modal flows with edit, reason and risk |
| T11 effects wiring | supervisor (S18, fixed in S23) | review x2 | A ticket would have been longer than the change |
| T12 runbooks | supervisor (S21) | review x2 | `settings.md` and edits to five runbooks |

Taken over: none. Abandoned: none. Supervisor pieces S1 to S6 (schema, projector and values, resolver, reader, service, the command and the proposals amendment) were reviewed by the orchestrator and by fresh reviewers; two review cycles followed.

## Reviews and what they changed
- First review (S1 to S6): changes requested. Fixed in S8 to S15: YAML import hygiene (no aliases, JSON-only values, text keys), copies out of the resolver and the reader, `True` is not `1`, undo only for the latest change (409 `setting_revert_not_latest`), `pending_effect` scoped to the view, proposal facts shown and a dangerous accept staying pending (422 `risk_not_accepted`), an egress allow-list validator and `always_refused`, policy providers read once per attempt with safe fallbacks, `isascii` in the budget read, `applies_at` validated before the risk check, `tl config` refusing agent actors.
- Second review (S17 to S22): changes requested, 3 MEDIUM and 4 LOW. Fixed in S23 to S29: restart is marked once the server listens (not before the app is built or the port bound); a rebuild marks the head it replayed in the same transaction (an `after_replay` hook on the adapters, both SQLite and Postgres); `FakeClient` settings follow the service (undo appends a row, same checks, same messages, a parity test that compares the two on a 30-step script); the screens repeat no service rule; the embedded guard text is built from `AGENT_MUST_PROPOSE`; a message quotes typed text at most 80 characters; the screen's omissions are recorded in A20; a remote test of the settings group and the screen against a live server.

## Gates (on the tip of `p0/i8a`, the commit before the one that adds this report)
| Gate | Result |
|---|---|
| `just check` (ruff, format, pyright, codegen drift, OpenAPI drift, licences) | green |
| `just test` | 4807 passed, 1 skipped (14 min 25 s), 26 snapshots passed |
| `just test-tui` | 529 passed, 26 snapshots passed |
| `just test-parity` | 1884 passed (SQLite and Postgres), 26 min 15 s |
| `just demo P0-I8-A` | "P0-I8-A demo ok" |
| Docs audit (`dev/tools/audit_docs.py`) | 0 findings for tl-api, tl-cli, tl-mcp, tl-tui and tl-adapters; 1 for tl-core (`tl_core.extypes`, workstream B) |

## Deviations from the plan
- **`F9`, not `Ctrl+,`, opens the screen** (A20): terminals do not deliver `Ctrl+,`. The palette has `about:config`.
- **Screen omissions** (A20): diff against another project, Enter toggling a boolean, origin as scope ids, lock on `L` (it is `k`), scheduled changes and company bounds; use `tl config` for those.
- **D2 deviations**: no `schema.conformance.mode` setting yet; `lake.sync.interval` needed a new `tl lake sync --watch`; `ai.agents.default_mode` is stored, shown and lockable, but nothing reads it.
- **T10, T11, T12 were supervisor-built**, not Haiku tickets (reasons above).
- **The platform has no key with a non-`live` effect yet.** The effect machinery (`pending_effect`, `setting_effect_applied`, `tl projections rebuild`, the server start) is tested with extension-style definitions only.
- The settings written by the embedded TUI client are not noted in `own_writes` (they are not records); the remote client records source `api`, the embedded one `tui`.

## Escalations and decisions
- Contract amendments (D3: `PROPOSABLE_TOOLS`, `accept_risk` in the accept body) and the `schema/**` changes of S1 and S2 were listed as SCHEMA_APPROVALS in round 1.
- The coordinator ruled on T02 (decode inside the error handler), on the embedded agent guard (exact message, one constant), and told me to merge `p0/i8` at the start of round 4.
- A21: a missing ledger ends `tl lake sync --watch`.
- Human gates not crossed: which person may change or lock which key (the permission model, ADR-0005), and a vault for secret settings (a `secret` key is refused).

## Learnings
L-P0-I8A-1 to L-P0-I8A-11 in `docs/memory/LEARNINGS.md` (module and function name clashes, the generated JSON schema's `Any`, fake clocks, Typer `add_typer` flattening, MCP ignoring undeclared arguments, literal counts in tests, ticket test counts, hostile numbers and nesting, the snapshot report file, Typer help from stub docstrings). Implementer proposals declined: none; the T07 note became A21, the T09 note became L-P0-I8A-11, the T05 note (stale comment in `feed/types.py`) was fixed in S17, the T08 note on hanging stream tests is a load effect already seen in P0-I8-C and is not repeated as a learning.

## Docs
Created: `docs/runbooks/settings.md`, `docs/tickets/P0-I8/README-A.md` and the T01 to T09 tickets, `dev/demos/P0-I8-A.sh` with `dev/demos/p0_i8_a_demo.py`. Updated: `docs/runbooks/README.md`, `lake-sync.md`, `rebuild-projections.md`, `webhook-operations.md`, `proposal-review-queue.md`, `tui-dev.md`; README.md and AGENTS.md of `tl-core`, `tl-cli`, `tl-api`, `tl-mcp` and `tl-tui`. `uv run python dev/tools/audit_docs.py` reports 0 findings for these packages; its one finding is `tl_core.extypes` (workstream B).

## Follow-ups filed
- Older commands print implementation steps as help text, as `tl config` did (L-P0-I8A-11): `tl proposal ls --help` and others show "In a read-only unit of work call ..." instead of user help. A sweep of every `@app.command` docstring is a small ticket.
- `tl_core.extypes` is undocumented in the `tl-core` README (workstream B).
- The `docs` text of `webhooks.egress.allowlist` in `schema/settings/platform.yaml` does not mention the tunnel ranges the validator now refuses (a schema edit, so a delegated approval).
- TUI: scheduled changes and company bounds in the form; diff against another project (needs a `ClientInterface` method).
- The first key with a non-`live` effect should come with an end-to-end test of `pending_effect` through the CLI.
- Who may change or lock which key (permission model) and a vault for secret settings are human gates.
- Process hygiene: stop a run by its pid, not with `pkill -f <pattern>`; the build container is shared and a broad pattern can stop another agent's test run (it happened once during these gates).
