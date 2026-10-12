# P1-I1-T12 — Simulator: the tag clerk

Status: ready
Tier: haiku
Labels: sim
Depends on: the tag desk (`TagDesk`, `Recorder.create_tag/rename_tag`, `FakeClient.create_tag/rename_tag`) and the scenario parameters, on `p1/i1`; no other ticket
Branch: `p1/i1-t12-sim-tag-clerk`

## Goal
The simulator has a person who keeps the tag list. `packages/tl-sim/src/tl_sim/actors/tag_clerk.py` has the constants, the actor class and its documented day final; `next_number` and `TagClerk.act` raise `NotImplementedError`. The actor is already registered (`actors/registry.py`), its parameters (`TagClerkParams`) are in the scenario model, and the recorder and the in-memory world can create and rename tags. You implement the two bodies. One provided test file (`9` test functions) must pass.

## Brief references (pasted)
> **Brief 29 Simulation.** Actors are deterministic from a seed: the same seed gives the same day. An actor decides what to do from its random generator and from what it reads through `ctx.client`; every write goes through a `Recorder` method, which writes the matching ground-truth line in the same breath.
>
> **Brief 9 M2.** A tag number is `<area>-<mnemonic>-<seq>`; a rename creates a new tag that supersedes the old one, which leaves service.

### Specification
- The module docstring of `tag_clerk.py` is the specification of a day: read it first. The order of the random draws is part of the contract (a different order gives a different day for the same seed).
- Reads go through `rec.records("type:engineering.Tag")`; writes only through `rec.create_tag(...)` and `rec.rename_tag(...)`. Never call `ctx.client` directly.
- A `Rec` has `key` (the tag number), `title` and `state` (`Superseded` for a tag a rename replaced; an empty status is `Draft`).
- `draw(count, rng)` turns the scenario's count (a number, a range or a normal) into an integer using the actor's generator.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-sim/src/tl_sim/actors/tag_clerk.py` (the stub you complete):
```python
"""The tag clerk: registers tags against the standards and now and then renumbers one.

Needs the company standards loaded in the ledger (`tl standards load`): the area list, the tag
pattern and the tag classes. One working day (``act``), in this order, drawing from ``ctx.rng``
only where stated:

1. Read the tags: ``rec.records("type:engineering.Tag")``. ``existing`` is that list.
2. Draw ``n = draw(params.tags_per_day, ctx.rng)``.
3. For each of the ``n`` new tags draw, in this order, ``area = ctx.rng.choice(AREAS)`` and
   ``kind = ctx.rng.choice(KINDS)`` (a ``(mnemonic, class_code, noun)``). The sequence is one more
   than the largest sequence among the tags (existing and created so far) whose number starts
   ``<area>-<mnemonic>-``, or 1 when there is none; the number is
   ``<area>-<mnemonic>-<seq:04d>``. Register it with ``rec.create_tag(number, class_code,
   service)`` where ``service`` is ``<Noun> <number>``.
4. Draw ``roll = ctx.rng.random()`` (always, even when nothing follows). When ``roll <
   params.rename_rate`` and ``existing`` holds tags that are in service (``state`` is not
   ``Superseded``), draw ``victim = ctx.rng.choice(candidates)`` where ``candidates`` are those
   tags in key order. The new number takes the victim's area and mnemonic and the next free
   sequence for that pair (as in step 3, counting every tag known so far). Renumber it with
   ``rec.rename_tag(victim, new_number, "renumbered")``.

A tag the clerk renumbers is replaced, never edited: the old tag stays in the ledger as
``Superseded`` and the new tag ``supersedes`` it (the log names both).

STUB (P1-I1-T12): the bodies of the functions raise NotImplementedError; their signatures,
docstrings and the constants are final. Each body has a STEPS comment. Implement them, then delete
this paragraph, the STEPS comments and the `ruff: noqa` line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written

from __future__ import annotations

from tl_sim.actors.base import BaseActor, Rec, Recorder
from tl_sim.scenario import TagClerkParams, draw
from tl_sim.types import SimContext

AREAS = ("10", "20", "30", "40", "47", "50")
#: (mnemonic, tag class, what it is called in a service description)
KINDS = (
    ("FV", "ControlValve", "Flow control valve"),
    ("PV", "ControlValve", "Pressure control valve"),
    ("HV", "ManualValve", "Isolation valve"),
    ("PT", "Transmitter", "Pressure transmitter"),
    ("P", "Pump", "Transfer pump"),
    ("V", "Vessel", "Separator"),
)
TAG_QUERY = "type:engineering.Tag"
ENDED_STATE = "Superseded"


def next_number(known: list[str], area: str, mnemonic: str) -> str:
    """The next free number for ``area`` and ``mnemonic`` given the numbers already used."""
    # STEPS
    # 1. prefix = f"{area}-{mnemonic}-". seqs = the integer after the prefix of every number in
    #    ``known`` that starts with it and whose rest is all digits.
    # 2. Return f"{prefix}{max(seqs, default=0) + 1:04d}".
    raise NotImplementedError


class TagClerk(BaseActor):
    name = "tag_clerk"
    params: TagClerkParams

    def act(self, ctx: SimContext, rec: Recorder) -> None:
        # STEPS
        # 1. existing = rec.records(TAG_QUERY); known = [tag.key for tag in existing].
        # 2. Draw n = draw(self.params.tags_per_day, ctx.rng). For each of the n tags (draw the area
        #    then the kind as the module docstring says): number = next_number(known, area,
        #    mnemonic); made = rec.create_tag(number, class_code, f"{noun} {number}"); append
        #    number to known.
        # 3. roll = ctx.rng.random(). candidates = the tags of ``existing`` whose ``state`` is not
        #    ENDED_STATE, in key order (existing is already in key order). When roll <
        #    self.params.rename_rate and candidates: victim = ctx.rng.choice(candidates); split
        #    victim.key at "-" into area and mnemonic (the first two parts); new_number =
        #    next_number(known, area, mnemonic); rec.rename_tag(victim, new_number,
        #    "renumbered"); append new_number to known.
        raise NotImplementedError
```

`packages/tl-sim/src/tl_sim/actors/base.py` (what the actor uses):
```python
@dataclass(frozen=True)
class Rec:
    id: str; key: str; title: str; status: str | None = None
    @property
    def state(self) -> str: ...      # status, or "Draft" when empty

class Recorder:
    def records(self, q: str = "", *, title_prefix: str | None = None) -> list[Rec]: ...   # in key order
    def create_tag(self, number: str, class_code: str, service: str) -> Rec: ...
    def rename_tag(self, old: Rec, new_number: str, reason: str) -> Rec: ...
```

`packages/tl-sim/src/tl_sim/scenario.py`:
```python
class TagClerkParams(Strict):
    tags_per_day: Count = CountRange(min=1, max=3)
    rename_rate: float = Field(default=0.2, ge=0, le=1)
def draw(count: Count, rng: Random) -> int: ...
```
`SimContext.rng` is a `random.Random` seeded per (run seed, actor, day).

## Context (read these, nothing else)
- `packages/tl-sim/src/tl_sim/actors/tag_clerk.py` (the file you edit)
- `packages/tl-sim/src/tl_sim/actors/crew.py` (a finished actor; read it for style)
- `docs/tickets/P1-I1/provided/t12-test_actor_tag_clerk.py.txt` (the test)
may explore: (none)

Learnings that apply (pasted from `docs/memory/LEARNINGS.md` and the build's conventions):
- Environment: run everything from the repository root. A new worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages (L-P0-I6A-1). `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- pyright is `standard` for `packages/tl-sim`; ruff limits lines to 100 columns, docstrings and comments included (L-P0-I1-6). Run `uv run ruff format` before committing.
- Provided files live under `docs/tickets/P1-I1/provided/` as `.py.txt`; copy them into the tree byte for byte (the target names are in *Steps*). Do not edit the copies: they are already `ruff format` and pyright clean.
- Commit your report at `docs/reports/P1-I1/<ticket-id>.md` (it is inside your Allowed paths). Say "commit your report" in your final message (L-P0-I2-B7).
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*.
- No new dependencies. Remove the `STUB` paragraph from the module docstring, every `STEPS` comment and the `# ruff: noqa: F401` line when you implement a stub.
- The test counts below were counted from the provided files (`grep -c "^def test_"`); parametrized tests expand to more cases when run, and the pytest summary is the number of cases (L-P0-I8A-8).
- Never name a module `types.py`, `enum.py` or `json.py` inside a package (L-P0-I5-B1).
- Never write a hand-made `cur_*` table or change `schema/**` or anything under `generated/` unless this ticket says so.
- The provided test runs the actor on `tl_sim.testing.FakeWorld` (in memory); it needs no server. Do not edit `testing.py`, `base.py`, `client.py` or `scenario.py`.
- The simulator may not import ledger, unit-of-work or handler code (`tests/test_contract_and_boundary.py` reads the imports of `src/tl_sim`); `tag_clerk.py` needs only what the stub already imports.
- Draw order matters: `area` then `kind` for each new tag; `roll` once after them, always.


## Allowed paths
- `packages/tl-sim/src/tl_sim/actors/tag_clerk.py` (edit)
- `packages/tl-sim/tests/test_actor_tag_clerk.py` (create; byte-identical copy of the provided test)
- `docs/reports/P1-I1/P1-I1-T12.md` (create)

## Steps
1. `uv sync --all-packages`.
2. Copy `docs/tickets/P1-I1/provided/t12-test_actor_tag_clerk.py.txt` to `packages/tl-sim/tests/test_actor_tag_clerk.py`.
3. Implement `next_number` and `TagClerk.act` by their STEPS comments; remove the STUB paragraph, the STEPS comments and the `ruff: noqa` line.
4. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest packages/tl-sim/tests/test_actor_tag_clerk.py -q
uv run pytest packages/tl-sim -q
```
Expected: `just check` clean; 9 test functions pass (the parametrized one counts twice); the whole tl-sim package passes.

## Tests to add
None beyond the provided file(s).

## Report requirements
Standard report (`docs/templates/haiku-report.md`) plus: the output of the parity run (decisive lines).

## Escalation triggers
- Stop and report *Blocked* if a STEPS line and the provided test disagree.
- Stop if a test needs a change outside the Allowed paths.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
