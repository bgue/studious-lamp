# Increment plan: P0-I8 workstream A, about:config settings v1

Status: in-progress
Supervisor session: 2026-10-10
Brief sections: §30 (settings), §10.6 sketch 14 (about:config screen), §31.1 (a type package's `settings.yaml`), §11.3 and §18.12 (agents propose)
Branch: `p0/i8a` (worktree `/home/user/wt/p0-i8a`), based on `p0/i8`; fanout plan `docs/tickets/P0-I8/FANOUT.md` (decisions D1 to D6 bind this workstream)

## Objective
Every tunable behaviour of the platform that already exists is a named, typed, documented, layered and ledgered setting. A person (or a script) reads
the effective value with its origin and the ● marker, sets or resets it at the company, project or (for `ui.*` keys) user layer, locks it or
bounds it for projects, schedules a change, sees the per-key history and reverts a change, diffs two layers and exports or imports a layer as YAML.
Dangerous and advanced keys need a reason and an explicit "I accept the risk". An AI agent never changes a setting: it proposes (`propose_setting_change`)
and a person accepts. The behaviour that used to be a constant (feed reactions and signal tags, webhook retry window and egress allow-list, the
agent proposal budget) reads from the settings, and a live change applies without a restart.

## Demo
```
just demo P0-I8-A
```
`dev/demos/P0-I8-A.sh`: a scratch ledger; `tl config ls --project P123` shows the defaults; `tl config set` changes a key at the company and the
project layer (● marks the project's own value, origin names the layer); a dangerous key is refused without a reason and without `--accept-risk`;
`tl config lock` makes the project's value inert; a scheduled change shows under `scheduled` and takes effect when its time comes; `tl config history`
and `revert`; `tl config diff default company`; `export` and `import` into a second project; an agent proposes a setting change over MCP and a person
accepts it; the API returns 403 `agent_must_propose` for an agent token; the TUI screen (`F9`) is shown as an SVG snapshot.

## Decisions
| # | Decision |
|---|---|
| A1 | **`cur_setting` has one row per `Setting.Changed` event** (not one per key and layer). It is the per-key history and the resolver's input; the "current" value is a function of the rows and the clock. `cur_setting_lock` has one row per key that was locked or bounded. `setting_effect_applied` is the operational table of D6 (`tl:current_state` only to get one DDL; created by the projector, never cleared by `reset`). |
| A2 | **Resolution is time-based** (D5). At each layer the entry in force is the one with the greatest `effective_us` (the later of `recorded_at` and `applies_at`), then `seq`, not after `t`. So a change recorded later but applying earlier wins until the earlier-recorded scheduled one applies, and an immediate change does not cancel a scheduled one. A scheduled change is cancelled by reverting it: that records the old state for the same instant, which wins the tie by `seq`. |
| A3 | **Locks and bounds are enforced twice**: when a project or user value is set (409 `setting_locked`, 422 `setting_out_of_bounds`) and when it is resolved (a stored project or user value that a later lock or bound makes illegal is ignored). The company layer is never bounded by its own bounds. A project may still reset a locked key (clean-up). |
| A4 | **Layer to ledger**: stream `setting:<layer>:<key>` (type `core.Setting`), event scope `project:<id>` for a project layer, else `company` (the user layer too). `Setting.Locked` uses the company stream of the key, so lock and change events share one version counter. |
| A5 | **The viewed layer** (for `modified_here` and `scheduled`) is the most specific layer asked for that the key allows: user (UI keys), else project, else company. A key whose `scopes` are only `platform` has none. |
| A6 | **`pending_effect`** (D6): a key with a non-`live` effect owes it while it has a change that took effect after the effect was last carried out (`setting_effect_applied.applied_seq` and `applied_us`; a change counts when its `seq` is newer or it took effect later in time). A rebuild satisfies a `reindex` too. `tl_core.settings.effects.mark_applied` writes the rows. |
| A7 | **Reader, no global state.** `SettingsReader` (cached snapshot of the three tables plus per-key answers valid until the key's next `applies_at`) invalidates on `Setting.*` events from a bus and expires after `max_age_s` (default 30 s) for processes that do not share the writer's bus. Code that runs inside a unit of work reads through `uow.conn()` (`settings.value_of`), so it sees its own transaction and needs no wiring; long-running workers build a reader over their unit-of-work factory. |
| A8 | **`ChangeSetting` is the command** behind `propose_setting_change` and `POST /commands/ChangeSetting`. A proposal never carries `accept_risk`: the person who accepts supplies it (`accept_or_fail(..., accept_risk=True)`, the accept route's body, `tl proposal accept --accept-risk`). A proposal for a dangerous key is not refused at proposal time for lacking it, and **accepting it without `accept_risk` raises `risk_not_accepted` (422) and leaves the proposal pending**: no `Proposal.Failed`, no re-proposal, no spent budget. `ReasonRequiredError` is refused at proposal time. A `ChangeSetting` proposal shows, from the definition and the ledger and not from agent text, its key, layer, the user a `user:` layer belongs to, current and proposed value, risk and effect (`ProposalView.setting`, `tl proposal ls` tags a non-normal risk, `show` prints the facts). |
| A9 | **"An agent never sets a value directly" is enforced where B15 enforces it for records**: the API guard (403 `agent_must_propose`) and MCP having only a proposing tool. The service functions take any actor (the proposal dry run and the accepted command both use them); the CLI write commands refuse `agent:*` (A18). |
| A10 | **`Setting.*` events are transparent to feed cards** (`TRANSPARENT_PREFIXES`): configuration, personal preferences included, is not feed content and must not split a burst of record events. |
| A11 | **Export/import document**: `version: 1`, `layer`, `settings: {key: value}` and for the company `locks: {key: {locked, bounds}}`. Export writes what the layer holds in force now (no schedules, no resets). Import applies keys in sorted order inside the caller's unit of work (all or nothing), takes one `reason`/`accept_risk` for all keys that need them, ignores the file's own `layer`, leaves keys that already hold the value alone, and accepts locks only into the company layer. Limits: 256 KiB, 1000 keys. |
| A12 | **Operator overrides stay**: `TL_AGENT_DAILY_PROPOSALS` wins over `ai.agents.daily_proposals` when set to a non-negative whole number (tests and the simulator use it), and `--allow-host`/`TL_WEBHOOK_ALLOWLIST` add to `webhooks.egress.allowlist` (they are explicit operator flags for one process). |
| A13 | **Deviations from D2**: (1) `schema.conformance.mode` is not a setting: the conformance code reads the mode from the schema packages in force (§6.3), and the same mode drives workflow guards; making a setting override it needs a ruling on which wins and touches contractual guard behaviour. Reported to the orchestrator. (2) `lake.sync.interval` had no constant to swap: there is no scheduler, so the ticket adds `tl lake sync --watch`, which reads the interval before every wait. (3) `ai.agents.default_mode` has one allowed value (`propose`) and nothing to wire: it is stored, shown, lockable and validated; `write` stays a human gate (ADR-0005). (4) `project.mode`, `ui.tui.keymap` and `ui.tui.graphics` are stored and shown only, as D2 says. |
| A14 | **`tl_core.settings.registry`** (not `definitions`) is the module with the registry, because the package exports the function `definitions()` from the contract and a submodule of the same name would be hidden by it. |
| A15 | **Only the latest change at a key and layer can be reverted** (409 `setting_revert_not_latest`): reverting an older one would silently discard the later ones. A not-found `seq` stays 404. Reverting a pending scheduled change that is the latest cancels it (A2). |
| A16 | **The egress allow-list is validated item by item** (`tl_core/settings/checks.py`): host name, `host:port`, IP or CIDR; a range at least /8 (IPv4) or /16 (IPv6); link-local, cloud-metadata (169.254.0.0/16, fe80::/10, fd00:ec2::254, 100.100.100.200), `0.0.0.0/8` and the metadata host names are refused; loopback stays allowed (D14). The delivery engine also refuses those addresses for any target, allow-listed or not (`egress.ALWAYS_REFUSED`), so `--allow-host` and `TL_WEBHOOK_ALLOWLIST` cannot reach them either. A DNS name that is allow-listed and later resolves to a private address is still the operator's trust decision (unchanged). |
| A17 | **Policy providers read once per attempt**: `DeliveryEngine.attempt` resolves egress and retry at its top and carries the retry policy on the outcome, so `settle` (inside the write transaction) never calls a provider. A failing egress provider means the strict default (empty allow-list), never the last or a wider one; a failing retry provider means the last good policy. Both are logged. |
| A18 | **The `tl config` write commands refuse `--actor agent:*`** (`tl_cli/actors.py`, an option callback; exit 1, `error: agent_must_propose: ...`), matching the API (D3 is absolute). The service functions still take any actor (A9). |
| A19 | **YAML import hygiene**: no anchors or aliases (a 280-byte file expanded to a million items), only JSON-typed values (dates, timestamps, sets and bytes are refused naming the key), text keys, nesting up to 12 levels. Values returned by the resolver and the reader are copies. No-op detection and choices compare canonical JSON (`true` is not `1`). `pending_effect` counts only the layers of the view being read. |
| A20 | **The about:config screen opens with `F9` (and the palette command `about:config`), not `Ctrl+,`**: most terminals do not deliver `Ctrl+,`. It writes through `ClientInterface` only, asks the form for the reason and the risk, and shows the service's refusal. Scheduled changes and company bounds are not editable from the screen (use `tl config`). The embedded client refuses an `agent:` actor (WS-B review ruling). |
| A21 | **A missing ledger ends `tl lake sync --watch`** (exit 1, `error: no ledger at ...: run `tl init``), because `_ledger_snapshot` exits the command: the ledger is the thing being copied, so a watcher without one has nothing to wait for. A busy or failing sync is not fatal: the watcher prints `error:` and tries again after the wait; an unreadable interval keeps the last good one. |

## Supervisor-built pieces (in order)
| # | Piece | Why supervisor-tier | Reviewer | Status |
|---|---|---|---|---|
| S1 | `schema/core/settings.yaml` (SettingDefinition, `Setting.Changed` and `Setting.Locked` catalog payloads, `cur_setting`, `cur_setting_lock`, `setting_effect_applied`), `schema/settings/platform.yaml` (the D2 keys), generated output, catalog scenario | schema (delegated approval); the platform keys are data the whole run reads | orchestrator | done (ffcff98) |
| S2 | `SettingProjector`, definitions registry and loader, value checks (`values.py`), layers, `effects.py`; feed cards ignore `Setting.*` | projection determinism, value semantics | fresh reviewer | done (d54023b) |
| S3 | Resolver (`resolve`, `resolve_all`, `history`, `diff`, `resolve_from` with an oracle property test), `views.py` | layer resolution, locks, bounds, schedules, origin and ● | fresh reviewer | done (15963d7) |
| S4 | `SettingsReader`, `conn_factory_from`, bus invalidation and expiry | concurrency (the race test) | fresh reviewer | done (05f918e) |
| S5 | Service: `change_setting`, `set_setting`, `reset_setting`, `lock_setting`, `revert_setting`; export/import; the `SettingError` classes | validation and refusals | fresh reviewer | done (b3436c0) |
| S6 | `ChangeSetting` command, proposals amendment (D3: `PROPOSABLE_TOOLS`, `accept_risk`, the budget read), MCP `propose_setting_change`, engine policy providers | contract amendment, propose-only enforcement, delivery engine | orchestrator | done (b735db3) |
| S7 | Stubs, provided tests and references for the surface tickets (round 1: T01 to T03; later rounds the rest) | scaffolds | | done (S11, S16, S18) |
| S8 to S16 | Review fixes and merges (see the commit log: S8 ad6771a, S9 1296416, S10 633ffaa, S11 0aead7f, S12 2054db9, S13 9e3a4ad, S14 96c2000, S15 165b005, S16 b7bac09) | review | fresh reviewers | done |
| S17 | Review LOW fixes: hostile numbers and nesting, IPv6 tunnel ranges in the egress allow-list | security hygiene | orchestrator | done (5cd1705) |
| S18 | Effects wiring (T11), `view_at`, the TUI settings contract, `FakeClient` settings, stubs for T07 to T09 | contract, determinism | orchestrator | done (18d8108) |
| S19 | The about:config screens (T10), the embedded-client agent guard, `tl-tui` docs | UI state machine with modal flows; not Haiku-able under the checklist (no short, checkable specification) | fresh reviewer | round 4 |
| S20 | `tl config --help` rewritten as user help (the merged ticket docstrings carried implementation steps) | quality | fresh reviewer | done (117aec5) |
| S21 | Demo, runbooks (T12), READMEs, report | closing work | | todo |

## Tickets
| ID | Title | Tier | Depends | Status | Outcome |
|---|---|---|---|---|---|
| P0-I8-T01 | `tl config ls\|get\|set\|reset\|lock\|history\|revert` | haiku | S4 | merged (pass) | 5fba5de |
| P0-I8-T02 | `tl config diff\|export\|import` | haiku | S4 | merged (pass) | 1922851 |
| P0-I8-T03 | `/settings` routes (`POST /commands/ChangeSetting` and the accept body's `accept_risk` are on the base) | haiku | S4, S6 | merged (pass) | 18cd9cc |
| P0-I8-T04 | MCP `get_settings` | haiku | S4 | merged (pass) | 9235f2a |
| P0-I8-T05 | feed reads `feed.reactions.enabled` and `feed.signal_tags` | haiku | S4 | merged (pass) | 44de0d7 |
| P0-I8-T06 | webhook retry window and egress allow-list read the settings | haiku | S5 | merged (pass) | 9fe5587 |
| P0-I8-T07 | `tl lake sync --watch` reads `lake.sync.interval` | haiku | S5 | merged (pass) | fb25d32 |
| P0-I8-T08 | `ApiClient` settings methods | haiku | T03 | merged (pass) | e86f9ea |
| P0-I8-T09 | TUI client: embedded settings calls (the remote client passes the ApiClient methods through; the contract and the fake are S18) | haiku | S18 | merged (pass) | 4c4feea |
| P0-I8-T10 | TUI about:config screen (`F9`) with snapshots | supervisor | S18 | built (S19) | modal flows with edit, reason and risk; a ticket would need the whole design pasted |
| P0-I8-T11 | effects: `tl projections rebuild` and the server start write `setting_effect_applied` | supervisor | S2 | built (S18) | a ticket would have been longer than the change (about 15 lines and one test file); reviewed with the S-commits |
| P0-I8-T12 | `docs/runbooks/settings.md` and the runbook edits | supervisor | T01 to T09 | todo (S21) | |

## Order of work
1. Round 1 (this one): S1 to S6, tests, the plan; stubs, provided tests and references for T01 to T03; DISPATCH T01, T02, T03.
2. Round 2: merge T01 to T03; stubs for T04 to T06; DISPATCH (merged: 9235f2a, 44de0d7, 9fe5587).
3. Round 3 (S17, S18): the review LOW fixes; T11 built by the supervisor; the TUI settings contract, the fake and the stubs for T07 to T09; DISPATCH T07, T08, T09 (at most three per batch).
4. Round 4: the about:config screen contract (S19) and T10; T12; the demo, READMEs, learnings and the report; DONE.

## Risks and escalation triggers
- **Settings touch feed, webhooks, lake, proposals, MCP, API, CLI and TUI.** Only this workstream changes them; the swap tickets keep each change to one package and keep the old behaviour as the default.
- **The webhook egress allow-list is a security control.** The swap (T06) must keep the SSRF rules of `egress.py` unchanged; a widened list is only reachable through a `dangerous` key that needs a reason and the risk accepted. Orchestrator review.
- **Who may set or lock dangerous keys is the permission model (human gate).** v1 applies the mechanism only; an approval workflow for dangerous keys is a follow-up (D3).
- **`tl_core/settings/types.py` is frozen.** Anything that would change it (a new field of `EffectiveSetting`, a payload field that is not additive) is escalated.
- **A known red on the base**: `packages/tl-schema/tests/test_catalog.py::test_every_event_type_the_code_names_is_in_the_catalog` fails on `p0/i8` because `tl_core/extypes/types.py` names four event types that workstream B has not catalogued yet. It is not this workstream's to fix; tickets are told to expect exactly that one failure.

## Blocked / Decision
(none yet)
