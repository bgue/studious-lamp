# P1-I2-T12a — Simulator: the document registrar actor

Status: ready
Tier: haiku
Labels: sim
Depends on: S16 on `p1/i2` (the scenario parameters, the `DocumentDesk` methods of the recorder and the in-memory world, all in the tree); no other ticket
Branch: `p1/i2-t12a-sim-document-registrar`

## Goal
The simulator gets a person who registers controlled documents: new numbers under the company numbering, the first revision of a document, and a floating link from a tag to a new document. `packages/tl-sim/src/tl_sim/actors/document_registrar.py` has the actor's class, its constants and `next_number` written; `DocumentRegistrar.act` raises `NotImplementedError`. You implement it. One provided test file must pass.

## Brief references (pasted)
> **Brief 29 (simulator).** An actor is a role with a rhythm: each simulated day it draws from the seeded generator and acts through the same API a person uses. The same seed gives the same day.
>
> **ADR-0011.** Controlling acts (issuing a revision) are an admin's; a simulated person is never an admin, so this actor registers and drafts only and no pin goes stale in a simulation.

### Specification
- `act` makes its draws from `ctx.rng` **in the order the STEPS give**; the test checks that the same seed gives the same day and that the draw order is the documented one. Draw `roll` even when its branch does nothing.
- Everything goes through the recorder (`rec.records`, `rec.register_document`, `rec.start_revision`, `rec.link`); the actor never touches a client, a database or a file.
- Do not change the parameters (`DocumentRegistrarParams`), the recorder or the registry; they are final.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-sim/src/tl_sim/actors/document_registrar.py` (the stub you complete):
```python
"""The document registrar: registers documents under the company numbering and starts revisions.

Needs the company standards and the document standards loaded in the ledger (`tl standards load`
for `co.acme.standards@1.0.0` and `co.acme.documents@1.0.0`): the document types, the disciplines
and the document number pattern. One working day (``act``), in this order, drawing from
``ctx.rng`` only where stated:

1. Read the documents, ``rec.records("type:documents.Document")`` (``existing``), the revisions,
   ``rec.records("type:documents.Revision")``, and the tags,
   ``rec.records("type:engineering.Tag")``.
2. Draw ``n = draw(params.documents_per_day, ctx.rng)``.
3. For each of the ``n`` new documents draw ``kind = ctx.rng.choice(KINDS)`` (a ``(doc_type,
   discipline, noun)``). The number is ``<doc_type>-<seq:04d>``, where the sequence is one more than
   the largest sequence among the documents (existing and created so far) whose number starts
   ``<doc_type>-``, or 1 when there is none. Register it with ``rec.register_document(number,
   title, doc_type, discipline)`` where ``title`` is ``<noun> <number>``. Keep the record in
   ``created``.
4. Draw ``roll = ctx.rng.random()`` (always, even when nothing follows). When ``roll <
   params.revision_rate``, the candidates are the documents (existing and created) that have no
   revision yet (no revision key starts ``<number>@``), in key order. When there are any, draw
   ``victim = ctx.rng.choice(candidates)`` and start its first revision with
   ``rec.start_revision(victim, "First draft")``.
5. Draw ``roll = ctx.rng.random()`` (always). When ``roll < params.link_rate`` and there are tags
   and ``created`` documents, draw ``tag = ctx.rng.choice(tags)`` and ``document =
   ctx.rng.choice(created)`` and link them with ``rec.link(tag, document, "references")``. Only a
   document created today is linked, so a pair is never linked twice.

No revision is issued: issuing is an admin's act (ADR-0011) and a simulated person is never an
admin, so no pin goes stale in a simulation. The link is floating.

STUB (P1-I2-T12a): the bodies of DocumentRegistrar.act raise NotImplementedError; their
signatures, options, docstrings and the helpers are final. Each body has a STEPS comment.
Implement them, then delete this paragraph, the STEPS comments and the `ruff: noqa` line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written

from __future__ import annotations

from tl_sim.actors.base import BaseActor, Rec, Recorder
from tl_sim.scenario import DocumentRegistrarParams, draw
from tl_sim.types import SimContext

#: (document type, discipline, what it is called in a title)
KINDS = (
    ("ISO", "PIP", "Isometric"),
    ("PID", "PRO", "P&ID"),
    ("DS", "MEC", "Datasheet"),
    ("LD", "INS", "Loop diagram"),
    ("SPC", "PRO", "Specification"),
    ("CAL", "STR", "Calculation"),
)
DOCUMENT_QUERY = "type:documents.Document"
REVISION_QUERY = "type:documents.Revision"
TAG_QUERY = "type:engineering.Tag"


def next_number(known: list[str], doc_type: str) -> str:
    """The next free number for ``doc_type`` given the numbers already used."""
    prefix = f"{doc_type}-"
    seqs = [
        int(number.removeprefix(prefix))
        for number in known
        if number.startswith(prefix) and number.removeprefix(prefix).isdecimal()
    ]
    return f"{prefix}{max(seqs, default=0) + 1:04d}"


class DocumentRegistrar(BaseActor):
    name = "document_registrar"
    params: DocumentRegistrarParams

    def act(self, ctx: SimContext, rec: Recorder) -> None:
        # STEPS
        # 1. existing = rec.records(DOCUMENT_QUERY); revised = the set of the part before "@" of
        #    each key of rec.records(REVISION_QUERY); tags = rec.records(TAG_QUERY);
        #    known = [d.key for d in existing]; created: list[Rec] = [].
        # 2. For _ in range(draw(self.params.documents_per_day, ctx.rng)): doc_type, discipline,
        #    noun = ctx.rng.choice(KINDS); number = next_number(known, doc_type); made =
        #    rec.register_document(number, f"{noun} {number}", doc_type, discipline);
        #    known.append(number); created.append(made).
        # 3. roll = ctx.rng.random() (always). If roll < self.params.revision_rate: candidates =
        #    the documents of existing + created whose key is not in `revised`, sorted by key;
        #    if there are any: victim = ctx.rng.choice(candidates);
        #    rec.start_revision(victim, "First draft").
        # 4. roll = ctx.rng.random() (always). If roll < self.params.link_rate and tags and
        #    created: tag = ctx.rng.choice(tags); document = ctx.rng.choice(created);
        #    rec.link(tag, document, "references").
        raise NotImplementedError
```

`packages/tl-sim/src/tl_sim/scenario.py` (excerpts; read-only, do not edit):
```python
def draw(count: Count, rng: Random) -> int:
    """One draw from ``count`` using ``rng``. Never negative."""
    ...


class DocumentRegistrarParams(Strict):
    """Keeps the document register: registers documents under the company's numbering, starts the
    first revision of some, and links tags to documents (floating). Needs the document standards
    loaded in the ledger. Issuing a revision is an admin's act (ADR-0011) and no simulated person
    is an admin, so no revision is issued and no pin goes stale.
    """

    documents_per_day: Count = CountRange(min=1, max=3)
    revision_rate: float = Field(default=0.5, ge=0, le=1)  # chance per day of starting a revision
    link_rate: float = Field(default=0.5, ge=0, le=1)  # chance per day of linking a tag
```

`packages/tl-sim/src/tl_sim/actors/base.py` (the recorder methods the actor uses; read-only):
```python
class Rec:  # a record as the recorder returns it
    id: str
    key: str
    title: str
    status: str | None = None

class Recorder:
    def records(self, q: str = "", *, title_prefix: str | None = None) -> list[Rec]: ...
    def register_document(self, number: str, title: str, doc_type: str, discipline: str) -> Rec: ...
    def start_revision(self, document: Rec, purpose: str) -> Rec: ...
    def link(self, source: Rec, target: Rec, relation: str) -> None: ...
```

## Context (read these, nothing else)
- `packages/tl-sim/src/tl_sim/actors/document_registrar.py` (the file you edit)
- `packages/tl-sim/src/tl_sim/actors/` (the other actors, for style: `foreman.py` or `tag_creator.py` if present)
- `packages/tl-sim/src/tl_sim/actors/base.py` (`BaseActor`, `Rec`, `Recorder`)
- `packages/tl-sim/src/tl_sim/testing.py` (`FakeWorld`, `make_context`, already in the tree)
- `docs/tickets/P1-I2/provided/t12a-test_actor_document_registrar.py.txt` (the test)
may explore: (none)

Learnings that apply (pasted from `docs/memory/LEARNINGS.md` and the build's conventions):
- Environment: run everything from the repository root. A new worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages (L-P0-I6A-1). `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- ruff limits lines to 100 columns, docstrings and comments included (L-P0-I1-6). Run `uv run ruff format` before committing. pyright is `standard` for `packages/tl-modules`, `tl-cli`, `tl-api`; strict for `tl_core`, `tl_schema`, `tl_adapters`.
- Provided files live under `docs/tickets/P1-I2/provided/` as `.py.txt`; copy them into the tree byte for byte (the target names are in *Steps*). Do not edit the copies: they are already `ruff format` and pyright clean.
- Commit your report at `docs/reports/P1-I2/<ticket-id>.md` (it is inside your Allowed paths). Say "commit your report" in your final message (L-P0-I2-B7).
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*.
- No new dependencies. Remove the `STUB` paragraph from the module docstring, every `STEPS` comment and the `# ruff: noqa: F401` line when you implement a stub.
- The test counts below were counted from the provided files (`grep -c "^def test_"`); parametrized tests expand to more cases when run, and the pytest summary is the number of cases (L-P0-I8A-8). A test that does not use the `db`, `world` or `engine` fixtures runs once under `--adapters sqlite,postgres`; one that does runs once per adapter (L-P1-I1-6).
- Never name a module `types.py`, `enum.py` or `json.py` inside a package (L-P0-I5-B1).
- Never write a hand-made `cur_*`, `hist_*` or `v_*` object, and never change `schema/**` or anything under `generated/` unless this ticket says so.
- `just test-parity` takes about 70 minutes for the whole repository (L-P1-I1-10): run only the scoped commands in *Acceptance* (a ticket whose tests do not use the database fixtures has no Postgres command), never the whole parity suite.
- Start Postgres with `sudo pg_ctlcluster 16 main start` if it is not running; `TL_PG_URL` is `postgresql://postgres:postgres@localhost:5432/tl_test`.
- Draw order is part of the contract: a reordered `ctx.rng` call changes every later day of every seed.
- `uv run pytest packages/tl-sim -q` is the package gate; sim tests run once (no database fixtures). The end-to-end test of this actor against the real API (`test_document_registrar_end_to_end.py`) is held by the supervisor and is not part of this ticket.

## Allowed paths
- `packages/tl-sim/src/tl_sim/actors/document_registrar.py` (edit)
- `packages/tl-sim/tests/test_actor_document_registrar.py` (create; byte-identical copy of the provided test)
- `docs/reports/P1-I2/P1-I2-T12a.md` (create)

## Steps
1. `uv sync --all-packages`.
2. Copy `docs/tickets/P1-I2/provided/t12a-test_actor_document_registrar.py.txt` to `packages/tl-sim/tests/test_actor_document_registrar.py`.
3. Implement `DocumentRegistrar.act` by its STEPS comment; remove the STUB paragraph, the STEPS comment and the `ruff: noqa` line.
4. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest packages/tl-sim/tests/test_actor_document_registrar.py -q
uv run pytest packages/tl-sim -q
```
Expected: `just check` clean; 11 test functions pass; the whole package passes.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`). There is no parity run for this ticket: its tests do not use the database fixtures, so Acceptance has no `--adapters` command.

## Escalation triggers
- Stop and report *Blocked* if a STEPS line and the provided test disagree.
- Stop if a test needs a change outside the Allowed paths.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
