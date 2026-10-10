"""`RemoteClient` over a real API server on loopback (the tl-api test harness, nothing mocked).

The API client's own round-trip test proves the answers equal the embedded client's. These tests
prove what the adapter adds: every interface method is served with the same signature, relations
are converted, errors keep their classes and are in CLIENT_ERRORS, own writes are noted, and an
unreachable server is reported as a state and an exception a screen can show.
"""

from __future__ import annotations

import inspect
from typing import Any

import pytest
from harness import Harness
from remote_support import SCOPE, free_port
from tl_api.client.base import ApiUnavailableError
from tl_core.ledger import ConcurrencyError
from tl_core.query import QuerySyntaxError
from tl_core.services.commands import CreateRecord, UpdateRecord
from tl_core.services.errors import RecordNotFoundError
from tl_tui.client import ClientInterface, RelationInfo
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.remote import RemoteClient

INTERFACE_METHODS = [
    name
    for name, member in vars(ClientInterface).items()
    if callable(member) and not name.startswith("_")
]


def create_cmd(key: str = "R-1") -> CreateRecord:
    return CreateRecord(
        actor="user:ignored",
        source="tui",
        scope=SCOPE,
        record_type="core.Record",
        key=key,
        title=f"Record {key}",
    )


def test_every_interface_method_is_served_with_its_signature(harness: Harness) -> None:
    assert len(INTERFACE_METHODS) >= 30
    remote = RemoteClient(harness.api())
    for name in INTERFACE_METHODS:
        served = getattr(remote, name)
        assert callable(served), name
        expected = inspect.signature(getattr(ClientInterface, name))
        got = inspect.signature(served)
        want = [
            (p.name, p.kind, p.default) for p in expected.parameters.values() if p.name != "self"
        ]
        have = [(p.name, p.kind, p.default) for p in got.parameters.values()]
        assert have == want, name


def test_relations_are_converted_to_the_tui_type(harness: Harness) -> None:
    relations = RemoteClient(harness.api()).relations()
    assert relations and all(type(r) is RelationInfo for r in relations)
    assert {"code", "label", "inverse_code", "inverse_label"} == set(RelationInfo.model_fields)


def test_a_live_server_answers_reads_commands_queries_and_errors(harness: Harness) -> None:
    with harness.live() as server:
        remote = RemoteClient.connect(server.base_url, server.token)
        try:
            made = remote.create_record(create_cmd("R-1"))
            record = remote.get_record(SCOPE, "R-1")
            assert record is not None and record["id"] == made.stream_id
            assert [r["key"] for r in remote.query_records(SCOPE, "title~record")] == ["R-1"]
            assert remote.count_records(SCOPE, "key:R-1") == 1
            with pytest.raises(QuerySyntaxError) as syntax:
                remote.query_records(SCOPE, "status:open )")
            assert syntax.value.position == 12
            assert isinstance(syntax.value, CLIENT_ERRORS)
            stale = UpdateRecord(
                actor="user:x",
                source="tui",
                scope=SCOPE,
                stream_id=made.stream_id,
                expected_version=99,
                changes={"title": "x"},
            )
            with pytest.raises(ConcurrencyError):
                remote.update_record(stale)
            assert remote.get_record(SCOPE, "NOPE") is None
            with pytest.raises(RecordNotFoundError):
                remote.conformance("no-such-id")
        finally:
            remote.close()


def test_events_of_own_commands_are_noted_and_reads_are_not(harness: Harness) -> None:
    with harness.live() as server:
        remote = RemoteClient.connect(server.base_url, server.token)
        try:
            result = remote.create_record(create_cmd("R-2"))
            remote.list_records(SCOPE)
            assert len(remote.own_writes) == len(result.events) == 1
            assert result.events[0].event_id in remote.own_writes
        finally:
            remote.close()


def test_an_unreachable_server_is_a_state_and_a_showable_error() -> None:
    remote = RemoteClient.connect(f"http://127.0.0.1:{free_port()}", "token", timeout=1.0)
    states: list[tuple[str, str]] = []
    remote.connection_listener = lambda state, detail: states.append((state, detail))
    try:
        with pytest.raises(ApiUnavailableError) as raised:
            remote.list_records(SCOPE)
        assert isinstance(raised.value, CLIENT_ERRORS)
        assert describe_error(raised.value).startswith("server unreachable")
        with pytest.raises(ApiUnavailableError):
            remote.count_records(SCOPE, "")
        assert [s for s, _ in states] == ["unreachable"]  # reported once, on the change
        assert "cannot reach the server" in states[0][1]
    finally:
        remote.close()


def test_the_next_good_call_reports_live_again(harness: Harness) -> None:
    from remote_support import restartable

    with restartable(harness) as server:
        remote = RemoteClient.connect(server.base_url, server.token, timeout=2.0)
        states: list[str] = []
        remote.connection_listener = lambda state, detail: states.append(state)
        try:
            remote.list_records(SCOPE)
            server.stop()
            with pytest.raises(ApiUnavailableError):
                remote.list_records(SCOPE)
            server.start()
            remote.list_records(SCOPE)
            assert states == ["unreachable", "live"]
        finally:
            remote.close()


def test_other_attributes_pass_through(harness: Harness) -> None:
    remote = RemoteClient(harness.api())
    other: Any = remote
    assert other.base_url == "http://testserver"
    with pytest.raises(AttributeError):
        other.no_such_method  # noqa: B018


def test_interactive_calls_time_out_after_a_few_seconds() -> None:
    from tl_tui.remote import INTERACTIVE_TIMEOUT_S

    assert INTERACTIVE_TIMEOUT_S == 3.0  # the UI thread may freeze this long, then the banner shows
    remote = RemoteClient.connect("http://127.0.0.1:9", "token")
    try:
        timeout = remote._api._http.timeout  # pyright: ignore[reportPrivateUsage]
        assert timeout.read == INTERACTIVE_TIMEOUT_S and timeout.connect == INTERACTIVE_TIMEOUT_S
    finally:
        remote.close()


def test_the_feed_methods_say_plainly_that_the_feed_over_the_api_is_not_there_yet(
    harness: Harness,
) -> None:
    from tl_tui.remote import FeedOverApiUnavailable

    remote = RemoteClient(harness.api())
    with pytest.raises(FeedOverApiUnavailable) as raised:
        remote.feed_page(SCOPE)
    assert isinstance(raised.value, CLIENT_ERRORS)  # a screen shows it and keeps its state
    assert "P0-I6 workstream B" in describe_error(raised.value)
