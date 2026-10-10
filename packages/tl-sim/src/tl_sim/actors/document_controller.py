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
