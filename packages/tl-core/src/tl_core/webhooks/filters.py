"""``WebhookFilter``: which outbox rows a subscription wants (brief 18.2, `SubscriptionFilter`).

The LinkML class is ``SubscriptionFilter`` in ``schema/core/integration.yaml``; this is its runtime
form. Every part that is set must match; a part left ``None`` matches everything; an empty list is a
mistake (it would match nothing) and raises ``ValueError``. Globs are
``tl_core.changefeed.filters.glob_match`` (``*``, ``?``, case-sensitive), the same glob the in-
process
change feed uses.

``matches_row`` decides everything that the outbox row itself can answer. ``record_selector`` (a
query-language expression about the subject record's current state) needs the database, so the
dispatcher evaluates it afterwards with ``tl_core.webhooks.dispatch.record_matches``.

Follow-ups, not built: the §18.2 selectors for module, correspondence domain, saved query, clock or
deadline and action have no events to select on yet.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from tl_core.webhooks.rows import OutboxRow

#: ``<from> -> <to>`` with ``*`` wildcards; the arrow may also be written ``→``.
TRANSITION_RE = re.compile(r"^\s*(\S.*?)\s*(?:->|→)\s*(\S.*?)\s*$")
FILTER_KEYS = (
    "scope_selector",
    "event_types",
    "record_selector",
    "record_ids",
    "changed_fields",
    "transitions",
    "link_relations",
    "file_slots",
    "hashtags",
)


def split_transition(entry: str) -> tuple[str, str]:
    """``"InReview -> Issued"`` gives ``("InReview", "Issued")``; ``ValueError`` if malformed."""
    match = TRANSITION_RE.match(entry)
    if match is None:
        raise ValueError(f"a transition is '<from> -> <to>' (use * as a wildcard), got {entry!r}")
    return match.group(1), match.group(2)


def normalise_hashtag(tag: str) -> str:
    """Lower case, without a leading ``#``."""
    return tag.lstrip("#").lower()


@dataclass(frozen=True)
class WebhookFilter:
    scope_selector: str | None = None
    event_types: tuple[str, ...] | None = None
    record_selector: str | None = None
    record_ids: frozenset[str] | None = None
    changed_fields: tuple[str, ...] | None = None
    transitions: tuple[str, ...] | None = None
    link_relations: tuple[str, ...] | None = None
    file_slots: tuple[str, ...] | None = None
    hashtags: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        for name in FILTER_KEYS:
            value = getattr(self, name)
            if value is not None and (isinstance(value, str) and not value.strip()):
                raise ValueError(f"{name} must not be blank; use None to leave it out")
            if value is not None and not isinstance(value, str) and len(value) == 0:
                raise ValueError(f"{name} must not be empty; use None to match everything")
        for entry in self.transitions or ():
            split_transition(entry)

    @staticmethod
    def from_dict(raw: Mapping[str, Any]) -> WebhookFilter:
        """Build from a ``SubscriptionFilter`` JSON object. Unknown keys are an error.

        ``record_selector`` is parsed with the query language so a bad expression is refused when
        the
        subscription is created (``QuerySyntaxError`` is a ``ServiceError``; here it becomes
        ``ValueError`` with the position).
        """
        unknown = sorted(set(raw) - set(FILTER_KEYS))
        if unknown:
            raise ValueError(f"unknown filter field(s): {', '.join(unknown)}")

        def many(name: str) -> tuple[str, ...] | None:
            value = raw.get(name)
            if value is None:
                return None
            if isinstance(value, str) or not all(isinstance(item, str) for item in value):
                raise ValueError(f"{name} must be a list of strings")
            return tuple(value)

        selector = raw.get("record_selector")
        if selector is not None:
            from tl_core.query.api import QuerySyntaxError, parse

            try:
                parse(str(selector))
            except QuerySyntaxError as exc:
                raise ValueError(f"record_selector: {exc} (at character {exc.position})") from exc
        ids = many("record_ids")
        scope = raw.get("scope_selector")
        if scope is not None and not isinstance(scope, str):
            raise ValueError("scope_selector must be a string")
        return WebhookFilter(
            scope_selector=scope,
            event_types=many("event_types"),
            record_selector=None if selector is None else str(selector),
            record_ids=None if ids is None else frozenset(ids),
            changed_fields=many("changed_fields"),
            transitions=many("transitions"),
            link_relations=many("link_relations"),
            file_slots=many("file_slots"),
            hashtags=many("hashtags"),
        )

    def to_dict(self) -> dict[str, Any]:
        """The JSON object form, set parts only, lists sorted where order carries no meaning."""
        out: dict[str, Any] = {}
        for name in FILTER_KEYS:
            value = getattr(self, name)
            if value is None:
                continue
            out[name] = (
                sorted(str(item) for item in cast("frozenset[str]", value))
                if isinstance(value, frozenset)
                else (list(cast("tuple[str, ...]", value)) if isinstance(value, tuple) else value)
            )
        return out

    def matches_row(self, row: OutboxRow) -> bool:
        """Whether ``row`` passes every part of the filter except ``record_selector``.

        STUB (P0-I5-T22): the body raises ``NotImplementedError``.
        """
        raise NotImplementedError
