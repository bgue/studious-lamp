# P0-I6-T41 — Planner actor

Status: ready
Tier: haiku
Labels: tests
Depends on: — (the base `p0/i6c` already has the actor base, `tl_sim.testing` and the stub)
Branch: `p0/i6c-t41-planner`

## Goal
The planner actor exists: each simulated working day it approves documents waiting in review, plans installation activities on piping lines (linked to the line and to an approved document), and on the configured weekday posts a look-ahead that names the first activities and holds on documents still waiting. The stub has the class and docstring; `act` raises `NotImplementedError`. A provided test file (12 tests) must pass.

## Brief references (pasted)
> **29.5** A simulator generates realistic project activity by acting through the suite's public MCP server and API, as if it were a project team. Deterministic actors do the bulk mechanics; roles include the document controller (registers revisions, transmittals), the planner (clears constraints) and the welding foreman / crew (records, photos, feed posts). Time compression: `sim_advance(days=...)` runs a working day in seconds. Determinism: seeded randomness, so a scenario replays identically.
> **29.1** Dogfood the open interfaces: the simulator uses only the public API and MCP.
> FANOUT D6: simulator v0 is fully deterministic and makes no LLM calls.

### Specification
`act` is the whole ticket. The module docstring of the stub is the specification (it is also the final docstring; keep it). Titles, link relations, transition names and post texts are checked character by character by the provided test.

The approve guard of the sample workflow needs an outgoing `references` link; when the suite refuses a transition `rec.transition(...)` returns `False` and the document simply waits.

**Imports to add:** `from tl_sim.actors.base import Rec`; `from tl_sim.clock import WEEKDAYS` (weekday names, Monday first); `from tl_sim.scenario import draw`.

`ctx.now.weekday()` is 0 for Monday; `WEEKDAYS[ctx.now.weekday()]` is the name (`"mon"`) to compare with `params.lookahead_day`.

Learnings that apply:
- pyright is `standard` for `packages/tl-sim`; ruff limits lines to 100 columns (docstrings and comments too). Run `uv run ruff format packages/tl-sim` and `uv run ruff check packages/tl-sim` before committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- Provided tests live under `docs/tickets/P0-I6/provided/*.py.txt`; copy them into the test tree byte for byte (`cp`). Do not edit the copy.
- Commit your report at `docs/reports/P0-I6/P0-I6-T41.md` (it is inside your Allowed paths).
- A fresh worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages. Always work from your worktree root and use `uv run`; never run Python from inside `packages/tl-sim/src/tl_sim`, where `types.py` would shadow the standard library.
- No new dependencies. ruff's autofix removed the unused imports of the stub; add the ones listed as *Imports to add*.
- `just test` is known red in `tests/api/test_client_roundtrip.py` (another workstream adds the feed methods to `ApiClient`). Any other failure is yours. Your acceptance is `uv run pytest packages/tl-sim -q` plus `just check`.
- The random generator is the point: draw from `ctx.rng` in exactly the order the specification lists, and never use `random`, `time`, `datetime.now`, `uuid` or set iteration order for a decision. The provided test pins the first draws for one seed, so a different order fails it.
- Write only through `rec` (the `Recorder`): it makes the call and writes the ground truth. Never call `ctx.client` for a write, and never import `tl_core.services` handlers, `tl_adapters` or `sqlalchemy` (the boundary test forbids it).

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-sim/src/tl_sim/types.py (frozen contract, do not edit)
@dataclass(frozen=True)
class SimContext:
    run_id: str; scope: str
    now: datetime            # simulated time (UTC)
    rng: Random              # seeded per (run seed, actor name, day): the ONLY source of randomness
    client: SimClient

# packages/tl-sim/src/tl_sim/actors/base.py (existing, final; do not edit)
@dataclass(frozen=True)
class Rec:
    id: str; key: str; title: str; status: str | None = None
    @property
    def state(self) -> str: ...            # status, or "Draft" when empty
class Recorder:
    ctx: SimContext; identity: str; truth: list[GroundTruth]
    def records(self, q: str = "", *, title_prefix: str | None = None) -> list[Rec]: ...   # key order; q is the query language ("status:Review")
    def create(self, title: str) -> Rec: ...                                  # record.created
    def set_psets(self, rec: Rec, values: dict[str, dict[str, Any]]) -> None: ...  # pset.set per property
    def link(self, source: Rec, target: Rec, relation: str) -> None: ...      # link.added
    def transition(self, rec: Rec, transition: str, to_state: str) -> bool: ...  # False when the suite refuses; records nothing then
    def post(self, body: str) -> str: ...                                     # post.created
class BaseActor:
    name: str = ""; params: Any; identity: str   # "agent:sim-<name>"
    def step(self, ctx: SimContext) -> list[GroundTruth]: ...                  # builds a Recorder, calls act, returns rec.truth
    def act(self, ctx: SimContext, rec: Recorder) -> None: ...                 # YOU implement this
```

```python
# packages/tl-sim/src/tl_sim/scenario.py (existing, final)
class PlannerParams(Strict):
    """Looks at documents in review, approves them, plans activities and writes the look-ahead."""

    approvals_per_day: Count = 2
    activities_per_day: Count = CountRange(min=0, max=2)
    lookahead_day: Weekday | None = "mon"  # the weekday of the look-ahead post; null is never

def draw(count: Count, rng: Random) -> int:
    """One draw from ``count`` using ``rng``. Never negative."""
    if isinstance(count, bool):
        raise TypeError("a count is a number, not a bool")
    if isinstance(count, int):
        return max(0, count)
    if isinstance(count, CountRange):
        return rng.randint(count.min, count.max)
    return max(0, round(rng.gauss(count.mean, count.sd)))
```

```python
# packages/tl-sim/src/tl_sim/actors/planner.py (existing stub; keep the constants and the class header)
"""The planner: approves documents in review, plans activities, writes the weekly look-ahead.

One working day (``act``), in this order, drawing from ``ctx.rng`` only where stated:

1. Read the documents in review: records with ``status:Review`` whose title starts ``Doc ``, in key
   order. Draw ``k = draw(params.approvals_per_day, ctx.rng)``. For the first ``k`` of them run
   ``approve`` (``Approved`` expected). The suite may refuse (the guard needs a ``references``
   link), which ``Recorder.transition`` reports as ``False``; a refused document stays waiting.
2. Draw ``m = draw(params.activities_per_day, ctx.rng)``. Read the lines (title starts ``Line ``);
   with no lines, plan nothing. For each of the ``m`` activities draw ``ctx.rng.choice(lines)``,
   create ``Activity <serial:03d> Install spools on <designation>`` (``serial`` is the number of
   existing activities plus one for each created so far; ``designation`` is the line title
   without ``Line ``), and link it ``belongs_to`` the line. Then read the approved documents
   (``status:Approved``, title starts ``Doc ``); if there are any, draw ``ctx.rng.choice`` of them
   (key order) and link the activity ``requires`` that document.
3. If ``params.lookahead_day`` is set and ``ctx.now`` falls on that weekday, post
   ``Look-ahead: <a> activities planned, <w> documents waiting for approval.`` where ``a`` is the
   number of activities this step created and ``w`` the number still in review after step 1. For
   each of the first three activities created add `` #<key>``; when ``w`` is above 0 append
   `` #hold`` and `` #<key>`` of the first document still waiting.
"""

from __future__ import annotations

from tl_sim.actors.base import BaseActor, Recorder
from tl_sim.scenario import PlannerParams
from tl_sim.types import SimContext


class Planner(BaseActor):
    name = "planner"
    params: PlannerParams

    def act(self, ctx: SimContext, rec: Recorder) -> None:
        raise NotImplementedError("STUB (P0-I6-T41)")
```


## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-sim/src/tl_sim/actors/planner.py`
- `packages/tl-sim/src/tl_sim/actors/base.py`
- `packages/tl-sim/src/tl_sim/testing.py` (the in-memory world the tests use; read `FakeClient`)
- `docs/tickets/P0-I6/provided/c-test_actor_planner.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-sim/src/tl_sim/actors/planner.py` (edit)
- `packages/tl-sim/tests/test_actor_planner.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I6/P0-I6-T41.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I6/provided/c-test_actor_planner.py.txt packages/tl-sim/tests/test_actor_planner.py`
2. Implement `act` and its helpers, add the imports, keep the docstring.
3. Run the acceptance commands, write the report, commit both.

## Acceptance
```
uv run pytest packages/tl-sim -q
just check
```
Expected: 12 tests pass in the new file and the whole `packages/tl-sim` run stays green; `just check` clean.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`). Paste the look-ahead post text from a run with waiting documents.

## Escalation triggers
- Stop and report *Blocked* if a pasted signature disagrees with the repo, or if the provided test cannot pass without changing a file outside *Allowed paths*.
- Stop after two attempts at the same failing test.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
