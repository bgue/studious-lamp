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

import re

from tl_sim.actors.base import BaseActor, Rec, Recorder
from tl_sim.scenario import DocumentControllerParams, draw
from tl_sim.types import SimContext

DISCIPLINES = ("Piping", "Mechanical", "Civil", "Instrumentation")
KINDS = ("isometric", "datasheet", "procedure", "layout")

_REVISION = re.compile(r"^(?P<stem>Doc \d{3} .+) Rev (?P<letter>[A-Z])$")
_OPEN_STATES = ("Review", "Approved")
_LAST_LETTER = "Z"  # no revision follows Rev Z, so a Rev Z document cannot be revised


def _newest_revisions(docs: list[Rec]) -> list[tuple[str, str, Rec]]:
    """The newest revision of each stem as ``(stem, letter, doc)``; non-documents are skipped."""
    newest: dict[str, tuple[str, Rec]] = {}
    for doc in docs:
        match = _REVISION.match(doc.title)
        if match is None:
            continue
        stem, letter = match["stem"], match["letter"]
        if stem not in newest or letter > newest[stem][0]:
            newest[stem] = (letter, doc)
    return [(stem, letter, doc) for stem, (letter, doc) in newest.items()]


def _revisable(docs: list[Rec]) -> list[tuple[str, str, Rec]]:
    """The newest revisions in review or approved, with a next letter, in key order."""
    found = [
        (stem, letter, doc)
        for stem, letter, doc in _newest_revisions(docs)
        if doc.state in _OPEN_STATES and letter < _LAST_LETTER
    ]
    return sorted(found, key=lambda item: item[2].key)


def _submitted(rec: Recorder, doc: Rec) -> Rec:
    """Submit ``doc`` for review; the returned record carries the state the suite left it in."""
    ok = rec.transition(doc, "submit", "Review")
    return Rec(id=doc.id, key=doc.key, title=doc.title, status="Review" if ok else None)


class DocumentController(BaseActor):
    name = "document_controller"
    params: DocumentControllerParams

    def act(self, ctx: SimContext, rec: Recorder) -> None:
        lines = rec.records(title_prefix="Line ")
        if not lines:
            return
        docs = rec.records(title_prefix="Doc ")
        existing = sum(1 for doc in docs if doc.title.endswith(" Rev A"))
        created: list[Rec] = []

        for _ in range(draw(self.params.documents_per_day, ctx.rng)):
            line = ctx.rng.choice(lines)
            discipline = ctx.rng.choice(DISCIPLINES)
            kind = ctx.rng.choice(KINDS)
            serial = existing + len(created) + 1
            doc = rec.create(f"Doc {serial:03d} {discipline} {kind} Rev A")
            rec.link(doc, line, "references")
            doc = _submitted(rec, doc)
            created.append(doc)
            docs.append(doc)

        roll = ctx.rng.random()
        if self.params.forced_revisions > 0:
            revisions = self.params.forced_revisions
        elif roll < self.params.revision_rate:
            revisions = 1
        else:
            revisions = 0

        for _ in range(revisions):
            candidates = _revisable(docs)
            if not candidates:
                break
            stem, letter, old = ctx.rng.choice(candidates)
            line = ctx.rng.choice(lines)
            new = rec.create(f"{stem} Rev {chr(ord(letter) + 1)}")
            rec.link(new, old, "supersedes")
            rec.link(new, line, "references")
            new = _submitted(rec, new)
            created.append(new)
            docs = [new if doc.key == old.key else doc for doc in docs]

        if created:
            keys = " ".join(f"#{doc.key}" for doc in created)
            rec.post(f"Registered {len(created)} documents: {keys}")
