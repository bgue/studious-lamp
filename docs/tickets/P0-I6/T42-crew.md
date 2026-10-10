# P0-I6-T42 — Crew actor

Status: ready
Tier: haiku
Labels: tests
Depends on: — (the base `p0/i6c` already has the actor base, `tl_sim.testing` and the stub)
Branch: `p0/i6c-t42-crew`

## Goal
The crew actor exists: each simulated working day it installs valves on piping lines (a record each, with `valve_data` values and a `belongs_to` link), posts the day's progress with the valve keys as hashtags, and now and then posts an inspection failure with `#hold`. A scenario injection can make it post an urgent announcement. The stub has the class, constants and docstring; `act` raises `NotImplementedError`. A provided test file (12 tests) must pass.

## Brief references (pasted)
> **29.5** A simulator generates realistic project activity by acting through the suite's public MCP server and API, as if it were a project team. Deterministic actors do the bulk mechanics; roles include the document controller (registers revisions, transmittals), the planner (clears constraints) and the welding foreman / crew (records, photos, feed posts). Time compression: `sim_advance(days=...)` runs a working day in seconds. Determinism: seeded randomness, so a scenario replays identically.
> **29.1** Dogfood the open interfaces: the simulator uses only the public API and MCP.
> FANOUT D6: simulator v0 is fully deterministic and makes no LLM calls.

### Specification
`act` is the whole ticket. The module docstring of the stub is the specification (it is also the final docstring; keep it). Titles, link relations, transition names and post texts are checked character by character by the provided test.

`rec.set_psets(valve, {"valve_data": {...}})` takes `{pset: {property: value}}`; `size` is the integer drawn from `SIZES_IN` (so a title reads `4in`, not `4.0in`).

**Imports to add:** `from tl_sim.actors.base import Rec`; `from tl_sim.scenario import draw`.

Learnings that apply:
- pyright is `standard` for `packages/tl-sim`; ruff limits lines to 100 columns (docstrings and comments too). Run `uv run ruff format packages/tl-sim` and `uv run ruff check packages/tl-sim` before committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- Provided tests live under `docs/tickets/P0-I6/provided/*.py.txt`; copy them into the test tree byte for byte (`cp`). Do not edit the copy.
- Commit your report at `docs/reports/P0-I6/P0-I6-T42.md` (it is inside your Allowed paths).
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
class CrewParams(Strict):
    """Installs valves on lines, records their data and posts the day's progress."""

    valves_per_day: Count = CountNormal(dist="normal", mean=3, sd=1)
    reject_rate: float = Field(default=0.1, ge=0, le=1)  # chance per day of a quality `#hold` post
    announce: str | None = None  # one-off: the `material_late` injection posts this text

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
# packages/tl-sim/src/tl_sim/actors/crew.py (existing stub; keep the constants and the class header)
"""The crew: installs valves on lines, records their data, reports progress, flags problems.

One working day (``act``), in this order, drawing from ``ctx.rng`` only where stated:

1. Read the lines (title starts ``Line ``). No lines: do nothing.
2. If ``params.announce`` is set, post ``#urgent <announce>``.
3. Draw ``n = draw(params.valves_per_day, ctx.rng)``. For each valve draw, in this order,
   ``ctx.rng.choice(lines)``, ``ctx.rng.choice(SIZES_IN)`` and ``ctx.rng.choice(MAKERS)``. Create
   ``Valve V<serial:03d> <size>in on <designation>`` (``serial`` is the number of existing records
   whose title starts ``Valve `` plus one for each created so far; ``size`` is the integer;
   ``designation`` is the line title without ``Line ``). Set the pset
   ``valve_data`` to ``{"size_in": size, "body_material": "CS", "manufacturer": maker}`` and link
   the valve ``belongs_to`` the line.
4. If valves were installed, post ``Installed <n> valves: #<key> #<key> ...`` (creation order).
5. Draw ``roll = ctx.rng.random()`` (always). When valves were installed and
   ``roll < params.reject_rate``, draw ``ctx.rng.choice(installed)`` and post
   ``Inspection failed on #<key>, needs rework #hold``.
"""

from __future__ import annotations

from tl_sim.actors.base import BaseActor, Recorder
from tl_sim.scenario import CrewParams
from tl_sim.types import SimContext

SIZES_IN = (2, 3, 4, 6, 8)
MAKERS = ("Crane", "Velan", "Emerson")


class Crew(BaseActor):
    name = "crew"
    params: CrewParams

    def act(self, ctx: SimContext, rec: Recorder) -> None:
        raise NotImplementedError("STUB (P0-I6-T42)")
```


## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-sim/src/tl_sim/actors/crew.py`
- `packages/tl-sim/src/tl_sim/actors/base.py`
- `packages/tl-sim/src/tl_sim/testing.py` (the in-memory world the tests use; read `FakeClient`)
- `docs/tickets/P0-I6/provided/c-test_actor_crew.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-sim/src/tl_sim/actors/crew.py` (edit)
- `packages/tl-sim/tests/test_actor_crew.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I6/P0-I6-T42.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I6/provided/c-test_actor_crew.py.txt packages/tl-sim/tests/test_actor_crew.py`
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
Standard report (`docs/templates/haiku-report.md`). Paste the posts of a two-day run.

## Escalation triggers
- Stop and report *Blocked* if a pasted signature disagrees with the repo, or if the provided test cannot pass without changing a file outside *Allowed paths*.
- Stop after two attempts at the same failing test.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
