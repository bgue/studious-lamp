"""Feed behaviour of `FakeClient` (P0-I6), kept apart so `fakes.py` stays readable.

The fake keeps feed items as real `FeedItem` objects and follows the real rules where they are
cheap: the real tag parser (with `key_patterns` and the fake records), the real effective
importance, the real error types, and `[retracted]` as the summary of a tombstone. It simplifies the
rest: no ledger events (results carry an empty `events` list), no link suggestions, event cards only
exist when a test seeds them with `seed_card`, and completion is a plain prefix match.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, Protocol

from tl_core.feed.config import reactions_enabled, signal_tags
from tl_core.feed.tags import effective_importance, parse_tags, record_ids_of, tag_key
from tl_core.feed.types import FeedItem, Importance, ParsedTag, TagKind
from tl_core.numbering.config import NumberingPattern
from tl_core.numbering.detect import KeyMatch
from tl_core.services.commands import CommandResult
from tl_core.services.errors import (
    InvalidScopeError,
    NoChangesError,
    PostNotFoundError,
    PostRetractedError,
    ReactionsDisabledError,
)
from tl_core.services.feed import EditPost, PostToFeed
from tl_core.services.feed_actions import ReactToPost, RetractPost
from tl_core.services.feed_queries import Completion, FeedPage, FeedSuggestion

_FEED_T0 = datetime(2026, 10, 9, 9, 0, 0, tzinfo=UTC)
PREVIEW_LABEL = 80


class _FeedHost(Protocol):
    calls: list[str]
    _records: dict[str, dict[str, Any]]
    _links: dict[str, dict[str, Any]]
    key_patterns: list[NumberingPattern]


class FakeFeedSupport:
    """Mixin for `FakeClient`: call `_init_feed()` from its `__init__`."""

    def _init_feed(self) -> None:
        self._feed: dict[str, FeedItem] = {}
        self._feed_n = 0
        self._reactors: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
        self.feed_commands: list[Any] = []

    def _fhost(self) -> _FeedHost:
        return self  # type: ignore[return-value]

    def _next_feed_id(self, prefix: str) -> tuple[str, int, datetime]:
        self._feed_n += 1
        return (
            f"{prefix}{self._feed_n:024d}",
            self._feed_n,
            _FEED_T0 + timedelta(minutes=self._feed_n),
        )

    # --- seeding ----------------------------------------------------------------------------

    def seed_card(
        self,
        summary: str,
        *,
        scope: str = "project:P123",
        actor: str = "user:jsmith",
        record_ids: tuple[str, ...] = (),
        event_count: int = 1,
    ) -> FeedItem:
        """Add an event card (the fake makes no cards by itself)."""
        item_id, seq, at = self._next_feed_id("CARD")
        item = FeedItem(
            id=item_id,
            item_type="card",
            scope=scope,
            actor=actor,
            at=at,
            seq=seq,
            summary=summary,
            importance="low",
            record_ids=record_ids,
            event_count=event_count,
        )
        self._feed[item_id] = item
        return item

    def seed_post(self, body: str, *, scope: str = "project:P123", actor: str = "user:mlee") -> str:
        """Add a post as `feed_post` would and return its id."""
        cmd = PostToFeed(actor=actor, source="tui", scope=scope, body=body)
        return self.feed_post(cmd).stream_id

    # --- parsing ----------------------------------------------------------------------------

    def _parse(self, scope: str, body: str) -> list[ParsedTag]:
        host = self._fhost()
        by_key = {r["key"]: r["id"] for r in host._records.values() if r["scope"] == scope}

        def resolve(match: KeyMatch) -> str | None:
            return by_key.get(match.key)

        return parse_tags(
            body, patterns=host.key_patterns, resolve=resolve, signal_tags=signal_tags()
        )

    def _post_item(
        self, base: FeedItem | None, cmd_scope: str, actor: str, body: str, declared: Importance
    ) -> FeedItem:
        tags = self._parse(cmd_scope, body)
        fields: dict[str, Any] = {
            "summary": body,
            "tags": tuple(tags),
            "record_ids": tuple(record_ids_of(tags)),
            "importance": effective_importance(declared, tags),
        }
        if base is not None:
            return replace(base, **fields)
        item_id, seq, at = self._next_feed_id("POST")
        return FeedItem(
            id=item_id, item_type="post", scope=cmd_scope, actor=actor, at=at, seq=seq, **fields
        )

    # --- commands ---------------------------------------------------------------------------

    def feed_post(self, cmd: PostToFeed) -> CommandResult:
        self._fhost().calls.append("feed_post")
        self.feed_commands.append(cmd)
        if not cmd.scope.startswith("project:"):
            raise InvalidScopeError(f"a post belongs to a project; scope {cmd.scope!r} is not one")
        item = self._post_item(None, cmd.scope, cmd.actor, cmd.body, cmd.importance)
        self._feed[item.id] = item
        return CommandResult(stream_id=item.id, key=None, version=1, events=[])

    def _post(self, scope: str, post_id: str) -> FeedItem:
        item = self._feed.get(post_id)
        if item is None or item.item_type != "post" or item.scope != scope:
            raise PostNotFoundError(f"no post {post_id!r} in scope {scope!r}")
        return item

    def feed_edit(self, cmd: EditPost) -> CommandResult:
        self._fhost().calls.append("feed_edit")
        self.feed_commands.append(cmd)
        item = self._post(cmd.scope, cmd.post_id)
        if item.retracted:
            raise PostRetractedError(f"post {cmd.post_id!r} was retracted and cannot be edited")
        if item.summary == cmd.body:
            raise NoChangesError(f"the body of post {cmd.post_id!r} is already that text")
        self._feed[item.id] = self._post_item(item, cmd.scope, item.actor, cmd.body, "normal")
        return CommandResult(stream_id=item.id, key=None, version=2, events=[])

    def feed_retract(self, cmd: RetractPost) -> CommandResult:
        self._fhost().calls.append("feed_retract")
        self.feed_commands.append(cmd)
        item = self._post(cmd.scope, cmd.post_id)
        if item.retracted:
            raise PostRetractedError(f"post {cmd.post_id!r} was already retracted")
        kept = tuple(t for t in item.tags if t.kind == "record")
        self._feed[item.id] = replace(item, summary="[retracted]", retracted=True, tags=kept)
        return CommandResult(stream_id=item.id, key=None, version=2, events=[])

    def feed_react(self, cmd: ReactToPost) -> CommandResult:
        self._fhost().calls.append("feed_react")
        self.feed_commands.append(cmd)
        if not reactions_enabled():
            raise ReactionsDisabledError("reactions are switched off")
        item = self._post(cmd.scope, cmd.post_id)
        if item.retracted:
            raise PostRetractedError(f"post {cmd.post_id!r} was retracted")
        actors = self._reactors[item.id][cmd.reaction]
        if (cmd.actor in actors) == cmd.on:
            raise NoChangesError(f"{cmd.actor} already has that reaction state on {cmd.post_id!r}")
        if cmd.on:
            actors.add(cmd.actor)
        else:
            actors.discard(cmd.actor)
        counts = {r: len(a) for r, a in self._reactors[item.id].items() if a}
        self._feed[item.id] = replace(item, reactions=counts)
        return CommandResult(stream_id=item.id, key=None, version=2, events=[])

    # --- queries ----------------------------------------------------------------------------

    def _linked_ids(self, record_id: str) -> set[str]:
        found: set[str] = set()
        for row in self._fhost()._links.values():
            if row["status"] in ("retracted", "suggested"):
                continue
            if row["from_id"] == record_id:
                found.add(row["to_id"])
            elif row["to_id"] == record_id:
                found.add(row["from_id"])
        return found

    def _suggestions(self, items: list[FeedItem]) -> dict[str, list[FeedSuggestion]]:
        found: dict[str, list[FeedSuggestion]] = {}
        records = self._fhost()._records
        for item in items:
            if item.item_type != "post" or item.retracted:
                continue
            if not any(t.kind == "signal" and tag_key(t) == "hold" for t in item.tags):
                continue
            for record_id in item.record_ids:
                key = records[record_id]["key"] if record_id in records else None
                found.setdefault(item.id, []).append(
                    FeedSuggestion(
                        item_id=item.id,
                        kind="constraint",
                        record_id=record_id,
                        record_key=key,
                        prompt=f"Create a constraint on {key or record_id}?",
                    )
                )
        return found

    def feed_page(
        self,
        scope: str,
        *,
        record_id: str | None = None,
        include_linked: bool = False,
        tag: str | None = None,
        item_type: Literal["post", "card"] | None = None,
        limit: int = 50,
        before_seq: int | None = None,
    ) -> FeedPage:
        self._fhost().calls.append("feed_page")
        wanted = {record_id} if record_id else set()
        if record_id and include_linked:
            wanted |= self._linked_ids(record_id)
        mention = tag.startswith("@") if tag else False
        needle = tag.lstrip("#@").lower() if tag else None

        def matches(item: FeedItem) -> bool:
            if item.scope != scope or (item_type and item.item_type != item_type):
                return False
            if before_seq is not None and item.seq >= before_seq:
                return False
            if wanted and not wanted & set(item.record_ids):
                return False
            if needle is not None:
                return any(
                    (t.kind == "mention") == mention and tag_key(t) == needle for t in item.tags
                )
            return True

        ordered = sorted(
            (i for i in self._feed.values() if matches(i)), key=lambda i: (i.at, i.seq)
        )
        ordered.reverse()
        items = ordered[:limit]
        records = self._fhost()._records
        labels = {
            rid: records[rid]["key"] or records[rid]["title"]
            for item in items
            for rid in item.record_ids
            if rid in records
        }
        return FeedPage(
            items=items,
            labels=labels,
            suggestions=self._suggestions(items),
            next_before=items[-1].seq if len(ordered) > limit else None,
        )

    def feed_complete(
        self, scope: str, sigil: Literal["#", "@"], prefix: str, *, limit: int = 8
    ) -> list[Completion]:
        self._fhost().calls.append("feed_complete")
        low = prefix.lower()
        found: list[Completion] = []
        if sigil == "#":
            for r in self._fhost()._records.values():
                if r["scope"] == scope and r["key"] and r["key"].lower().startswith(low):
                    found.append(Completion(r["key"], "record", r["title"]))
            for word in signal_tags():
                if word.startswith(low):
                    found.append(Completion(word, "signal", "signal tag"))
            used: dict[str, TagKind] = {}
            for item in self._feed.values():
                for t in item.tags:
                    if t.kind in ("code", "topic"):
                        used[tag_key(t)] = t.kind
            found += [
                Completion(k, kind, "used") for k, kind in sorted(used.items()) if k.startswith(low)
            ]
        else:
            tags = [t for item in self._feed.values() for t in item.tags]
            mentions = sorted({tag_key(t) for t in tags if t.kind == "mention"})
            found += [Completion(m, "mention", "used") for m in mentions if m.startswith(low)]
            authors = {
                i.actor.removeprefix("user:") for i in self._feed.values() if i.item_type == "post"
            }
            seen = {c.text for c in found}
            found += [
                Completion(p, "mention", "agent" if p.startswith("agent:") else "person")
                for p in sorted(authors)
                if p.lower().startswith(low) and p not in seen
            ]
        return found[:limit]
