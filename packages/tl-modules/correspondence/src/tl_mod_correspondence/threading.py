"""Threading keys: normalise what an item says about its place in a conversation (brief 9 M10).

Pure functions over text. Nothing here reads the ledger, the clock or the network; the caller
looks up candidate items and hands them in (``match_thread``), so the same input always gives the
same answer. Every function bounds its input and returns an empty result for what it cannot read;
none raises on hostile text.

The module is named ``threading.py`` inside a package, which is safe because the package imports
it by its full name; do not run a script from this directory (L-P0-I5-B1).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

MAX_SUBJECT_CHARS: Final = 500
MAX_HEADER_CHARS: Final = 10_000
MAX_TEXT_CHARS: Final = 20_000
MAX_MESSAGE_ID_CHARS: Final = 254
MAX_REFERENCES: Final = 50
MAX_KEYS: Final = 50
#: A subject shorter than this (after cleaning) is too thin to join two items to one thread.
MIN_SUBJECT_KEY_CHARS: Final = 4

_PREFIX = re.compile(r"^\s*(?:re|fw|fwd|aw|sv|vs|wg|tr)(?:\[\d{1,3}\])?\s*:\s*", re.IGNORECASE)
_SPACE = re.compile(r"\s+")
_ANGLE = re.compile(r"<([^<>\s]{1,254})>")
_PROJECT = re.compile(r"[A-Za-z0-9_.-]{1,40}")
_TYPE_CODE = re.compile(r"[A-Z0-9]{1,8}")


def normalise_subject(subject: str) -> str:
    """The subject as threading compares it: no reply or forward prefixes, one space, lower case.

    ``"RE: Fwd: Re[2]: Revised  Programme"`` gives ``"revised programme"``. Text past
    ``MAX_SUBJECT_CHARS`` is ignored, control characters become spaces, and the result is
    compatibility-normalised (``NFKC``) so a full-width letter equals its plain form.
    """
    text = unicodedata.normalize("NFKC", subject[:MAX_SUBJECT_CHARS])
    text = "".join(" " if unicodedata.category(c).startswith("C") else c for c in text)
    for _ in range(20):  # a prefix may repeat; the loop is bounded
        stripped = _PREFIX.sub("", text, count=1)
        if stripped == text:
            break
        text = stripped
    return _SPACE.sub(" ", text).strip().lower()


def normalise_message_id(value: str | None) -> str | None:
    """A Message-ID without angle brackets, or ``None`` when it is not a usable one.

    Usable: 3 to ``MAX_MESSAGE_ID_CHARS`` characters, one ``@``, no whitespace, angle bracket or
    control character. The case is kept, because the local part may be case sensitive.
    """
    if value is None:
        return None
    text = value.strip()
    if text.startswith("<") and text.endswith(">"):
        text = text[1:-1]
    if not 3 <= len(text) <= MAX_MESSAGE_ID_CHARS or text.count("@") != 1:
        return None
    if any(c.isspace() or c in "<>" or unicodedata.category(c).startswith("C") for c in text):
        return None
    return text


def parse_references(header: str | None) -> list[str]:
    """The message ids in a ``References`` or ``In-Reply-To`` header, in order, without brackets.

    Only ``<...>`` tokens count. At most ``MAX_REFERENCES`` are returned (the first ones), an
    unusable token is skipped, a repeated one is kept once, and a header longer than
    ``MAX_HEADER_CHARS`` is read up to that length.
    """
    if not header:
        return []
    found: list[str] = []
    for token in _ANGLE.findall(header[:MAX_HEADER_CHARS]):
        message_id = normalise_message_id(token)
        if message_id is not None and message_id not in found:
            found.append(message_id)
            if len(found) == MAX_REFERENCES:
                break
    return found


def find_item_numbers(text: str, project: str, type_codes: Sequence[str]) -> list[str]:
    """Item numbers written in ``text``: ``<project>-<TYPE>-<digits>`` for each type code.

    ``find_item_numbers("see P123-COR-0042 and p123-cor-0042", "P123", ("COR", "TRN"))`` gives
    ``["P123-COR-0042"]``: matching ignores case, the result is upper case, in order of first
    appearance, without repeats, at most ``MAX_KEYS``. Digits are 4 to 8 long. Text past
    ``MAX_TEXT_CHARS`` is ignored. A ``project`` or type code that is not plain letters, digits
    and ``_.-`` gives an empty list.
    """
    if _PROJECT.fullmatch(project) is None or not type_codes:
        return []
    codes = [code.upper() for code in type_codes]
    if any(_TYPE_CODE.fullmatch(code) is None for code in codes):
        return []
    kinds = "|".join(re.escape(code) for code in codes)
    pattern = re.compile(
        rf"(?<![A-Za-z0-9]){re.escape(project)}-(?:{kinds})-\d{{4,8}}(?!\d)", re.IGNORECASE
    )
    found: list[str] = []
    for match in pattern.finditer(text[:MAX_TEXT_CHARS]):
        number = match.group(0).upper()
        if number not in found:
            found.append(number)
            if len(found) == MAX_KEYS:
                break
    return found


@dataclass(frozen=True)
class ThreadFacts:
    """What a new item says about where it belongs. Built by the caller from the item."""

    in_reply_to: str | None  # normalised message id of In-Reply-To, if any
    references: Sequence[str]  # normalised message ids of References, oldest first
    subject_key: str  # ``normalise_subject`` of the subject
    numbers: Sequence[str]  # item numbers found in subject and body, in order


@dataclass(frozen=True)
class KnownItem:
    """An item already in the register that a new item may answer."""

    item_id: str
    thread_id: str | None


@dataclass(frozen=True)
class ThreadMatch:
    """The answer: which thread the item joins and which item it answers, and why."""

    thread_id: str | None
    responds_to_id: str | None
    matched_by: str  # header, reference_key or subject (``names.MATCHED_BY``)


def match_thread(
    facts: ThreadFacts,
    by_message_id: Mapping[str, KnownItem],
    by_number: Mapping[str, KnownItem],
    open_threads_by_subject: Mapping[str, str],
) -> ThreadMatch | None:
    """Decide the thread of a new item, or ``None`` when nothing matches.

    In order: (1) ``in_reply_to``, then ``references`` from the newest backwards, looked up in
    ``by_message_id``: matched by ``header``; (2) each of ``numbers`` in order, looked up in
    ``by_number``: matched by ``reference_key``; (3) ``subject_key`` in ``open_threads_by_subject``
    when the key has at least ``MIN_SUBJECT_KEY_CHARS`` characters: matched by ``subject``, with
    no ``responds_to_id``. A hit on an item that has no thread gives ``thread_id=None`` and the
    item's id as ``responds_to_id`` (the caller opens a thread for both).
    """
    candidates: list[str] = []
    if facts.in_reply_to:
        candidates.append(facts.in_reply_to)
    candidates.extend(reversed(list(facts.references)))
    for message_id in candidates:
        known = by_message_id.get(message_id)
        if known is not None:
            return ThreadMatch(known.thread_id, known.item_id, "header")
    for number in facts.numbers:
        known = by_number.get(number)
        if known is not None:
            return ThreadMatch(known.thread_id, known.item_id, "reference_key")
    if len(facts.subject_key) >= MIN_SUBJECT_KEY_CHARS:
        thread_id = open_threads_by_subject.get(facts.subject_key)
        if thread_id is not None:
            return ThreadMatch(thread_id, None, "subject")
    return None
