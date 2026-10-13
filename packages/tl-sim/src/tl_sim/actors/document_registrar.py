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
"""

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
        existing: list[Rec] = rec.records(DOCUMENT_QUERY)
        revised = {revision.key.split("@", 1)[0] for revision in rec.records(REVISION_QUERY)}
        tags: list[Rec] = rec.records(TAG_QUERY)
        known = [doc.key for doc in existing]
        created: list[Rec] = []
        for _ in range(draw(self.params.documents_per_day, ctx.rng)):
            doc_type, discipline, noun = ctx.rng.choice(KINDS)
            number = next_number(known, doc_type)
            made = rec.register_document(number, f"{noun} {number}", doc_type, discipline)
            known.append(number)
            created.append(made)
        roll = ctx.rng.random()
        if roll < self.params.revision_rate:
            candidates = sorted(
                (doc for doc in [*existing, *created] if doc.key not in revised),
                key=lambda doc: doc.key,
            )
            if candidates:
                victim = ctx.rng.choice(candidates)
                rec.start_revision(victim, "First draft")
        roll = ctx.rng.random()
        if roll < self.params.link_rate and tags and created:
            tag = ctx.rng.choice(tags)
            document = ctx.rng.choice(created)
            rec.link(tag, document, "references")
