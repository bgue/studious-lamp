"""Hashtag and mention parser (brief 21.2). Pure text work: no database, no clock.

A post body is scanned for ``#tag`` and ``@mention`` tokens. A sigil starts a token only at the
start of the text or after a character that is not a word character, ``#`` or ``@``, so
``a#b`` and ``me@site.org`` hold no tags. A token is a word character followed by word
characters, ``.``, ``:``, ``/`` or ``-``, with trailing ``.:/-`` left out (``#hold.`` is ``hold``).

Resolution precedence (``ParsedTag.kind``), first match wins:

1. ``@token``: a mention. ``@party:acme-nde`` carries the namespace ``party``. ``@agent:<id>`` is
   the actor string of an agent (the text is that actor). Mentions are not resolved further.
2. ``#token`` that is a key fitting a numbering pattern of the scope, written exactly as the
   pattern writes it and not glued to other characters (``numbering.detect.detect_keys``). If
   ``resolve`` finds a record the tag is ``record`` with its ``record_id``. If it finds none the
   tag is a ``topic`` (FANOUT decision D2: unresolved record-like tags stay topics).
3. ``#ns:value``: a namespaced code. The namespace is a letter followed by word characters or
   dashes. Codes are stored with their namespace and not resolved (Standards registry: Phase 1).
4. ``#word`` in the signal set (case-insensitive): a signal tag.
5. ``#word`` with at least one letter: a topic. ``#3`` and ``#2026`` are not tags.

Only ``#``-prefixed keys are record tags; a bare key in the body is the composer's business
(key chips, brief 7.2), not a tag. A tag keeps the text as written; feeds match on the lower-cased
text (``tag_key``).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import asdict
from typing import Any

from tl_core.feed.types import DEFAULT_SIGNAL_TAGS, Importance, ParsedTag
from tl_core.numbering.config import NumberingPattern
from tl_core.numbering.detect import KeyMatch, detect_keys

_SIGIL = re.compile(r"(?<![\w@#])[#@](?=\w)")
_BODY = re.compile(r"\w[\w.:/-]*")
_TRAILING = ".:/-"
_NAMESPACE = re.compile(r"[A-Za-z][\w-]*")

Resolver = Callable[[KeyMatch], str | None]


def _namespace_of(token: str) -> str | None:
    """``ns`` of a token written ``ns:value`` (both parts non-empty), else ``None``."""
    namespace, colon, value = token.partition(":")
    if colon and value and _NAMESPACE.fullmatch(namespace):
        return namespace
    return None


def parse_tags(
    text: str,
    *,
    patterns: Sequence[NumberingPattern],
    resolve: Resolver,
    signal_tags: Collection[str] = DEFAULT_SIGNAL_TAGS,
) -> list[ParsedTag]:
    """The tags and mentions of ``text`` in text order, never overlapping.

    ``patterns`` are the numbering patterns that apply to the post's scope. ``resolve`` maps a
    detected key to the id of the record that has it, or ``None``; it is called once per record-like
    tag, in text order. The same tag twice gives two entries.
    """
    keys_at = {match.start: match for match in detect_keys(text, patterns)}
    signals = {word.lower() for word in signal_tags}
    tags: list[ParsedTag] = []
    cursor = 0
    for sigil in _SIGIL.finditer(text):
        start = sigil.start()
        if start < cursor:
            continue
        body_start = start + 1
        is_hash = sigil.group() == "#"

        key = keys_at.get(body_start) if is_hash else None
        if key is not None:
            record_id = resolve(key)
            tags.append(
                ParsedTag(
                    text=key.key,
                    kind="record" if record_id is not None else "topic",
                    start=start,
                    end=key.end,
                    record_id=record_id,
                )
            )
            cursor = key.end
            continue

        found = _BODY.match(text, body_start)
        if found is None:
            continue
        token = found.group().rstrip(_TRAILING)
        if not token:
            continue
        end = body_start + len(token)
        cursor = end
        namespace = _namespace_of(token)
        if not is_hash:
            if any(ch.isalpha() for ch in token):
                tags.append(ParsedTag(token, "mention", start, end, namespace=namespace))
        elif namespace is not None:
            tags.append(ParsedTag(token, "code", start, end, namespace=namespace))
        elif token.lower() in signals:
            tags.append(ParsedTag(token, "signal", start, end))
        elif any(ch.isalpha() for ch in token):
            tags.append(ParsedTag(token, "topic", start, end))
    return tags


def tag_key(tag: ParsedTag) -> str:
    """The text feeds match on: the tag lower-cased."""
    return tag.text.lower()


def record_ids_of(tags: Iterable[ParsedTag]) -> list[str]:
    """Ids of the records the tags resolved to, in text order, without repeats."""
    seen: dict[str, None] = {}
    for tag in tags:
        if tag.kind == "record" and tag.record_id is not None:
            seen.setdefault(tag.record_id)
    return list(seen)


def effective_importance(declared: Importance, tags: Iterable[ParsedTag]) -> Importance:
    """High when any tag is a signal tag (brief 21.3), else the importance the author gave."""
    return "high" if any(tag.kind == "signal" for tag in tags) else declared


def tags_to_payload(tags: Iterable[ParsedTag]) -> list[dict[str, Any]]:
    """Tags as the plain dicts the ``Feed.Posted`` and ``Feed.Edited`` payloads carry."""
    return [asdict(tag) for tag in tags]


def tags_from_payload(items: Iterable[Mapping[str, Any]]) -> tuple[ParsedTag, ...]:
    """Inverse of ``tags_to_payload``."""
    return tuple(
        ParsedTag(
            text=item["text"],
            kind=item["kind"],
            start=item["start"],
            end=item["end"],
            namespace=item.get("namespace"),
            record_id=item.get("record_id"),
        )
        for item in items
    )
