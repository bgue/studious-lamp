# P2-INS — Activity and Insights record tabs, Checks, telemetry stub (part C of the owner's Insights request)

Status: planning (round 1, docs only; nothing dispatched; start after the wave 2 merge)
Supervisor session: 2026-11-08
Brief sections: §5.1, §8, §11.3, §18.12. Spec: `docs/build-spec/specs/insights-and-activity.md` (its "Plan check" section wins). ADR: `docs/adr/0028-insight-providers-routing-telemetry.md` (plan-check answers F1 to F12 win over its body). Owner words: part C of the request of 2026-11-07.
Branch: `p2/ins`, from `p2/wave2-close` @0ae6527 (constraints, readiness and the IWP screens are on it; the intent slice, ADR-0025, is not).

## Objective
Replace the record screen's History tab with an Activity tab (everything that happened around the record, "Revisions only" one key away) and add an Insights tab on key `9` whose Checks subtab
is filled from what exists; the other three subtabs say "not available yet" and note the unmet need. Add the telemetry table and its one write path, with no reader. Nothing acts alone; reads write nothing;
a hidden record leaves no trace in either tab.
**Intent "why":** the ADR-0025 slice has not landed, so the Activity `Why` column is empty and drops out of the table, and Checks shows no "why this is open" line. Both appear when the slice lands, with no change to the contracts here.
Out of scope (roadmap item 1, plan check F4): the log `!` marker and filter, the panel "Needs attention" line, `attention_counts`, data-health checks, stale-pin and orphan-link findings, any telemetry reader, providers, router, `cur_insights`.

## Owner and plan-check answers applied
| Point | Applied as |
|---|---|
| F3 keys and name | Insights is key `9`; the log filter (later) is `!`; never `n` or `I`. Module `record_activity_text.py` |
| F5 proposals | No `cur_proposal_subjects`: accepted proposals by `cur_proposals.result_stream_id`, pending and rejected by a scope-bounded match on the stored command, then `filter_events` |
| F6 paging | By `seq` over `outbox_events` plus `cur_links` for the far end; filters before LIMIT with refill; caps; statement count pinned in S1 |
| F7 telemetry | Screen-opened rows hold `record_type` only; `record_id` only for an explicit request; one note per session, type and subtab; route refused to agents and rate-limited (30 per 10 minutes per actor); nested transaction; `recorded_at` indexed. Owner question I-Q5 stays open (see OPEN) |
| F8 shape | Telemetry folds into S2; walking tests inside S1 and S2; 2 S + 4 H |
| F9 slots | S1 and S2 run in one workflow, before or after the ADR-0025 slice, not beside it; T02 owns `record_view.py`; T02 and T03 merge outside the release freeze; this increment yields its slots once wave 3 answers land |
| F12 Sec | Rows below; range `<p2/wave2-close>..<p2/ins head>` |

## Demo
No `just demo` script: it is not in the 2 S + 4 H budget (OPEN Q2). Each piece leaves `dev/accept/P2-INS/<id>.py`; the screens are shown by the tour. By hand on the generated demo project (SQLite, then Postgres):
1. Open an IWP in the record screen, press `4`: Activity lists edits, moves, links, files, posts, proposals and constraints, newest first; `v` gives today's revision list; `r` hides related rows.
2. Answer an RFI that a constraint targets: the constraint's Activity shows "RFI answered" marked `↳` (related); for a reader who cannot read the RFI the row is absent and nothing else changes.
3. Press `9`: Checks lists the blocked readiness check, the open constraint, a missing expected link, an overdue clock and a short MTO line, grouped by source; a clean record says "Nothing needs attention."
4. Right arrow to Suggestions: "Suggestions are not available yet."; the database holds one `telemetry_need` row (record type, no record id) and a second visit adds none.

## Pieces (builder, `kind: piece`, review full)
| Id | Piece | Spec | Depends | Sec | Gate (orchestrator APPROVALS line) |
|---|---|---|---|---|---|
| S1 | INS-A1: `record_activity`, `GET /records/{id}/activity`, `ClientInterface.activity`, both clients and the fake, walking test, statement count | `S1-activity-read.md` | wave 2 close | Activity related-hop filter (row S-A) | interface line (with S2) |
| S2 | INS-B1 + T1: `CheckFinding`, `record_checks` (five sources), `GET /records/{id}/checks`, `ClientInterface.checks`, `telemetry_need`, `note_need`, route `POST /insights/needs`, setting, walking tests | `S2-checks-telemetry.md` | wave 2 close | Checks `resolve_via` and detail filter (S-B); `note_need` route (S-C) | schema line (`schema/core/telemetry.yaml`, one setting) and the same interface line |

## Tickets
| ID | Title | Tier | Rev | Depends | Status |
|---|---|---|---|---|---|
| T01 | INS-A2: Activity text module (`record_activity_text.py`) | haiku | lite | S1 | draft |
| T02 | INS-A3: Activity tab replaces History; filters `v` `r` `/`; owns `record_view.py`; stub Insights pane and key `9` | haiku | full | S1, T01 | draft |
| T03 | INS-B2: Insights tab, Checks list, three "not available yet" subtabs noting the need | haiku | full | S2, T02 | draft |
| T04 | INS-A4+B5: twin tests of Activity and Checks | haiku | full | S1, S2 | draft |
Tickets are drafted against the S1 and S2 contracts; the round after S1 and S2 merge re-reads the merged code, refreshes the pasted blocks and runs the Haiku-ability checklist (§6) before dispatch. Total 2 S + 4 H, about 3 points.

## Sec rows (security review scope: one fresh review at DONE; range `<p2/wave2-close>..<p2/ins head>`)
| Row | What to prove |
|---|---|
| S-A Activity related hop | The viewer filter runs at the link (either end hidden drops the far end, in SQL, before events are read) and again on the far record's events; only the six cause relations and the six event types; caps hold; a twin without the link gives equal rows, order and counts; the proposal command match returns no proposal that names a hidden record |
| S-B Checks `resolve_via` and `detail` | A readiness result computed with no viewer never reaches a reader with a hidden key in `resolve_via`, `detail` or `text`; a constraint with a hidden target keeps its row and shows no target; counts are not identities |
| S-C `note_need` route | Refused to agent tokens; actor and role from the token, never the body; closed sets; no content column; per-actor rate limit; `begin_nested` never poisons the caller's transaction; screen rows carry no record id; the table is outside the ledger, archive, lake, outbox, webhooks, sync and projection rebuild |

## Order of work
1. Round 2 (orchestrator dispatches after the wave 2 merge): S1 and S2 in one workflow (disjoint Allowed paths; shared files `client.py`, `embedded.py`, `remote.py`, `fakes.py` and `app.py` get methods and one registration line in different places, so a merge conflict is append-only and the orchestrator resolves it).
2. After S1 and S2 merge and the orchestrator records the two APPROVALS lines: next round refreshes T01 to T04 and dispatches T01 and T04 (disjoint paths).
3. T02 after T01; then T03 after T02 and S2. T02 and T03 merge outside the TUI release freeze (the History tab stays until T02 merges; a release that misses the freeze ships History).
4. DONE: whole-suite gate, `gate-pg` on touched directories, the security review on S-A to S-C, `just tour` rows for the two tabs, the report.

## Risks and escalation triggers
- The outbox has no index on `stream_id`; S1 relies on `subject_id IN (...) AND stream_id IN (...)`. If a link or thread kind cannot be reached without a new index, S1 stops (schema change, not in this increment's gate).
- S1 and S2 both extend `ClientInterface`; the fake and the conformance test must list both. Pins are listed in each report.
- Slot: wave 3 answers (owner) outrank this increment; it pauses at a piece boundary if they land.
- No demo script yet (OPEN Q2).
- Stop for the orchestrator if: the interface must change after S1 or S2 merges; a twin test fails (a finding); the telemetry table is treated as a projection by the generator.

## Blocked / Decision
(filled during escalation)
