# P2-I5 STATE  r=2 base=ec3314d C=0 ck=0 gate=n/a wt=/home/user/wt/p2-i5
## BOARD   (pieces S, tickets T; nothing dispatched until P2-INT C2 is on the trunk and merged into p2/i5)
S1 p mrg f 76c15b4 schema, package content, words, settings; spec r2; gate orch P2-Q10
S2 p disp f - engine, progress cmds, IWP start/complete, math rules; spec r2; needs S1
S3 p todo f - rollup + CSV export; spec at C1; pairs S4 A
S4 p todo f - A weekly cmds (human gate); B waive word on clear + hold rule + worker word; spec at C1
S5 p todo f - closeout, hours and subcontract CSV readers; spec at C1; pairs S4 B
S6 p todo f - tests piece at C3
T01 t todo f - tl awp roc ls|show|set; needs S1
T03 t todo f - look_ahead_view; needs S2 S4A
T04 t todo f - look-ahead and week CLI
T05 t todo f - interface-constraint helper; needs S5
T06a t todo f - TUI cycle steps 1-3; needs T11b
T06b t todo f - TUI cycle steps 4-6
T06c1 t todo f - IWP log mine/counts/state-since
T06c2 t todo f - tui.landing at sign-in
T07a t todo f - pack HTML + segno QR svg
T07b t todo l - pack template
T07c t todo f - pack PDF behind flag
T08 t todo f - closeout reads, routes, CLI
T09 t todo l - seven KPIs + recount test
T10 t todo f - subcontract reads, routes, CLI
T11a1 t todo f - API routes S2/S3 models
T11a2 t todo f - API routes weekly + look-ahead
T11b t todo f - client methods + fakes
T11c t todo f - MCP reads + two proposable rows
T12 t todo f - demo, ten clauses
T13 t todo l - docs, three runbooks
T15 t todo f - registrations only if glue > 50 lines
## DEC
D1 2026-11-08 plan is 6 pieces + 21 tickets; PLANCHK F1-F12 all accepted; answers in README
D2 2026-11-08 CLI and TUI only; web pages for cycle, look-ahead, progress, pack, closeout, landing go to the web increment row at close
D3 2026-11-08 F3 rules of credit are schemareg package content (section rules_of_credit in co.acme.awp@1.1.0); no record class, no loader; setting holds package@version
D4 2026-11-08 P2-Q11: HTML always; QR as segno SVG inline; PDF is T07c; flag awp.pack.pdf default off; optional extra pack; no api.public_base_url (F12)
D5 2026-11-08 P2-Q13 A: CWP assigned_party free text; Interface constraint type; CSV progress; no accounts
D6 2026-11-08 F2: no WaiveConstraint, no new event; clearing a check-raised constraint needs core.constraint.waive (controller) and a reason (cap 300), shown as waived; core handler change is S4 B, gated
D7 2026-11-08 F1 INTERPRETATION OF W3-6 (owner to be told): no foreman account role; user-scope setting tui.landing; unset resolves to iwp_mine for a person who is foreman on any IWP at sign-in; no auth change
D8 2026-11-08 W3-7: awp.iwp.ready_lead_weeks exists, default 4; no change
D9 2026-11-08 F10 hold-on-new-constraint rule (P2-I2 Q1): follower worker, Issued only, state re-checked on apply, idempotent on replay, by_module; tl awp worker access word folded in; S4 B
D10 2026-11-08 ADR-0027: I4-A S2 owns proposable_exclusions.toml, its test and baseline; I5 appends only (F5); approvals, verify, closes, waived clears excluded
D11 2026-11-08 ADR-0026 F5: three at fields tagged tl:valid_time; P2-INT C2 first, no untagged fallback (F4)
D12 2026-11-08 F9 math: stored progress unfiltered, filtered on read; null est_hours weighs the mean of the others; Decimal, round once, largest-remainder split; PPC by count; burned from cost snapshot read-only (S2)
D13 2026-11-08 F7 pairs: S3 with S4 A, S5 with S4 B; at most one builder + one ticket workflow per round
D14 2026-11-08 F8: look_ahead_view T03 and interface helper T05 are tickets; T11a and T06c split in two; closeout and subcontract routes live in T08, T10; T14 sim actor deferred to I6 (F12)
D15 2026-11-08 F11: S4 human gate + APPROVALS, S5 APPROVALS; S1 gate runs uv sync --extra pack before the licence check; one SR3 range ec3314d..head
D16 2026-11-08 deferred, not folded: WBS node workflow/opt-in, automatic constraint population, materials screen gaps; folded: hold rule, IWP log follow-ups, awp worker word
## SEC   (SR3 I5 rows in README)
(none yet)
## OPEN
Q1 When is P2-INT C2 on the trunk? S1 is held until then; merge the trunk into p2/i5 first needs orch raised r2
Q2 Does the package content model accept a new section without a core change? S1 checks and escalates needs builder raised r2
D-o1 2026-11-09 owner: reorder accepted; I5 trimmed now (S1-S4, look-ahead, mine log and landing, HTML pack); deferred to roadmap item 3c: T07c PDF pack, S5 closeout and subcontract CSV (T08, T10, T05), five of seven KPI tiles
## NEXT
1. Orchestrator: after P2-INT C2, merge the trunk into p2/i5, send `13.`; round 3 dispatches S1 alone.
2. After S1: S2 (alone, owns module.py); T01 spec beside it.
3. At C1 (S1, S2 merged) write S3, S4, S5 specs; rounds pair S3 with S4 A, then S5 with S4 B.
4. T03, T11a1 after S2/S3/S4 A; then T11a2, T11b; screens, CLI, pack after.
5. At C2 registrations (<= 50 lines) else T15; pinned lists as union after I4-A merges.
6. At close add the web-pages line to DEFERRED.md and the I6 actor line (not now).
## REFS
Plan `docs/build-spec/08-phase2-plan.md` Increment 5; design `module-designs/field-work-packaging.md`; format `docs/tickets/P2-I2/`; parallel `p2/i4a:docs/tickets/P2-I4A/README.md`.
Patterns: rollup `tl_mod_awp/rollup.py`; readiness `readiness/views.py` (`visible_readiness`); look-ahead `tl_mod_schedule/lookahead.py`; envelope `tl_core/derivation/envelope.py`; constraints `tl_core/constraints/`; packages `tl_schema/packages.py`, `lint.py`; file slots `schema/fixtures/files/`.
## TRAPS
Gates name test files or one package (OOM on 16 GB); never pkill -f; never delete /tmp/pytest-of-root; pinned lists as union; a check name used twice is an error; tests dialect-neutral (no group_concat).
