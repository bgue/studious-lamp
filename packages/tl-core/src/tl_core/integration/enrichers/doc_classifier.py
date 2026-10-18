# ruff: noqa: F401
# pyright: reportUnusedImport=false, reportUnusedFunction=false
"""``doc_classifier``: a deterministic document classifier (brief §18.9; ADR-0008 decision 8).

STUB (P1-I7-T06): the tables and constants are final; the bodies below raise NotImplementedError.
Remove this paragraph, every STEPS comment, the two lint-silencing lines above and
`NotImplementedError` when you implement them.

It reads the facts a document already has (its number, its title, the file's name, its title
metadata) and proposes two properties of its own layer ``enrich.doc_classifier``:

* ``doc_type``: a code of the ``DocumentType`` list of the sample company's standards;
* ``discipline``: a code of the ``Discipline`` list.

There is no model and no network: a fixed keyword table, matched on whole words (a keyword is a
run of words, so ``photo`` is not ``mto``), the longest match winning. The confidence is that of the
rule that matched: the document number's own prefix is the surest, a keyword in the title next, a
keyword only in the file name or its metadata the least. Nothing is raised for a bad subject; a
subject nothing matches is ``unsupported``.
"""

from __future__ import annotations

import re

from tl_core.integration.contract import (
    EnrichmentResult,
    EnrichmentSubject,
    ProposedValue,
)

NAME = "doc_classifier"
VERSION = "1.0.0"
NOTE = "deterministic classifier, no model (ADR-0008 decision 8)"

#: The confidence of each kind of evidence.
CONFIDENCE_NUMBER = 0.95
CONFIDENCE_TITLE = 0.85
CONFIDENCE_FILE = 0.7
#: A general "drawing" says little: it is the fallback type, never the surest.
CONFIDENCE_FALLBACK = 0.5
#: Only this much of any text is read (a title is short; this bounds the work on hostile input).
MAX_TEXT_CHARS = 2_000

#: ``DocumentType`` code -> keyword phrases (lower case words). The code is also a document
#: number prefix (``ISO-1234``).
DOC_TYPE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "ISO": ("isometric", "isometrics"),
    "PID": (
        "p&id",
        "p and id",
        "pid",
        "piping and instrument diagram",
        "piping and instrumentation diagram",
    ),
    "GA": ("general arrangement", "ga drawing"),
    "DS": ("datasheet", "data sheet"),
    "LD": ("loop diagram", "loop drawing"),
    "SPC": ("specification", "spec"),
    "PRC": ("procedure", "method statement"),
    "CAL": ("calculation", "calculations", "calc"),
    "MTO": ("material take off", "material takeoff", "mto", "bill of materials"),
    "ITR": ("inspection and test record", "inspection test record", "itr"),
    "WPS": ("welding procedure specification", "wps"),
    "DRW": ("drawing", "drawings"),
}
#: Types that are the fallback when only a general word matched.
FALLBACK_TYPES = frozenset({"DRW"})

#: ``Discipline`` code -> keyword phrases.
DISCIPLINE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "PIP": ("piping", "pipe", "pipeline", "isometric", "spool", "p&id", "pipe support"),
    "MEC": ("mechanical", "pump", "compressor", "vessel", "heat exchanger", "equipment", "turbine"),
    "ELE": ("electrical", "cable", "cabling", "switchgear", "motor", "earthing", "lighting"),
    "INS": ("instrument", "instrumentation", "loop", "transmitter", "control valve", "analyser"),
    "CIV": ("civil", "foundation", "drainage", "roadworks", "paving"),
    "STR": ("structural", "steelwork", "beam", "platform"),
    "PRO": ("process", "flow diagram", "pfd", "heat and material balance", "hydraulic"),
    "HSE": ("safety", "hazop", "environmental", "risk assessment", "permit to work", "fire"),
}

_WORD = re.compile(r"[a-z0-9]+")


def words(text: str) -> tuple[str, ...]:
    """Lower-case words of ``text``: runs of letters and digits. Only the first
    ``MAX_TEXT_CHARS`` characters are read."""
    # STEPS
    # 1. Cut `text` to its first MAX_TEXT_CHARS characters, then lower-case it.
    # 2. Return every match of `_WORD` in it, in order, as a tuple.
    raise NotImplementedError


def _phrase(text: str) -> tuple[str, ...]:
    # STEPS
    # 1. Lower-case `text` and return every match of `_WORD` in it as a tuple. (Unlike `words`
    #    this is not cut: it reads the table's own short phrases.)
    raise NotImplementedError


def best_code(table: dict[str, tuple[str, ...]], tokens: tuple[str, ...]) -> tuple[str, int] | None:
    """The code whose longest keyword phrase occurs in ``tokens`` as a run of whole words.

    Returns ``(code, number of words in the phrase)``; the longer phrase wins, then the code that
    comes first in ``table``. ``None`` when nothing matches.
    """
    # STEPS
    # 1. `best` starts as None.
    # 2. For each code and each phrase of the code, in table order: `parts = _phrase(phrase)`;
    #    skip it when it is empty or longer than `tokens`.
    # 3. If `parts` occurs in `tokens` as consecutive items (compare slices of equal length at
    #    every start), it is a match of `len(parts)` words. Keep it only when `best` is None or
    #    the match is strictly longer than `best`'s (so a tie keeps the earlier code).
    # 4. Return `best`. Do not use regular expressions on `tokens` (they are hostile input).
    raise NotImplementedError


def number_prefix(key: str | None) -> str | None:
    """The ``DocumentType`` code a document number starts with (``ISO-1234`` gives ``ISO``)."""
    # STEPS
    # 1. No key (None or empty): return None.
    # 2. The head is the part of `key.strip().upper()` before the first "-". A key with no "-"
    #    has no prefix: return None.
    # 3. Return the head when it is a code of DOC_TYPE_KEYWORDS, else None.
    raise NotImplementedError


class DocClassifier:
    name = NAME
    version = VERSION
    model_ref: str | None = None

    def accepts(self, subject: EnrichmentSubject) -> bool:
        # STEPS
        # 1. True when the title has a non-blank character, or the record has a key, or there is
        #    a file; False for a subject with none of these.
        raise NotImplementedError

    def enrich(self, subject: EnrichmentSubject) -> EnrichmentResult:
        # STEPS
        # 1. `title = words(subject.title)`. `file_words` is the words of the file name without
        #    its last extension (`filename.rsplit(".", 1)[0]`) followed by the words of the file's
        #    metadata title (None counts as ""); empty when there is no file.
        # 2. doc_type, in this order, the first that applies:
        #    a. `number_prefix(subject.record.key)` gives a code: that code with CONFIDENCE_NUMBER.
        #    b. `best_code(DOC_TYPE_KEYWORDS, title)` gives a code: that code with
        #       CONFIDENCE_TITLE.
        #    c. the same on `file_words` with CONFIDENCE_FILE.
        #    In b and c a code in FALLBACK_TYPES gets at most CONFIDENCE_FALLBACK.
        #    When one applies, add ProposedValue(property="doc_type", value=code, confidence=...).
        # 3. discipline: `best_code(DISCIPLINE_KEYWORDS, title)` with CONFIDENCE_TITLE, else the
        #    same on `file_words` with CONFIDENCE_FILE. Add
        #    ProposedValue(property="discipline", ...).
        # 4. Return EnrichmentResult(enricher=NAME, enricher_version=VERSION, status "ok" when
        #    there is a value else "unsupported", values=the list, notes=[NOTE]).
        raise NotImplementedError
