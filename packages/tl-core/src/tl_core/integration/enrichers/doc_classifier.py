"""``doc_classifier``: a deterministic document classifier (brief §18.9; ADR-0008 decision 8).

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
    return tuple(_WORD.findall(text[:MAX_TEXT_CHARS].lower()))


def _phrase(text: str) -> tuple[str, ...]:
    return tuple(_WORD.findall(text.lower()))


def best_code(table: dict[str, tuple[str, ...]], tokens: tuple[str, ...]) -> tuple[str, int] | None:
    """The code whose longest keyword phrase occurs in ``tokens`` as a run of whole words.

    Returns ``(code, number of words in the phrase)``; the longer phrase wins, then the code that
    comes first in ``table``. ``None`` when nothing matches.
    """
    best: tuple[str, int] | None = None
    for code, phrases in table.items():
        for phrase in phrases:
            parts = _phrase(phrase)
            size = len(parts)
            if size == 0 or size > len(tokens):
                continue
            for start in range(len(tokens) - size + 1):
                if tokens[start : start + size] == parts:
                    if best is None or size > best[1]:
                        best = (code, size)
                    break
    return best


def number_prefix(key: str | None) -> str | None:
    """The ``DocumentType`` code a document number starts with (``ISO-1234`` gives ``ISO``)."""
    if not key:
        return None
    head = key.strip().upper().split("-", 1)[0]
    return head if head in DOC_TYPE_KEYWORDS and "-" in key else None


class DocClassifier:
    name = NAME
    version = VERSION
    model_ref: str | None = None

    def accepts(self, subject: EnrichmentSubject) -> bool:
        return bool(subject.title.strip() or subject.record.key or subject.file is not None)

    def enrich(self, subject: EnrichmentSubject) -> EnrichmentResult:
        title = words(subject.title)
        file = subject.file
        file_words: tuple[str, ...] = ()
        if file is not None:
            file_words = words(file.filename.rsplit(".", 1)[0]) + words(file.title or "")
        values: list[ProposedValue] = []

        doc_type: tuple[str, float] | None = None
        prefix = number_prefix(subject.record.key)
        if prefix is not None:
            doc_type = (prefix, CONFIDENCE_NUMBER)
        else:
            for tokens, confidence in ((title, CONFIDENCE_TITLE), (file_words, CONFIDENCE_FILE)):
                found = best_code(DOC_TYPE_KEYWORDS, tokens)
                if found is not None:
                    code = found[0]
                    if code in FALLBACK_TYPES:
                        confidence = min(confidence, CONFIDENCE_FALLBACK)
                    doc_type = (code, confidence)
                    break
        if doc_type is not None:
            values.append(
                ProposedValue(property="doc_type", value=doc_type[0], confidence=doc_type[1])
            )

        for tokens, confidence in ((title, CONFIDENCE_TITLE), (file_words, CONFIDENCE_FILE)):
            found = best_code(DISCIPLINE_KEYWORDS, tokens)
            if found is not None:
                values.append(
                    ProposedValue(property="discipline", value=found[0], confidence=confidence)
                )
                break

        return EnrichmentResult(
            enricher=NAME,
            enricher_version=VERSION,
            status="ok" if values else "unsupported",
            values=values,
            notes=[NOTE],
        )
