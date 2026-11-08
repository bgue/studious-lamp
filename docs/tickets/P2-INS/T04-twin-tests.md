# P2-INS-T04 — Twin tests of Activity and Checks (INS-A4 + INS-B5, reduced by plan check F8)

Status: ready (round 2, against merged S1 and S2 @2fbcdcf; independent of T01 to T03, so it may go in any batch)
Tier: haiku
review: full
Labels: tests
Depends on: S1, S2 merged (yes). The five-reader route walks, the statement count and the read-only checks are already in S1 and S2 (`test_activity_walk.py`, `test_checks_walk.py`, `test_note_need_walk.py`); this ticket adds core-level twin tests only
Branch: `p2/ins-t04-twin-tests`
Worktree: `/home/user/wt/ins-t04`

## Goal
Twin tests prove that a hidden record leaves no trace in what a viewer reads: a record linked to a hidden record reads exactly like its twin with no such link (Activity), and a finding that would name a hidden record reads exactly like one that names an id that names nothing (Checks). Tests only; no source change. A failing twin is reported as a finding (`F<n> HI file:line`), never fixed here.

## Brief references (pasted; spec C3)
- Activity twin A: world A = `sw.build(root_a)` plus `sw.add_hidden(world_a)` (a restricted record linked both ways to the IWP, with a causal event of its own); world B = `sw.build(root_b)` only. For the lowest-clearance viewer, `record_activity(uow, world.iwp, ...)` gives the same page for A and B after normalising each row to `(kind, event.event_type, event.actor, related, from_key, decided_by, note)` (seqs and ids differ between two worlds). Compare the full list, the row count, and a paged read with `limit=5` (same list of page lengths, and `next_before_seq is None` on the same pages). Also `related=False`.
- Activity twin B (viewer who can read the hidden record): a controller (`cf.Viewer("user:controller", 1, "user:controller")`) sees more in A than in B: assert A has at least one extra row (the restricted record's link row or its related row) and that B equals the lowest-clearance read of B. This pins that the twin passes because of the filter, not because the world is empty.
- Checks twin: from `seed_world(conn)` of `test_checks.py`: world X as seeded (the readiness check names a hidden record in `resolve_via`; the constraint's subject can be re-pointed); world Y = the same seed with the hidden id replaced by a fresh `new_ulid()` that names nothing (`UPDATE cur_awp_readiness_check SET resolve_via_json = ...`, and for the constraint `UPDATE cur_core_constraint SET subject_id = :nothing`). `record_checks(conn, facts, SOURCES, USER)` equals the same read in Y as full `model_dump()` lists, for the readiness finding and for the constraint case (X: a constraint on the hidden record is no finding; Y: on an unknown id, no finding).
- Intent: nothing to test until the ADR-0025 slice lands (no `why` on the base). Write no skipped test (AGENTS.md); list it under "not covered".
- Not covered (say so in the report): related rows miss `Constraint.Cleared` and `Proposal.Accepted` of far records (follow-up F-S1-1, roadmap; the twin cannot see what the read never shows); a twin with a proposal that names a hidden record in its stored command (no helper builds one; S1's walk covers the page of the plain proposals).
- The scan cap: both worlds hold far fewer than 1000 candidate events, so the cap of S1 is never reached.

## Interfaces (verbatim at @2fbcdcf)
```python
# tl_core.insights.activity
def record_activity(uow: UnitOfWork, record_id: str, *, revisions_only: bool = False, related: bool = True,
                    before_seq: int | None = None, limit: int = 120) -> ActivityPage
# the viewer is the ambient one: `with open_uow(world.w.db, readonly=True) as uow, cf.use_viewer(viewer):`  (cf = tl_core.confidentiality; cf.LOWEST is the lowest clearance)
# dev/accept/P2-INS/s1_world.py (import it as test_activity.py does: sys.path.insert(0, ACCEPT); import s1_world as sw)
def build(root: Path, target: Any = None) -> World      # World(w, iwp, ids); one IWP with edits, links, post, constraint, readiness; a far IWP
def add_hidden(world: World) -> str                     # restricted record that blocks and is targeted by the IWP, with its own event
# tl_core.insights.checks
def record_checks(conn, facts: RecordFacts, sources, viewer) -> list[CheckFinding]
def record_facts(conn, record_id: str, viewer) -> RecordFacts | None
# packages/tl-core/tests/insights/test_checks.py: SOURCES, USER, HIDDEN_LINE, seed_world(conn) -> dict[str, str] (keys iwp, doc, hidden, constraint, corr, line), `world(db)` context manager, the root `conftest.py` `db` fixture (sqlite and postgres)
```

## Context (<= 6 files)
`packages/tl-core/tests/insights/test_activity.py` (world fixture, `read`, imports); `packages/tl-core/tests/insights/test_checks.py` (`seed_world`, `world`, the hidden tests at lines 170-205); `dev/accept/P2-INS/s1_world.py`; the repository `conftest.py` (the `db` fixture, sqlite and postgres; tests take `db: Any`).
may explore: `packages/tl-core/src/tl_core/insights/activity.py` (read only).

## Allowed paths
- `packages/tl-core/tests/insights/test_activity_twin.py`, `test_checks_twin.py` (create)
- `docs/reports/P2-INS/T04.md` (create)
Not allowed: any `src/` file, `confidentiality.py`, existing tests, `s1_world.py`, `test_checks.py` (import from them, never edit).

## Acceptance
```
just check
just gate packages/tl-core/tests/insights/test_activity_twin.py packages/tl-core/tests/insights/test_checks_twin.py
just gate-pg packages/tl-core/tests/insights/test_checks_twin.py
```
The activity twin is SQLite only (`sw.build` is SQLite by default; S1's parity test covers Postgres).

## Tests to add
One function per twin pair, each asserting equality of the full normalised result (not a count only); one deliberate break per pair run once by the author by hand (for example drop the `hidden_ok` filter in a scratch copy, or print the hidden key in `HIDDEN_LINE`), reported in one line and reverted, never committed.

## Report requirements
`docs/templates/haiku-report.md`, <= 60 lines; deviations first; the "not covered" lines; output of the three commands (<= 5 lines each).

## Commit
`P2-INS-T04: <imperative summary>`; trailer lines as `docs/build-spec/SUPERVISOR-PROMPT.md`; no model names. Do not merge; do not push.

## Escalation triggers
- Stop and report *Blocked* if a twin differs (a finding to escalate, not to fix); a fixture needs a source change; a world grows past 1000 candidate events.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
