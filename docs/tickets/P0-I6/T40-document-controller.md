# P0-I6-T40 — Document controller actor

Status: ready
Tier: haiku
Labels: tests
Depends on: — (the base `p0/i6c` already has the actor base, `tl_sim.testing` and the stub)
Branch: `p0/i6c-t40-document-controller`

## Goal
The document controller actor exists: each simulated working day it registers documents against piping lines, submits them for review, now and then issues a new revision that supersedes an earlier one, and posts what it registered. The stub has the class, constants and docstring; `act` raises `NotImplementedError`. A provided test file (13 tests) must pass.

## Brief references (pasted)
> **29.5** A simulator generates realistic project activity by acting through the suite's public MCP server and API, as if it were a project team. Deterministic actors do the bulk mechanics; roles include the document controller (registers revisions, transmittals), the planner (clears constraints) and the welding foreman / crew (records, photos, feed posts). Time compression: `sim_advance(days=...)` runs a working day in seconds. Determinism: seeded randomness, so a scenario replays identically.
> **29.1** Dogfood the open interfaces: the simulator uses only the public API and MCP.
> FANOUT D6: simulator v0 is fully deterministic and makes no LLM calls.

### Specification
`act` is the whole ticket. The module docstring of the stub is the specification (it is also the final docstring; keep it). Titles, link relations, transition names and post texts are checked character by character by the provided test.

**Imports to add:** `import re`; `from tl_sim.actors.base import Rec`; `from tl_sim.scenario import draw`.

Helpers you will want (private, same module): one that splits a title into its stem and revision letter (regex `^(?P<stem>Doc \d{3} .+) Rev (?P<letter>[A-Z])$`), and one that keeps, from a list of documents, only the newest revision of each stem. After creating a revision, replace the old document by the new one in your working list so a second revision in the same step cannot pick it again.

Learnings that apply:
- pyright is `standard` for `packages/tl-sim`; ruff limits lines to 100 columns (docstrings and comments too). Run `uv run ruff format packages/tl-sim` and `uv run ruff check packages/tl-sim` before committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- Provided tests live under `docs/tickets/P0-I6/provided/*.py.txt`; copy them into the test tree byte for byte (`cp`). Do not edit the copy.
- Commit your report at `docs/reports/P0-I6/P0-I6-T40.md` (it is inside your Allowed paths).
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
class DocumentControllerParams(Strict):
    """Registers documents against lines, submits them for review and issues new revisions."""

    documents_per_day: Count = CountRange(min=1, max=2)
    revision_rate: float = Field(default=0.25, ge=0, le=1)  # chance per day of one new revision
    forced_revisions: int = Field(default=0, ge=0)  # one-off: the `design_revision` injection

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
# packages/tl-sim/src/tl_sim/actors/document_controller.py (existing stub; keep the constants and the class header)
"""The document controller: registers documents against lines, submits them, issues revisions.

One working day (``act``), in this order, drawing from ``ctx.rng`` only where stated:

1. Read the lines (``title`` starting ``Line ``). No lines: do nothing.
2. Draw ``n = draw(params.documents_per_day, ctx.rng)``.
3. For each of the ``n`` new documents, draw in this order ``ctx.rng.choice(lines)``,
   ``ctx.rng.choice(DISCIPLINES)``, ``ctx.rng.choice(KINDS)``. Create the record titled
   ``Doc <serial:03d> <discipline> <kind> Rev A``, where ``serial`` is the number of documents
   that already exist (titles starting ``Doc `` and ending ``Rev A``) plus one for each document
   this step has created so far. Link it ``references`` the line, then ``submit`` it
   (``Review`` expected).
4. Draw ``roll = ctx.rng.random()`` (always, even when nothing follows). The number of revisions is
   ``params.forced_revisions`` when that is above 0, else 1 if ``roll < params.revision_rate``,
   else 0.
5. For each revision, the candidates are the documents that are the latest revision of their
   number (no other title has the same ``Doc <serial:03d> <discipline> <kind>`` stem with a later
   letter) and whose ``state`` is ``Review`` or ``Approved``, in key order. None: stop. Otherwise
   draw ``ctx.rng.choice(candidates)`` and ``ctx.rng.choice(lines)``. Create the next revision
   (``Rev A`` to ``Rev B``, and so on), link it ``supersedes`` the old one and ``references`` the
   drawn line, and ``submit`` it.
6. If anything was created, post ``Registered <k> documents: #<key> #<key> ...`` (``k`` is the
   count, keys in creation order).
"""

from __future__ import annotations

from tl_sim.actors.base import BaseActor, Recorder
from tl_sim.scenario import DocumentControllerParams
from tl_sim.types import SimContext

DISCIPLINES = ("Piping", "Mechanical", "Civil", "Instrumentation")
KINDS = ("isometric", "datasheet", "procedure", "layout")


class DocumentController(BaseActor):
    name = "document_controller"
    params: DocumentControllerParams

    def act(self, ctx: SimContext, rec: Recorder) -> None:
        raise NotImplementedError("STUB (P0-I6-T40)")
```


## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-sim/src/tl_sim/actors/document_controller.py`
- `packages/tl-sim/src/tl_sim/actors/base.py`
- `packages/tl-sim/src/tl_sim/testing.py` (the in-memory world the tests use; read `FakeClient`)
- `docs/tickets/P0-I6/provided/c-test_actor_document_controller.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-sim/src/tl_sim/actors/document_controller.py` (edit)
- `packages/tl-sim/tests/test_actor_document_controller.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I6/P0-I6-T40.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I6/provided/c-test_actor_document_controller.py.txt packages/tl-sim/tests/test_actor_document_controller.py`
2. Implement `act` and its helpers, add the imports, keep the docstring.
3. Run the acceptance commands, write the report, commit both.

## Acceptance
```
uv run pytest packages/tl-sim -q
just check
```
Expected: 13 tests pass in the new file and the whole `packages/tl-sim` run stays green; `just check` clean.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`). Paste the titles of the records created in a two-day run.

## Escalation triggers
- Stop and report *Blocked* if a pasted signature disagrees with the repo, or if the provided test cannot pass without changing a file outside *Allowed paths*.
- Stop after two attempts at the same failing test.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
