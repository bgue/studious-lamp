# Deferred side quests

Owner rule (2026-11-07): log major side quests and defer them; do none of them now unless they block the work in hand.
One line each: what, why it waits, and the phase it belongs to. Newest at the bottom of each group.

## Security reviews
| Item | Why deferred | Phase |
|---|---|---|
| Wider security review of the terminal release (beyond the release-path checks) | Release needs only the sign-in, token and server-connection paths checked | Phase 2 exit |
| Web security re-check of everything added since SEC-C4 (web look v2, wave 2 web twins) | The web stays off in production until its next review; it runs with the web increment | Web increment after wave 4 |
| Project membership on reads: unknown or not-a-member project answers the one 404 page (web and API); `item_projects` filtered by membership | Projects are not a read boundary in the MVP (roles-mvp §7) | Phase 3 I8 |
| Wave security reviews for P2-I2 to I5 beyond the per-increment Sec rows | Owner: security reviews are owner-optional; keep to what release needs | Phase 2 exit |
| An agent's own module role is not checked when it files a proposal (`submit` skips `require_command_access`), and agents read internal records of any project (agent-first spec 3.1) | People still decide every proposal with their own access; fix with read scoping | Phase 3 |

## Test runs
| Item | Why deferred | Phase |
|---|---|---|
| Full per-folder run more often than once per wave close | Each ticket's own gate is the rule | wave closes only |
| The whole parity suite on Postgres | Dedicated time | Phase 2 exit |
| Phase mutation sweep (30–60 mutants) | Dedicated time | Phase 2 exit |
| `test_stream.py` can hang; a stream test flakes under load (passes alone) | Not blocking; a bounded timeout is the fix | Phase 2 exit |
| The web test seed fails on Postgres (Q4) | The web tests run on SQLite | Web increment after wave 4 |

## Refactors
| Item | Why deferred | Phase |
|---|---|---|
| Pinned module, command and tool lists computed from the registries instead of written by hand | They break on every merge of two modules (wave 1 close: 25 fixes) | Phase 2 exit |
| Tests in other packages import the materials acceptance scripts through `sys.path` (L-P2-I3-1) | Works; move shared fixtures to a test helper package | Phase 2 exit |
| `dev/gate.sh` per-folder mode as the default whole run | The four-part run no longer fits 16 GB; a script does it today | wave 3 close |
| `refresh_preview.sh` leaves the tools out when it stops on a conflict | Replaced by the demo project generator for the tour | with item 1 (generator) |

## Nice-to-haves and small follow-ups
| Item | Why deferred | Phase |
|---|---|---|
| WBS node workflow and constraint opt-in on WBS nodes (ADR-0024 plan check F10) | No wave 2 demo clause needs it; overlaps I5 progress | wave 3 |
| Six materials terminal screens have no technical-mode rows (D, E, I, M, S, W) | Missing feature, not a break | wave 3 |
| `tl mat move reserve --for-line` should take the take-off line key, not its record id | Usability; the runbook points at the API for the id | wave 3 |
| Plain mode shows `@N` in take-off line keys (`P200-200-ISO-0901@0/MTO/001`) and lot references (`P200-RCPT-0001@1`); show them in words (rev 0, line 001) so the plain-text leak check passes. The demo tour marks those two shots technical until then (P2-SEED-T03) | Display change in the materials screens; not a leak of hidden data | wave 3 |
| Locations web page: tree indent and lot counts (WEB1 D46) | Cosmetic | Web increment after wave 4 |
| WBS reload keeps a reinstated node's old title (S7 F6); the CWA target has the same reload shape | The demo needs the same tree only | wave 3 |
| `tl awp worker` has no access word; spec §3 role wording | Docs and a small gate | wave 3 |
| P2-W0 follow-ups: Add property shown to readers who would be refused; technical-mode label gaps; RFI panel overdue uses the wall clock | Small UX items | Phase 2 exit |
| Web pages for the wave 3 and 4 logs; create forms (old P2-WEB2) | Owner: CLI and TUI first | Web increment after wave 4 |
| TUI inside the web page as a second mode | Recommendation no (remote-shell-shaped surface, second UI); see the panel spec §7 | not planned |
| Drawings and model panel extras: preview pictures, `tl-tui[images]`, a following 200-column TUI pane, an external model viewer link, three web layouts | The plan check (F8, F11) keeps v1 small: TUI modal and tab, web drawer | after the web increment |

## Platform features (owner, 2026-11-07, parts B to E)
| Item | Why deferred | Phase |
|---|---|---|
| Native automation rules: an IFTTT- or n8n-style rule builder inside Throughline. Hard parts: authority (a scoped service account, or rules that only file proposals for a person to approve); confidentiality (a rule's effects must not reveal hidden records); rule management (loops, rate limits, rules versioned like schema packages). Until then external tools use the outbound webhooks and inbound mappings | Large; external tools cover it today | Phase 4 or 5 |
| Goal records; a read-only goal view walking from an end state through its open constraints to each target's allowed next actions and who may take them; agents that plan toward an end state and file proposals at each step; automatic intents from readiness and constraint clearing | Intent slot first (ADR-0025); the rest builds on it | Phase 3 |
| Knowledge graph build: the creator tool, the ledger hash chain, the record graph tab and the project graph view (ADR-0026, `specs/graph-views.md`) | Design only now; stubs go in with constraints and intents | Phase 3 (chain with replicas) to Phase 4 |
| Agent-first layer: agent accounts with module roles per project and module, proposal rationale and evidence, a batch review queue, delegation and escalation policies, an agent activity and acceptance view (design note) | Design only now; each new module from wave 3 gets a proposable path | Phase 3 to 4 |
| Insights: data-health checks (missing owner, stale draft, orphan link) on the Checks tab (roadmap insights item 1) | Part C builds the tab on existing checks first | Phase 2 exit |
| Insights: provider registry and router, existing checks wrapped as providers (item 2, ADR-0028) | Needs the contract accepted; Part C needs no registry | Phase 3 early |
| Insights: `cur_insights` projection with recompute, expiry and the dismissal table (item 3) | Needs the registry; no provider yet makes insights | Phase 3 early |
| Insights: telemetry reader (CLI, TUI log, retention, privacy review of free text) (item 4) | Part C writes the table only; a reader needs the viewer filter and a review | Phase 3 early |
| Insights: best-practice library of versioned rule packages (item 5) | Needs a rule format design and the rules-of-credit governance from wave 3 | Phase 3 early |
| Insights: retrieval index on a local similarity model, per clearance or query-filtered (item 6) | Needs a model and licence choice and a vector store in both adapters | Phase 3 mid |
| Insights: suggestions on local models, five kinds (item 7) | Needs items 2, 3 and 6 and real accept and dismiss data | Phase 3 mid |
| Insights: evaluation set from the demo project generator (item 8) | Needs the generator and the first providers | Phase 3 mid |
| Insights: offline behaviour, analysis and ask queued until reconnect (item 9) | Needs Phase 3 sync | Phase 3 mid |
| Insights: security review before any suggestion or analysis provider goes live (item 10) | Owner-optional reviews are kept to what ships; this one gates the first provider | Phase 3 mid |
| Insights: analysis jobs and the per-person inbox (item 11) | Needs a carried viewer in jobs, the queue and a spend decision for non-local models | Phase 3 late |
| Insights: Ask, a record-scoped conversation with cited answers (item 12) | Needs retrieval, analysis jobs, a streaming route and a spend decision unless local | Phase 3 to 4 |
| Insights: web versions of the Insights tab, inbox and Ask (item 13) | Owner: CLI and TUI first | Web increment after wave 4 |
| Activity and Insights extras: "show in graph" from an Activity row, related activity beyond one hop, subtab hot keys, an Activity web page | Part C keeps one hop and the TUI only | Phase 4 and the web increment |
