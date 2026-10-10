"""Feed pane: the activity feed of a project, a record or a hashtag (P0-I6-T04; brief 21.4).

Sketch 6 is the layout. One option per feed item, newest first. A post shows ``author · time``, its
body with `#tags` and `@mentions` highlighted, and a line of reactions and suggestions; an event
card is one line (``▤ jsmith created 14 records (P1-REC-0001, ...) · 09:15``). A tab strip filters
(All, Posts, Events, #hold). The pane reads and writes only through `ClientInterface` and posts
messages for what it cannot do itself: `PostRequested` (the app opens the composer) and
`OpenRecord`.
"""

from __future__ import annotations

from datetime import UTC
from typing import ClassVar, Literal

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option
from tl_core.feed.types import FeedItem, Reaction
from tl_core.services.errors import NoChangesError
from tl_core.services.feed_actions import ReactToPost
from tl_core.services.feed_queries import FeedPage, FeedSuggestion

from tl_tui.client import ClientInterface
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.messages import OpenRecord, StatusMessage

Filter = Literal["all", "posts", "events", "hold"]
FILTERS: tuple[Filter, ...] = ("all", "posts", "events", "hold")
FILTER_LABELS: dict[Filter, str] = {
    "all": "All",
    "posts": "Posts",
    "events": "Events",
    "hold": "#hold",
}
PAGE_SIZE = 50
MAX_LABELS = 3
TAG_STYLES: dict[str, str] = {
    "record": "bold underline",
    "signal": "bold red",
    "code": "bold cyan",
    "topic": "cyan",
    "mention": "magenta",
}


def author_text(actor: str) -> str:
    """``mlee`` for ``user:mlee``; agents read ``agent:triage ⚙``; other actors as they are."""
    if actor.startswith("user:"):
        return actor.removeprefix("user:")
    if actor.startswith("agent:"):
        return f"{actor} ⚙"
    return actor


def clock(item: FeedItem) -> str:
    """``09:42`` (UTC, ``%H:%M``) from the item's time."""
    return item.at.astimezone(UTC).strftime("%H:%M")


def tabs_text(active: Filter) -> str:
    """``[All] Posts Events #hold``: the labels of ``FILTERS`` joined by a space, the active one in
    brackets."""
    return " ".join(f"[{FILTER_LABELS[f]}]" if f == active else FILTER_LABELS[f] for f in FILTERS)


def labels_suffix(item: FeedItem, labels: dict[str, str]) -> str:
    """`` (K1, K2, K3 +2)`` for the item's records that have a label: the first ``MAX_LABELS``
    joined by ``, ``, then `` +N`` for the rest; ``""`` when no record has a label."""
    named = [labels[rid] for rid in item.record_ids if rid in labels]
    if not named:
        return ""
    text = ", ".join(named[:MAX_LABELS])
    if len(named) > MAX_LABELS:
        text += f" +{len(named) - MAX_LABELS}"
    return f" ({text})"


def reactions_line(item: FeedItem, suggestions: list[FeedSuggestion]) -> str:
    """``+1 1 · ack 3 · proposal: constraint on FV-1001 [a]``.

    Parts joined by `` · ``: ``<reaction> <count>`` for each reaction, sorted by reaction name, then
    ``proposal: constraint on <record_key or record_id> [a]`` for each suggestion. ``""`` when
    there are none.
    """
    parts = [f"{name} {count}" for name, count in sorted(item.reactions.items())]
    parts += [f"proposal: constraint on {s.record_key or s.record_id} [a]" for s in suggestions]
    return " · ".join(parts)


def item_text(item: FeedItem, labels: dict[str, str], suggestions: list[FeedSuggestion]) -> Text:
    """The option text of one item (a `rich.text.Text`, so brackets are never markup).

    A card is one line, dim: ``▤ <summary><labels_suffix> · <clock>``.

    A post is ``<author_text> · <clock>`` (bold; with `` !`` appended for high importance unless
    retracted), a newline, then the body. A retracted post shows its summary (``[retracted]``) dim
    and italic. Otherwise each tag of the item is styled in the body with ``TAG_STYLES[tag.kind]``
    over ``tag.start`` to ``tag.end``. When ``reactions_line`` is not empty add a newline, two
    spaces and the line, dim.
    """
    if item.item_type == "card":
        line = f"▤ {item.summary}{labels_suffix(item, labels)} · {clock(item)}"
        return Text(line, style="dim")
    head = f"{author_text(item.actor)} · {clock(item)}"
    if item.importance == "high" and not item.retracted:
        head += " !"
    text = Text(head)
    text.stylize("bold", 0, len(head))
    text.append("\n")
    body = len(text.plain)
    if item.retracted:
        text.append(item.summary, style="dim italic")
    else:
        text.append(item.summary)
        for tag in item.tags:
            text.stylize(TAG_STYLES[tag.kind], body + tag.start, body + tag.end)
    reactions = reactions_line(item, suggestions)
    if reactions:
        text.append(f"\n  {reactions}", style="dim")
    return text


class PostRequested(Message):
    """The user pressed `p`: the app should open the composer."""

    def __init__(self, record_key: str | None) -> None:
        super().__init__()
        self.record_key = record_key


class FeedPane(Vertical):
    """The feed of ``scope``; with ``record_id`` the feed of that record, with ``tag`` a hashtag."""

    KEY_HINTS: ClassVar[str] = (
        "j/k move  Enter/o open record  p post  . ack  + like  x resolved  "
        "1-4 filter  L linked  t thread  f follow  r reload"
    )
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("j", "move(1)", "Down", show=False),
        Binding("k", "move(-1)", "Up", show=False),
        Binding("o", "open", "Open", show=False),
        Binding("p", "post", "Post", show=False),
        Binding("full_stop", "react('ack')", "Ack", show=False),
        Binding("plus", "react('+1')", "Like", show=False),
        Binding("x", "react('resolved')", "Resolved", show=False),
        Binding("1", "filter('all')", "All", show=False),
        Binding("2", "filter('posts')", "Posts", show=False),
        Binding("3", "filter('events')", "Events", show=False),
        Binding("4", "filter('hold')", "#hold", show=False),
        Binding("L", "toggle_linked", "Linked", show=False),
        Binding("t", "thread", "Thread", show=False),
        Binding("f", "follow", "Follow", show=False),
        Binding("a", "accept", "Accept", show=False),
        Binding("r", "reload", "Reload", show=False),
    ]

    def __init__(
        self,
        client: ClientInterface,
        scope: str,
        *,
        record_id: str | None = None,
        record_key: str | None = None,
        tag: str | None = None,
        actor: str = "user:dev",
        page_size: int = PAGE_SIZE,
        id: str | None = None,  # noqa: A002
    ) -> None:
        super().__init__(id=id)
        self.client = client
        self.scope = scope
        self.record_id = record_id
        self.record_key = record_key
        self.tag = tag
        self.actor = actor
        self.page_size = page_size
        self.active: Filter = "all"
        self.include_linked = False
        self.items: list[FeedItem] = []
        self.labels: dict[str, str] = {}
        self.suggestions: dict[str, list[FeedSuggestion]] = {}
        self.next_before: int | None = None

    def compose(self) -> ComposeResult:
        """Three children: a `Static` ``#feed-title`` and a `Static` ``#feed-tabs`` (both with
        ``markup=False``), then an `OptionList` ``#feed-list``."""
        yield Static("", id="feed-title", markup=False)
        yield Static("", id="feed-tabs", markup=False)
        yield OptionList(id="feed-list")

    def on_mount(self) -> None:
        """``reload``."""
        self.reload()

    def focus(self, scroll_visible: bool = True) -> FeedPane:
        """Focus the option list (the pane itself takes no focus) and return the pane."""
        self.query_one("#feed-list", OptionList).focus(scroll_visible)
        return self

    @property
    def highlighted_item(self) -> FeedItem | None:
        """The item under the option list's highlight, ``None`` when nothing is highlighted."""
        index = self.query_one("#feed-list", OptionList).highlighted
        if index is None or index >= len(self.items):
            return None
        return self.items[index]

    def _fetch(self, before_seq: int | None) -> FeedPage:
        """One page of the feed for the active filter; raises the client's errors."""
        item_type: Literal["post", "card"] | None = None
        tag = self.tag
        if self.active == "posts":
            item_type = "post"
        elif self.active == "events":
            item_type = "card"
        elif self.active == "hold":
            tag = "hold"
        return self.client.feed_page(
            self.scope,
            record_id=self.record_id,
            include_linked=self.include_linked,
            tag=tag,
            item_type=item_type,
            limit=self.page_size,
            before_seq=before_seq,
        )

    def _highlight_id(self) -> str | None:
        item = self.highlighted_item
        return None if item is None else item.id

    def _title(self) -> str:
        title = f"Feed · {self.scope.removeprefix('project:')}"
        if self.record_id is not None:
            title += f" · record {self.record_key or self.record_id}"
            if self.include_linked:
                title += " · + linked"
        if self.tag:
            title += f" · {self.tag}" if self.tag.startswith("@") else f" · #{self.tag.lstrip('#')}"
        return title

    def _show(self, keep: str | None) -> None:
        """Redraw title, tabs and list; the highlight goes to item ``keep`` when it is listed."""
        self.query_one("#feed-title", Static).update(self._title())
        self.query_one("#feed-tabs", Static).update(tabs_text(self.active))
        options = self.query_one("#feed-list", OptionList)
        if not self.items:
            options.set_options([Option(Text("Nothing here yet. Press p to post.", style="dim"))])
            return
        options.set_options(
            [
                Option(item_text(i, self.labels, self.suggestions.get(i.id, [])), id=i.id)
                for i in self.items
            ]
        )
        options.highlighted = next((n for n, i in enumerate(self.items) if i.id == keep), 0)

    def reload(self) -> None:
        """Fetch the first page again and show it, keeping the highlight on the same item id when
        it is still listed, else on the first.

        The fetch is ``client.feed_page(scope, record_id=..., include_linked=..., tag=...,
        item_type=..., limit=page_size, before_seq=...)``. The filter decides: ``posts`` is
        ``item_type="post"``, ``events`` is ``"card"``, ``hold`` sets ``tag="hold"`` (otherwise the
        pane's own ``tag``). Store ``items``, ``labels``, ``suggestions`` and ``next_before`` from
        the page. A client error (``CLIENT_ERRORS``) posts ``StatusMessage(describe_error(exc),
        "error")`` and keeps what is shown. Update ``#feed-title`` and ``#feed-tabs``: the title is
        ``Feed · <scope without "project:">``, then `` · record <key or id>`` for a record feed
        (with `` · + linked`` when ``include_linked``), then `` · #tag`` (or the ``@mention``) for a
        tag feed. The list has one `Option(item_text(...), id=item.id)` per item; with no items it
        holds one dim option ``Nothing here yet. Press p to post.`` and no highlight.
        """
        keep = self._highlight_id()
        try:
            page = self._fetch(None)
        except CLIENT_ERRORS as exc:
            self.post_message(StatusMessage(describe_error(exc), "error"))
            return
        self.items = list(page.items)
        self.labels = dict(page.labels)
        self.suggestions = dict(page.suggestions)
        self.next_before = page.next_before
        self._show(keep)

    def load_more(self) -> bool:
        """Append the page that follows (``before_seq=next_before``) to ``items``, ``labels`` and
        ``suggestions``, keep the highlight, redraw, and return True; False when ``next_before`` is
        None or the fetch failed.
        """
        if self.next_before is None:
            return False
        try:
            page = self._fetch(self.next_before)
        except CLIENT_ERRORS as exc:
            self.post_message(StatusMessage(describe_error(exc), "error"))
            return False
        keep = self._highlight_id()
        self.items.extend(page.items)
        self.labels.update(page.labels)
        self.suggestions.update(page.suggestions)
        self.next_before = page.next_before
        self._show(keep)
        return True

    def action_move(self, delta: int) -> None:
        """Move the highlight by ``delta`` (j: +1, k: -1), clamped to the items. Moving down from
        the last item calls ``load_more`` and, when a page came, moves onto its first item. No
        items: do nothing.
        """
        if not self.items:
            return
        options = self.query_one("#feed-list", OptionList)
        current = options.highlighted or 0
        if delta > 0 and current >= len(self.items) - 1:
            before = len(self.items)
            if not self.load_more():
                return
            target = before
        else:
            target = current + delta
        options.highlighted = max(0, min(target, len(self.items) - 1))

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Enter on an option: stop the event and do what ``o`` does."""
        event.stop()
        self.action_open()

    def action_open(self) -> None:
        """Post ``OpenRecord(record["scope"], record["key"], follow=True)`` for the first record of
        the highlighted item; the record comes from ``client.get_record_by_id``. Nothing
        highlighted: do nothing. The item has no record: say "This item references no record"
        (info). The client finds no record or it has no key: say "The referenced record is not
        available" (warning). "Say" means post a ``StatusMessage``.
        """
        item = self.highlighted_item
        if item is None:
            return
        if not item.record_ids:
            self.post_message(StatusMessage("This item references no record", "info"))
            return
        try:
            record = self.client.get_record_by_id(item.record_ids[0])
        except CLIENT_ERRORS as exc:
            self.post_message(StatusMessage(describe_error(exc), "error"))
            return
        if record is None or not record.get("key"):
            self.post_message(StatusMessage("The referenced record is not available", "warning"))
            return
        self.post_message(OpenRecord(record["scope"], record["key"], follow=True))

    def action_post(self) -> None:
        """Post ``PostRequested(self.record_key)``."""
        self.post_message(PostRequested(self.record_key))

    def action_react(self, reaction: Reaction) -> None:
        """Toggle ``reaction`` on the highlighted post for ``self.actor``.

        Send ``client.feed_react(ReactToPost(actor=self.actor, source="tui", scope=self.scope,
        post_id=..., reaction=reaction, on=True))``. If it raises ``NoChangesError`` the actor
        already has the reaction, so send the same command with ``on=False``. Any other
        ``CLIENT_ERRORS`` error: say ``describe_error`` (error) and stop. After success ``reload``.
        On a card, or with nothing highlighted, say "Reactions go on posts" (info).
        """
        item = self.highlighted_item
        if item is None or item.item_type != "post":
            self.post_message(StatusMessage("Reactions go on posts", "info"))
            return
        post_id = item.id

        def send(on: bool) -> None:
            self.client.feed_react(
                ReactToPost(
                    actor=self.actor,
                    source="tui",
                    scope=self.scope,
                    post_id=post_id,
                    reaction=reaction,
                    on=on,
                )
            )

        try:
            try:
                send(True)
            except NoChangesError:
                send(False)
        except CLIENT_ERRORS as exc:
            self.post_message(StatusMessage(describe_error(exc), "error"))
            return
        self.reload()

    def action_filter(self, name: Filter) -> None:
        """Make ``name`` the active filter and ``reload``."""
        self.active = name
        self.reload()

    def action_toggle_linked(self) -> None:
        """Flip ``include_linked`` and ``reload``. Outside a record feed (no ``record_id``) say
        "Linked records apply to a record's feed" (info) and change nothing.
        """
        if self.record_id is None:
            self.post_message(StatusMessage("Linked records apply to a record's feed", "info"))
            return
        self.include_linked = not self.include_linked
        self.reload()

    def action_thread(self) -> None:
        """Say "Threads are switched off for this project" (info)."""
        self.post_message(StatusMessage("Threads are switched off for this project", "info"))

    def action_follow(self) -> None:
        """Say "Following arrives with the settings screen" (info)."""
        self.post_message(StatusMessage("Following arrives with the settings screen", "info"))

    def action_accept(self) -> None:
        """On an item that has a suggestion say "Constraint proposals arrive with the review queue"
        (info); otherwise say "No suggestion on this item" (info). Nothing is created in Phase 0.
        """
        item = self.highlighted_item
        if item is not None and self.suggestions.get(item.id):
            text = "Constraint proposals arrive with the review queue"
        else:
            text = "No suggestion on this item"
        self.post_message(StatusMessage(text, "info"))

    def action_reload(self) -> None:
        """``reload``."""
        self.reload()
