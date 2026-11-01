"""The row type of the ``RULES`` table (``actions.py``), apart so ``mto.py`` can build rows of it
without importing ``actions.py`` (which imports ``mto.py`` for ``MTO_RULES``)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    """One command a screen may offer on a record, as a line of m4-materials.md section 6.

    ``condition`` is the text of the spec's State / condition column, verbatim (``Received``,
    ``short``, ``no reservation``); ``actions.py`` knows how to judge each text from the record's
    rows, and an unknown text is never offered. ``word`` is the command's access word
    (``materials.reserve``): a test holds it equal to the ``access`` of the command's row in
    ``MATERIALS_COMMANDS``.
    """

    record_type: str
    condition: str
    label: str  # plain words
    command: str  # the command model's class name, as in ``MATERIALS_COMMANDS``
    word: str
