# P2-I5 STATE  r=4 base=ec3314d C=1 ck=0 gate=n/a wt=/home/user/wt/p2-i5
## BOARD   (C1 reached: S1 mrg@76c15b4, S2 mrg@00647bf; reports docs/reports/P2-I5/S1.md, S2.md)
S1 p mrg f 76c15b4 schema, package content, words, settings
S2 p mrg f 00647bf engine, progress cmds, IWP start/complete, math rules
S3 p mrg f 3eafc70 rollup+CSV export on read; after S4a merges (F4, F6); pins named (F10)
S4a p mrg f 011349c weekly cmds, week reads, propose_week_commitment; building; orch APPROVALS only
S4b p mrg f 450b814 waive word, hold rule, worker word; READY r4 (F1 F2 F11 applied); human gate, owner approver
S5 p abn f - roadmap 3c (closeout, subcontract CSV)
S6 p abn f - replaced by T16 (Haiku five-reader walk)
T01 t mrg f 7c094c8 tl awp roc ls|show|set; READY r4; provided/T01_test_awp_roc.py
T03 t mrg f 998797d look_ahead_view; READY r4 (stub in tree); provided/T03_test_look_ahead_view.py
T04 t stg f - look-ahead + week open|ls|show|commit|outcome|close|ppc|reasons CLI; needs S4a T03; test after S4a
T04b t todo f - CLI for S2 writes (start-work, complete-field, item-move, step, progress); READY after T01 merges
T06a t todo f - TUI cycle steps 1-3; needs T11b S4b
T06b t todo f - TUI cycle steps 4-5 + actions.RULES rows StartIwpWork, CompleteIwpField (Q-o2)
T06c1 t todo f - IWP log mine/counts/state-since; needs T11b
T06c2 t todo f - tui.landing at sign-in; needs T06c1
T07a t todo f - pack HTML + segno QR svg; needs T11b
T07b t todo l - pack template; provided test written when T07a merges
T07c t abn f - roadmap 3c (PDF)
T08 t abn f - roadmap 3c
T09 t todo l - two KPI tiles (PPC, % constraint-free); needs S4a only; test written when S4a merges
T10 t abn f - roadmap 3c
T11a1 t todo f - API routes S2/S3 models; needs S3
T11a2 t todo f - API routes weekly + look-ahead; needs S4a T03
T11b t todo f - client methods + fakes; needs T11a1 T11a2 S4b
T11c t todo f - MCP reads; rows already in S2 and S4a
T12 t todo f - demo clauses 1-6,9,10; needs S4b
T13 t todo l - docs, three runbooks
T15 t todo f - registrations only if glue > 50 lines
T16 t todo f - five-reader walk of every new route and tool; after T11c, S4b
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
D17 2026-11-09 r3: S3 computes the progress rollup on read (reuses rollup.compute with earned hours as budgets); no stored figure, no new event, no human gate; demo clause 5 'rollup job writes' read as 'rollup reads'
D18 2026-11-09 r3: waived is derived (Cleared, source check, suppress_hash kept); no new payload key or column; S4b adds `waived` to the constraint read row only
D19 2026-11-09 r3: propose_week_commitment row lives in S4a (ADR-0027 per piece); T11c writes MCP reads only; OpenWeeklyPlan, RecordWeekOutcome, CloseWeek are exclusions
D20 2026-11-09 r3: S3 and S4a share a round (disjoint paths); S4b is independent, run when a slot is free (3 heavy max incl. supervisor)
D21 2026-11-09 r3: remaining plan is 17 tickets (> 10): PLANCHK asked for the trimmed ticket set; pieces S3, S4a, S4b are inside the checked plan and may dispatch
D22 2026-11-09 r4: PLANCHK of the trimmed set (F1-F12) all applied: S4b spec (F1 signoff.py:207, F2 openapi+test_auth_review pins, F11 require_word at constraint_read.py:52), T04 gains `week open`, T04b new (F3), S6 -> T16 (F8), S3 pins named (F10), README strikes (F7)
D23 2026-11-09 r4 GATE ROWS (F9): S4a = orchestrator APPROVALS only (new access-worded commands, no schema). S4b = human gate, owner approver (core constraint handler, words core.constraint.waive and awp.worker.run) plus orchestrator APPROVALS. S1 and S2 done earlier. SR3 Sec list (one range ec3314d..head): S1 package lint/settings/dependency; S2 arithmetic and viewer filter; S3 CSV export; S4a week words and stale writes; S4b waive word, hold rule, worker word; T07a template; T11a1/T11a2 routes and the five-reader walk; T11c agent tools. S5 dropped.
D24 2026-11-09 r4: T01, T03, T04b are Haiku tickets over existing S1/S2 code; T03 has a stub (`look_ahead_view.py`, NotImplementedError) so its provided test compiles (pyright clean); T04 has no provided test until S4a is merged (names are in the S4a spec)
D25 2026-11-09 r4: T09 depends on S4a only (PPC by count, % constraint-free from readiness/constraints; S3 not needed); T03 does not depend on S4a (F5)
## SEC   (SR3 I5 rows in README)
(none yet)
## OPEN
Q1 closed r3 (trunk merged, S1 merged); Q2 closed r3 (S1 shipped the section; package-form file path schema/fixtures/packages/ pending orch confirm, S1 dev 1, S2 dev 3)
Q3 PLANCHK of the trimmed 17-ticket set needs orch raised r3
Q4 core feed policy list lacks the eight new feed_policy none events (S1 dev 6) needs orch raised r3
D-o1 2026-11-09 owner: reorder accepted; I5 trimmed now (S1-S4, look-ahead, mine log and landing, HTML pack); deferred to roadmap item 3c: T07c PDF pack, S5 closeout and subcontract CSV (T08, T10, T05), five of seven KPI tiles
Q-o1 at merge with p2/i4a or the trunk: add the four proposable-exclusion lines listed in docs/reports/P2-I5/S2.md to tests/tools/proposable_exclusions.toml
Q-o2 actions.RULES lacks StartIwpWork and CompleteIwpField: assigned to T06b r4
Q-o3 feed cards: tl_core.feed.cards.POLICY_EVENT_TYPES lacks the WeeklyPlan.* and IWP.* quiet events (S1 dev 6, S4a F1); core ticket
## NEXT
1. Orchestrator now: dispatch workflow [T01, T03] and builder S4b (S4a is running: 3 heavy slots). T04b after T01 merges (both edit awp.py by one line).
2. After S4a merges: dispatch S3; write the T04 provided test, the T09 provided test and T11a2 (S4a, T03 in the tree); T11a1 after S3.
3. After T11a1, T11a2 merged and S4b merged: T11b, then T06a, T06c1, T07a, T09, T11c in batches of 2-3; T06b, T06c2, T07b after (T07b test when T07a merges).
4. T06b carries the actions.RULES rows (Q-o2). T16 after T11c; T12 last with T13.
5. At C2 registrations (<= 50 lines) else T15; pinned lists as union; add the four S2 exclusion lines and the S4a/S4b lines at the I4-A merge (Q-o1).
6. At close add the web-pages line and the roadmap-3c line (S5, T05, T07c, T08, T10, five KPI tiles, clauses 7-8) to DEFERRED.md; I6 actor line.
## REFS
Provided tests `docs/tickets/P2-I5/provided/` (T01, T03, T04b; copy byte-identical to the ticket's test path). Stub `tl_mod_awp/look_ahead_view.py`. Plan `docs/build-spec/08-phase2-plan.md` Increment 5; design `module-designs/field-work-packaging.md`; format `docs/tickets/P2-I2/`; parallel `p2/i4a:docs/tickets/P2-I4A/README.md`.
Patterns: rollup `tl_mod_awp/rollup.py`; readiness `readiness/views.py` (`visible_readiness`); look-ahead `tl_mod_schedule/lookahead.py`; envelope `tl_core/derivation/envelope.py`; constraints `tl_core/constraints/`; packages `tl_schema/packages.py`, `lint.py`; file slots `schema/fixtures/files/`.
## TRAPS
uv sync --frozen --all-packages was needed in a fresh worktree before pyright resolved imports. Gates name test files or one package (OOM on 16 GB); never pkill -f; never delete /tmp/pytest-of-root; pinned lists as union; a check name used twice is an error; tests dialect-neutral (no group_concat).
