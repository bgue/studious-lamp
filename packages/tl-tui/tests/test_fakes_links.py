"""The link and workflow side of `FakeClient` (P0-I3): TUI tests rely on it matching the core."""

from __future__ import annotations

import pytest
from fakes import SCOPE, FakeClient
from tl_core.ledger import ConcurrencyError
from tl_core.services.errors import (
    DuplicateLinkError,
    GuardFailedError,
    InvalidLinkTransitionError,
    SelfLinkError,
    SuggestionDeclinedError,
)
from tl_core.services.links import (
    AcceptLink,
    AddLink,
    DeclineLink,
    FlagLink,
    RepinLink,
    SuggestLink,
    VerifyLink,
)
from tl_core.services.workflow import TransitionWorkflow
from tl_tui.client import ClientInterface


def ids(client: FakeClient, *keys: str) -> list[str]:
    return [client._records_by_key(k)["id"] for k in keys]  # pyright: ignore[reportPrivateUsage]


def common(**kw: object) -> dict[str, object]:
    return {"actor": "user:t", "source": "tui", "scope": SCOPE, **kw}


def test_both_directions_and_labels() -> None:
    client = FakeClient.with_valve_example()
    a, b = ids(client, "FV-1001", "FV-1002")
    client.seed_link("FV-1001", "FV-1002", "raised_against")
    out = client.links_of(a)[0]
    inbound = client.links_of(b)[0]
    assert (out.direction, out.label, out.other_key) == ("out", "raised against", "FV-1002")
    assert (inbound.direction, inbound.label, inbound.other_key) == ("in", "has raised", "FV-1001")


def test_add_suggest_accept_and_the_lifecycle_rules() -> None:
    client = FakeClient.with_valve_example()
    a, b, c = ids(client, "FV-1001", "FV-1002", "FV-1003")
    added = client.add_link(AddLink(**common(from_id=a, to_id=b)))  # type: ignore[arg-type]
    with pytest.raises(DuplicateLinkError):
        client.add_link(AddLink(**common(from_id=a, to_id=b)))  # type: ignore[arg-type]
    with pytest.raises(SelfLinkError):
        client.add_link(AddLink(**common(from_id=a, to_id=a)))  # type: ignore[arg-type]
    suggested = client.suggest_link(SuggestLink(**common(from_id=a, to_id=c, confidence=0.7)))  # type: ignore[arg-type]
    with pytest.raises(InvalidLinkTransitionError):
        client.accept_link(AcceptLink(**common(link_id=added.stream_id)))  # type: ignore[arg-type]
    client.accept_link(AcceptLink(**common(link_id=suggested.stream_id)))  # type: ignore[arg-type]
    statuses = {v.link_id: v.status for v in client.links_of(a)}
    assert statuses == {added.stream_id: "active", suggested.stream_id: "active"}


def test_a_declined_suggestion_is_remembered_and_hidden() -> None:
    client = FakeClient.with_valve_example()
    a, b = ids(client, "FV-1001", "FV-1002")
    suggested = client.suggest_link(SuggestLink(**common(from_id=a, to_id=b)))  # type: ignore[arg-type]
    client.decline_link(DeclineLink(**common(link_id=suggested.stream_id, reason="no")))  # type: ignore[arg-type]
    assert client.links_of(a) == []
    assert len(client.links_of(a, include_retracted=True)) == 1
    with pytest.raises(SuggestionDeclinedError):
        client.suggest_link(SuggestLink(**common(from_id=a, to_id=b)))  # type: ignore[arg-type]


def test_repin_verify_flag_and_expected_version() -> None:
    client = FakeClient.with_valve_example()
    a, b = ids(client, "FV-1001", "FV-1002")
    link_id = client.seed_link("FV-1001", "FV-1002", pin="B")
    client.flag_link(FlagLink(**common(link_id=link_id, status="stale", reason="rev C")))  # type: ignore[arg-type]
    client.repin_link(RepinLink(**common(link_id=link_id, pin="C")))  # type: ignore[arg-type]
    client.verify_link(VerifyLink(**common(link_id=link_id)))  # type: ignore[arg-type]
    view = client.links_of(a)[0]
    assert (view.status, view.pin, view.verified_by, view.version) == ("active", "C", "user:t", 4)
    with pytest.raises(ConcurrencyError):
        client.verify_link(VerifyLink(**common(link_id=link_id, expected_version=1)))  # type: ignore[arg-type]
    assert b


def test_counts_expected_links_and_search() -> None:
    client = FakeClient.with_valve_example()
    a, b, c = ids(client, "FV-1001", "FV-1002", "FV-1003")
    client.seed_link("FV-1001", "FV-1002")
    client.seed_link("FV-1003", "FV-1001", status="suggested")
    counts = client.link_counts([a, b, c])
    assert (counts[a].active_out, counts[a].suggested) == (1, 1)
    assert counts[b].active_in == 1
    assert [m.expectation.label for m in client.expected_links(b)] == ["data sheet"]
    assert client.expected_links(a) == []
    found = client.search_linkable(SCOPE, "valve manual")
    assert [t.key for t in found] == ["FV-1002"]
    assert found[0].link_total == 1
    assert [t.key for t in client.search_linkable(SCOPE, "", exclude_id=a, limit=1)] == ["FV-1002"]


def test_trace_follows_links_to_the_depth() -> None:
    client = FakeClient.with_valve_example()
    a, b, c = ids(client, "FV-1001", "FV-1002", "FV-1003")
    client.seed_link("FV-1001", "FV-1002")
    client.seed_link("FV-1002", "FV-1003", "requires")
    tree = client.trace(a, depth=1)
    assert [n.key for n in tree.children] == ["FV-1002"]
    assert tree.children[0].children == []
    assert tree.children[0].more == 1
    deeper = client.trace(a, depth=2)
    assert deeper.children[0].children[0].key == "FV-1003"
    assert deeper.children[0].children[0].label == "requires"
    assert client.trace(c, depth=2, direction="out").children == []
    assert b


def test_detect_keys_resolves_and_marks_links() -> None:
    client = FakeClient.with_valve_example()
    a, b = ids(client, "FV-1001", "FV-1002")
    client.seed_link("FV-1001", "FV-1002")
    chips = client.detect_keys(
        SCOPE, "see FV-1002 and FV-1003 and FV-9999 and FV-1001", linked_to=a
    )
    assert [(c.key, c.record_id is not None, c.link_status) for c in chips] == [
        ("FV-1002", True, "active"),
        ("FV-1003", True, None),
        ("FV-9999", False, None),
    ]
    assert b


def test_relations_and_defaults_come_from_the_vocabulary() -> None:
    client = FakeClient.with_valve_example()
    relations = client.relations()
    assert relations[0].code == "references"
    assert [r.inverse_label for r in relations if r.code == "raised_against"] == ["has raised"]
    assert client.default_relation("core.Record", "core.Record") == "references"


def test_workflow_blocks_until_the_expected_link_and_role_exist() -> None:
    client = FakeClient.with_valve_example()
    a, b = ids(client, "FV-1001", "FV-1002")
    status = client.workflow_status(a)
    assert (status.state, status.workflow) == ("Design", "fake.valves")
    (install,) = status.options
    assert (install.transition, install.allowed) == ("install", False)
    assert [(g.kind, g.passed) for g in install.guards] == [
        ("expected_links", False),
        ("roles", False),
    ]

    def run(*roles: str) -> object:
        version = client.get_record_by_id(a)["version"]  # type: ignore[index]
        return client.transition(
            TransitionWorkflow(
                actor="user:t",
                source="tui",
                scope=SCOPE,
                stream_id=a,
                expected_version=version,
                transition="install",
                actor_roles=list(roles),
            )
        )

    with pytest.raises(GuardFailedError) as caught:
        run()
    assert len(caught.value.results) == 2
    client.seed_link("FV-1001", "FV-1002")
    with pytest.raises(GuardFailedError) as caught:
        run()
    assert [r.passed for r in caught.value.results] == [True, False]
    result = run("engineer")
    assert result.events[0].event_type == "Workflow.Transitioned"  # type: ignore[attr-defined]
    after = client.workflow_status(a)
    assert after.state == "Installed"
    assert after.entered_at != status.entered_at
    assert [o.transition for o in after.options] == ["commission", "revert"]
    assert b


def test_the_fake_satisfies_the_protocol() -> None:
    client: ClientInterface = FakeClient()
    assert client.relations()
