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
