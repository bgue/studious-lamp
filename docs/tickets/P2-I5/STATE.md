# P2-I5 STATE  r=6 base=bcf3c2e C=1 ck=0 gate=n/a wt=/home/user/wt/p2-i5
## BOARD   (merged: S1 S2 S3 S4a S4b T01 T03 T04b; reports docs/reports/P2-I5/<id>.md; tickets written r5: ready or staged by need)
S1 p mrg f 76c15b4 schema, package content, words, settings
S2 p mrg f 00647bf engine, progress cmds, IWP start/complete, math rules
S3 p mrg f 3eafc70 rollup+CSV export on read
S4a p mrg f 011349c weekly cmds, week reads, propose_week_commitment
S4b p mrg f 450b814 waive word, hold rule, worker word; human gate done
T01 t mrg f 7c094c8 tl awp roc ls|show|set
T03 t mrg f 998797d look_ahead_view
T04b t mrg f 02a926d CLI for S2 writes
T09 t mrg l b1666b8 KPI tiles; fix round (provided test had wrong-case miss key, IWP state by shortcut)
T07a t mrg f bcf3c2e pack HTML + QR + `iwp pack`; build_pack_data, render_html -> Rendered
T04 t todo f - look-ahead + week CLI; ready after T09; provided test in tree (R-B)
T11a1 t todo f - API progress/rollup/kpis/counts/hash routes; after T09 (R-B)
T11c t todo f - MCP five reads; after T09 (R-B)
T11a2 t todo f - API weeks/miss-reasons/look-ahead; after T11a1 (R-C)
T07b t stg l - pack template; ready; provided test r6; golden made by the ticket (R-C)
T11b t todo f - client methods + fakes + two command doors; after T11a1 T11a2 (R-D)
T06a t todo f - TUI cycle steps 1-3; after T11b; stub weekly_text.py + provided test in tree (R-E)
T16 t todo f - five-reader walk, three test files; after T11c T11b T04 (R-E)
T06b t todo f - TUI steps 4-5 + actions.RULES rows StartIwpWork, CompleteIwpField; after T06a (R-F)
T06c1 t todo f - IWP log counts, filters, backlog 500, mine flag; after T11b (R-F)
T06c2 t todo f - landing at sign-in; after T06c1 T06b (R-G)
T12 t todo f - demo clauses 1-6, 9, 10; after T06c2 T06b T07b T09 T16 (R-H)
T13 t todo l - docs, three runbooks; after T12 (R-I)
T17 t todo f - tour steps (Activity, Insights, intent, weekly loop, pack); after T12 (R-I)
T15 t todo f - registrations only if glue > 50 lines
S5 S6 T05 T07c T08 T10 abn - roadmap 3c, or replaced (T16)
## DEC     (D1-D25 in git history of this file at b9a8e6d; kept: D7 landing is a setting, D17 rollup on read, D18 waived derived, D19 exclusions, D23 gate rows)
D26 2026-11-09 r5 pack without Jinja2: not a dependency of tl-mod-awp; string.Template + one html.escape helper; README said Jinja2 (owner to be told in the report)
D27 2026-11-09 r5 `week ppc` = PPC tile = pooled done/committed over the last 4 Closed plans (T09), one definition
D28 2026-11-09 r5 TUI writes go through two client doors, awp_command and constraint_command (T11b); nothing like them existed
D29 2026-11-09 r5 look-ahead is not an MCP tool this increment (needs a schedule snapshot); five MCP reads only
D30 2026-11-09 r5 route and client read for the IWP record hash (T11a1, T11b) so the remote release step can sign off and issue; no new word; SR3 row added
D31 2026-11-09 r5 web IWP page keeps IWP_COLUMNS; the TUI log gets IWP_COUNT_COLUMNS (T06c1); no web change
D32 2026-11-09 r5 waves R-A..R-I in README; one workflow of 2-3 tickets with disjoint files per round; no builder left; shared one-line files (awp.py, app.py, openapi.json) are touched by one ticket per wave
## SEC     (SR3 I5 rows in README; range ec3314d..head; none run yet)
(none yet)
## OPEN
Q2 package-form file path schema/fixtures/packages/co.acme.awp@1.1.0.yaml (S1 dev 1) needs orch confirm raised r3; T12 clause 1 uses it
Q4 core feed policy list lacks the eight new quiet events (S1 dev 6) and POLICY_EVENT_TYPES lacks WeeklyPlan.* and IWP.* (Q-o3) needs orch raised r3
Q5 awp.worker.run is company scope (S4b): project controllers cannot run the worker; per project? needs owner raised r4
Q-o1 at merge with p2/i4a or the trunk: add the four S2 exclusion lines (S2 report) and the three S4a lines (OpenWeeklyPlan, RecordWeekOutcome, CloseWeek) to tests/tools/proposable_exclusions.toml
Q6 platform.yaml tui.landing docs say default lands "on their packages"; D7 makes unset resolve to iwp_mine and explicit default land as before: T06c2 does that; fix the description text at close (schema/settings/platform.yaml is S1's) needs orch raised r5
## NEXT
1. After T09 fix merges: R-B [T11a1, T04, T11c]. T04 test r6: look-ahead Plant now evaluates readiness through evaluate_now (no cur_* inserts); T06a miss key is `Weather` (edition code).
2. R-C [T11a2, T07b] may go now for T07b (needs only T07a).
3. R-C [T11a2, T07b]; R-D [T11b]; R-E [T06a, T16]; R-F [T06b, T06c1]; R-G [T06c2]; R-H [T12]; R-I [T13, T17]. After each merge: `just gen` last, openapi.json and pinned lists as union.
4. Between waves a supervisor reads the reports of the merged tickets and re-specs a ticket whose named interface moved (never edits code).
5. T12 and T16 run the two adapters; SR3 range ec3314d..head runs at C4 with the full gate, gate-pg on touched dirs and the demo; T17 after the demo.
6. At close: DEFERRED lines (web pages for cycle, look-ahead, progress, pack, closeout, landing; roadmap 3c: S5 T05 T07c T08 T10, five KPI tiles, clauses 7-8; I6 foreman actor); tell the owner D7 and D26.
## REFS
Provided tests `docs/tickets/P2-I5/provided/`: T01 T03 T04b (merged), T04_test_awp_week.py, T06a_test_weekly_text.py, T07b_test_pack_template.py (r6; hand-built PackData, golden is the no-segno form), T09_test_kpis.py (copy byte-identical to the ticket's test path). Stubs in tree: `tl_mod_awp/kpis.py` (T09), `tl_tui/weekly_text.py` (T06a). Tickets: docs/tickets/P2-I5/T*.md. Models: P2-I2 T04c1, T04c2, T09b. Provided tests were checked with ruff and pyright only (no suite run): a failure that the ticket does not explain goes under Blocked, the supervisor corrects the test copy.
## TRAPS
r6: provided tests run once against temp copies (T07b, T04, T06a): they fail only where the ticket's work is missing; copies deleted. Miss-reason codes are capitalised (Weather). Never write cur_* rows in a provided test.
uv sync --frozen --all-packages before pyright in a fresh worktree; pyright resolves `awp_world`/`progress_world` only from the awp tests dir (copy the file there to check, then remove); gates name test files or one package (OOM on 16 GB); never pkill -f; never delete /tmp/pytest-of-root; pinned lists as union; tests dialect-neutral; slow gate step: tl-api test_commands + mcp write tools took 370 s (S4a), use a long timeout or background.
