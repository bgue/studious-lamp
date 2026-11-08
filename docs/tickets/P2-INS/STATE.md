# P2-INS STATE  r=2 base=2fbcdcf C=2 ck=0 gate=n/a wt=/home/user/wt/p2-ins
## BOARD   <id> <t|p> <todo|stg|disp|pass|mrg|abn|2s|gr|blk> <l|f> <sha|-> <note, <= 8 words>
S1 p mrg f 96d4a51 Activity read, route, client; APPROVALS a6a854e
S2 p mrg f 06e2c3e Checks, telemetry, note_need; APPROVALS 2fbcdcf
T01 t todo l - real text bodies over committed stub; ready
T02 t todo f - ActivityTab + InsightsTab stub widgets, no record_view; ready
T02b t todo f - record_view wiring, keys 4/h/9, keymap, pins; after T01+T02
T03 t todo f - Insights tab Checks + 3 unmet subtabs; after T02b
T04 t todo f - twin tests core level; independent, ready now
## DEC     D<n> <date> <one line: what, why, where recorded>
D1 2026-11-08 Activity pages by outbox seq (before_seq), not recorded_at; S1 spec
D2 2026-11-08 Link events found via subject_id IN + stream_id IN (no stream_id index); S1
D3 2026-11-08 Check sources are module functions, assembled once in tl_api/insights_sources.py; S2
D4 2026-11-08 Related hop: 6 relations, 6 event types, caps 100/30/1000; S1
D5 2026-11-08 note_need route: 204, 30 per 10 min per actor, agent refused, screen rows record type only; S2
D6 2026-11-08 T02b owns record_view.py and the Insights pane and key 9; T03 edits one compose line only (F9)
D7 2026-11-08 No why on base: Why column drops out; no skipped test (T04)
D8 2026-11-08 Stale pins, orphan links, data health, log marker, panel line stay roadmap item 1 (F4)
D9 2026-11-09 No demo ticket (tour + accept scripts); I-Q5 default as built (orch, TL92 r2)
D10 2026-11-09 Route action is activity.read, closed to agents (S1 dev 1); accepted with merge
D11 2026-11-09 T02 split (checklist item 4): T02 widget, T02b wiring. Tabs load by plain call like ThreadTab (no worker)
D12 2026-11-09 Stub record_activity_text.py committed on p2/ins (frozen signatures) so T01 and T02 run in one workflow; T02 tests never pin its wording
D13 2026-11-09 T04 cut to core twin tests (route walks, read-only, statement count already in S1/S2); no dependency on T01-T03
## SEC     F<n> <HI|MD|LO> <fixed@sha|open> <one line>
S-A sec review mrg (S1), S-B/S-C sec review mrg (S2): no open findings.
F-S1-1 LO open DEFERRED: related rows miss Constraint.Cleared and Proposal.Accepted of far records (coverage); roadmap item 1; named under T04 not covered
## OPEN    Q<n> <question> needs <orch|owner|builder> raised <id>
Q4 After wave 2 merge: rebase p2/ins onto trunk or keep base; wave 2 fixes may touch constraints/readiness views needs orch raised r1
Q5 S2: constraint findings skip core.constraint.view access word; route is record.read as specified; confirm intended needs orch raised r2
Q6 telemetry_need not in dev MCP sqlguard blocklist (tl_mcp/dev/sqlguard.py); ids and words only; add or waive needs orch raised r2
## NEXT
1. Orch: dispatch T01 + T02 in one workflow (batch of 2, disjoint paths; stub already in tree). Gates: T01 just gate its test file; T02 its test file.
2. Next round (r3): after T01 and T02 merge, dispatch T02b + T04 (disjoint; T04 may go earlier in any free slot).
3. r4: T03 after T02b merged. Paste check: T03 edits one record_view compose line.
4. DONE: whole gate by package (never all of tl-schema/tests in one session: OOM; split by file), gate-pg on touched dirs, security review S-A..S-C already done, tour rows, report (<= 80 lines).
## REFS
Plan `docs/tickets/P2-INS/README.md`; reports `docs/reports/P2-INS/S1.md S2.md`; tickets T01 T02 T02b T03 T04; stub `packages/tl-tui/src/tl_tui/record_activity_text.py`; worlds `dev/accept/P2-INS/s1_world.py`, `packages/tl-core/tests/insights/test_checks.py` (seed_world). Spec `docs/build-spec/specs/insights-and-activity.md`.
## TRAPS
Docs round: just check/gates not run (stub checked with ruff only). `test_client_conformance.py` does not exist: gates name `tests/api/test_client_roundtrip.py`, `test_fakes.py`, `test_remote_client.py` instead; a missing path makes pytest exit 4. Confidentiality-walk seed fails on Postgres (AttachFile word): walks SQLite only. Max 2 heavy pytest runs. Never pkill -f; never delete /tmp/pytest-of-root.
