"""Feed pane: rendering, keys, filters and paging on the fake client (P0-I6-T04). Provided."""

from __future__ import annotations

from typing import Any

from fakes import SCOPE, FakeClient
from helpers import run_pilot, screen_text
from textual.app import App, ComposeResult
from textual.message import Message
from textual.pilot import Pilot
from tl_core.feed.types import FeedItem, ParsedTag
from tl_core.services.feed_actions import ReactToPost
from tl_core.services.feed_queries import FeedSuggestion
from tl_tui.messages import OpenRecord, StatusMessage
from tl_tui.widgets.feed_pane import (
    FeedPane,
    PostRequested,
    author_text,
    item_text,
    labels_suffix,
    reactions_line,
    tabs_text,
)


class Host(App[None]):
    def __init__(self, client: FakeClient, **kw: Any) -> None:
        super().__init__()
        self.client = client
        self.kw = kw
        self.seen: list[Message] = []

    def compose(self) -> ComposeResult:
        yield FeedPane(self.client, SCOPE, actor="user:me", id="feed", **self.kw)

    def on_mount(self) -> None:
        self.query_one(FeedPane).focus()

    def on_open_record(self, message: OpenRecord) -> None:
        self.seen.append(message)

    def on_status_message(self, message: StatusMessage) -> None:
        self.seen.append(message)

    def on_post_requested(self, message: PostRequested) -> None:
        self.seen.append(message)

    def pane(self) -> FeedPane:
        return self.query_one(FeedPane)


def seeded() -> FakeClient:
    client = FakeClient.with_valve_example()
    client.seed_card("jsmith created 14 records", record_ids=())
    client.seed_post("Spool arrived #FV-1001 #hold @party:fab-a", actor="user:mlee")
    client.seed_post("Classified 3 letters #fyi", actor="agent:triage")
    return client


def tag(text: str, kind: Any, start: int, end: int) -> ParsedTag:
    return ParsedTag(text=text, kind=kind, start=start, end=end)


def item(**kw: Any) -> FeedItem:
    from datetime import UTC, datetime

    base: dict[str, Any] = {
        "id": "P1",
        "item_type": "post",
        "scope": SCOPE,
        "actor": "user:mlee",
        "at": datetime(2026, 10, 9, 9, 42, tzinfo=UTC),
        "seq": 1,
        "summary": "hello",
        "importance": "normal",
    }
    base.update(kw)
    return FeedItem(**base)


# --- pure text --------------------------------------------------------------------------------


def test_author_text() -> None:
    assert author_text("user:mlee") == "mlee"
    assert author_text("agent:triage") == "agent:triage ⚙"
    assert author_text("svc:importer") == "svc:importer"


def test_tabs_text_brackets_the_active_filter() -> None:
    assert tabs_text("all") == "[All] Posts Events #hold"
    assert tabs_text("hold") == "All Posts Events [#hold]"


def test_labels_suffix() -> None:
    card = item(item_type="card", record_ids=("a", "b", "c", "d", "e"))
    labels = {"a": "K1", "b": "K2", "c": "K3", "d": "K4", "e": "K5"}
    assert labels_suffix(card, labels) == " (K1, K2, K3 +2)"
    assert labels_suffix(item(item_type="card", record_ids=("a",)), labels) == " (K1)"
    assert labels_suffix(item(item_type="card"), labels) == ""


def test_reactions_line() -> None:
    suggestion = FeedSuggestion(
        "P1", "constraint", "r1", "FV-1001", "Create a constraint on FV-1001?"
    )
    assert reactions_line(item(reactions={"ack": 3, "+1": 1}), [suggestion]) == (
        "+1 1 · ack 3 · proposal: constraint on FV-1001 [a]"
    )
    assert reactions_line(item(), []) == ""


def test_item_text_of_a_post_highlights_tags_and_escapes_markup() -> None:
    post = item(summary="see [x] #hold now", tags=(tag("hold", "signal", 8, 13),))
    text = item_text(post, {}, [])
    assert text.plain == "mlee · 09:42\nsee [x] #hold now"
    assert [(s.start - 13, s.end - 13, str(s.style)) for s in text.spans if s.start >= 13] == [
        (8, 13, "bold red")
    ]


def test_item_text_of_cards_tombstones_and_important_posts() -> None:
    card = item(item_type="card", summary="jo created 2 records", record_ids=("a",))
    assert item_text(card, {"a": "K1"}, []).plain == "▤ jo created 2 records (K1) · 09:42"
    gone = item(summary="[retracted]", retracted=True, importance="high")
    assert item_text(gone, {}, []).plain == "mlee · 09:42\n[retracted]"
    urgent = item(importance="high", reactions={"ack": 2})
    assert item_text(urgent, {}, []).plain == "mlee · 09:42 !\nhello\n  ack 2"


# --- the widget -------------------------------------------------------------------------------


def test_the_pane_lists_posts_and_cards_newest_first_with_a_title_and_tabs() -> None:
    app = Host(seeded())

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        screen = screen_text(app)
        assert "Feed · P123" in screen and "[All] Posts Events #hold" in screen
        assert (
            screen.index("agent:triage ⚙") < screen.index("mlee") < screen.index("▤ jsmith created")
        )
        assert "Spool arrived #FV-1001 #hold @party:fab-a" in screen
        assert "proposal: constraint on FV-1001 [a]" in screen

    run_pilot(app, scenario)


def test_j_and_k_move_the_highlight_and_the_end_stops() -> None:
    app = Host(seeded())

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        pane = app.pane()
        assert pane.highlighted_item is not None and pane.highlighted_item.actor == "agent:triage"
        await pilot.press("j")
        assert pane.highlighted_item is not None and pane.highlighted_item.actor == "user:mlee"
        await pilot.press("j", "j", "j")
        assert pane.highlighted_item is not None and pane.highlighted_item.item_type == "card"
        await pilot.press("k")
        assert pane.highlighted_item is not None and pane.highlighted_item.actor == "user:mlee"

    run_pilot(app, scenario)


def test_filters_reload_with_the_right_arguments() -> None:
    client = seeded()
    app = Host(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        pane = app.pane()
        await pilot.press("2")
        assert [i.item_type for i in pane.items] == ["post", "post"]
        await pilot.press("3")
        assert [i.item_type for i in pane.items] == ["card"]
        await pilot.press("4")
        assert [i.actor for i in pane.items] == ["user:mlee"]
        assert "All Posts Events [#hold]" in screen_text(app)
        await pilot.press("1")
        assert len(pane.items) == 3

    run_pilot(app, scenario)


def test_dot_toggles_an_ack_for_the_acting_user() -> None:
    client = seeded()
    app = Host(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("j")  # mlee's post
        await pilot.press("full_stop")
        sent = [c for c in client.feed_commands if isinstance(c, ReactToPost)]
        assert [(c.actor, c.reaction, c.on, c.source) for c in sent] == [
            ("user:me", "ack", True, "tui")
        ]
        assert "ack 1" in screen_text(app)
        await pilot.press("full_stop")  # already set: the pane clears it
        sent = [c for c in client.feed_commands if isinstance(c, ReactToPost)]
        assert [c.on for c in sent] == [True, True, False]
        assert "ack 1" not in screen_text(app)
        await pilot.press("plus")
        assert "+1 1" in screen_text(app)

    run_pilot(app, scenario)


def test_reacting_to_a_card_says_so() -> None:
    app = Host(seeded())

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("j", "j", "full_stop")
        statuses = [m for m in app.seen if isinstance(m, StatusMessage)]
        assert statuses and "posts" in statuses[-1].text

    run_pilot(app, scenario)


def test_o_and_enter_open_the_first_referenced_record() -> None:
    client = seeded()
    app = Host(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("j", "o")
        opened = [m for m in app.seen if isinstance(m, OpenRecord)]
        assert [(m.scope, m.key, m.follow) for m in opened] == [(SCOPE, "FV-1001", True)]
        await pilot.press("enter")
        assert len([m for m in app.seen if isinstance(m, OpenRecord)]) == 2
        await pilot.press("k", "o")  # the agent's post references no record
        statuses = [m for m in app.seen if isinstance(m, StatusMessage)]
        assert statuses and "no record" in statuses[-1].text

    run_pilot(app, scenario)


def test_p_asks_the_app_for_the_composer() -> None:
    app = Host(seeded(), record_key="FV-1001")

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("p")
        requests = [m for m in app.seen if isinstance(m, PostRequested)]
        assert [m.record_key for m in requests] == ["FV-1001"]

    run_pilot(app, scenario)


def test_t_f_and_a_are_explained_not_silent() -> None:
    app = Host(seeded())

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("t", "f")
        texts = [m.text for m in app.seen if isinstance(m, StatusMessage)]
        assert any("Threads" in t for t in texts) and any("Following" in t for t in texts)
        await pilot.press("j", "a")  # mlee's post has the #hold suggestion
        assert "review queue" in [m.text for m in app.seen if isinstance(m, StatusMessage)][-1]
        await pilot.press("k", "a")
        assert "No suggestion" in [m.text for m in app.seen if isinstance(m, StatusMessage)][-1]

    run_pilot(app, scenario)


def test_a_record_feed_passes_the_record_and_toggles_linked_records() -> None:
    client = seeded()
    valve = client.get_record(SCOPE, "FV-1001")
    assert valve is not None
    app = Host(client, record_id=valve["id"], record_key="FV-1001")

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        pane = app.pane()
        assert [i.actor for i in pane.items] == ["user:mlee"]
        assert "record FV-1001" in screen_text(app)
        await pilot.press("L")
        assert pane.include_linked and "+ linked" in screen_text(app)
        await pilot.press("L")
        assert not pane.include_linked

    run_pilot(app, scenario)


def test_l_outside_a_record_feed_is_explained() -> None:
    app = Host(seeded())

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("L")
        assert "record's feed" in [m.text for m in app.seen if isinstance(m, StatusMessage)][-1]
        assert not app.pane().include_linked

    run_pilot(app, scenario)


def test_moving_past_the_last_item_loads_the_next_page() -> None:
    client = FakeClient.with_valve_example()
    for n in range(5):
        client.seed_post(f"post {n}")
    app = Host(client, page_size=2)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        pane = app.pane()
        assert len(pane.items) == 2 and pane.next_before is not None
        await pilot.press("j", "j")
        assert len(pane.items) == 4
        await pilot.press("j", "j", "j")
        assert len(pane.items) == 5 and pane.next_before is None
        assert pane.highlighted_item is not None and pane.highlighted_item.summary == "post 0"

    run_pilot(app, scenario)


def test_an_empty_feed_says_how_to_start() -> None:
    app = Host(FakeClient())

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        assert "Nothing here yet" in screen_text(app)
        await pilot.press("j", "k", "o")  # nothing to move on, nothing to open

    run_pilot(app, scenario)


def test_a_client_error_is_shown_not_raised() -> None:
    client = seeded()

    def broken(*_: Any, **__: Any) -> Any:
        from tl_core.services.errors import InvalidScopeError

        raise InvalidScopeError("no such project")

    client.feed_page = broken  # type: ignore[method-assign]
    app = Host(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        errors = [m for m in app.seen if isinstance(m, StatusMessage)]
        assert errors and errors[0].severity == "error" and "no such project" in errors[0].text

    run_pilot(app, scenario)
