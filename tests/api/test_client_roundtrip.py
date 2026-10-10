"""ApiClient against the embedded client: every ClientInterface method WS-D will call.

Both clients sit on the same SQLite ledger. Reads must return equal data; commands run through the
API must have the effect the embedded handlers have, and failures must raise the same exception
class. Nothing is mocked. A method that ApiClient cannot serve fails ``test_every_method_exists``.
"""

from __future__ import annotations

import inspect
from typing import Any

import pytest
from pydantic import BaseModel
from support import ACTOR, Pair
from tl_core.ledger import ConcurrencyError
from tl_core.services.commands import CreateRecord, UpdateRecord
from tl_core.services.edit import EditRecord, PsetEdit
from tl_core.services.errors import (
    DuplicateKeyError,
    GuardFailedError,
    RecordNotFoundError,
    UnknownPsetError,
)
from tl_core.services.links import (
    AcceptLink,
    AddLink,
    DeclineLink,
    FlagLink,
    RepinLink,
    RetractLink,
    SuggestLink,
    VerifyLink,
)
from tl_core.services.psets import SetPsetValues
from tl_core.services.workflow import TransitionWorkflow
from tl_tui.client import ClientInterface

SCOPE = "project:P123"


def plain(value: Any) -> Any:
    """Models, lists and dicts as plain JSON data, so two clients' answers can be compared."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [plain(item) for item in value]  # pyright: ignore[reportUnknownVariableType]
    if isinstance(value, dict):
        return {key: plain(item) for key, item in value.items()}  # pyright: ignore
    return value


def common(**extra: Any) -> dict[str, Any]:
    return {"actor": ACTOR, "source": "tui", "scope": SCOPE, **extra}


def create(client: Any, key: str, title: str = "Record") -> str:
    cmd = CreateRecord(**common(record_type="core.Record", title=title, key=key))
    return client.create_record(cmd).stream_id


def interface_methods() -> list[str]:
    return sorted(
        name
        for name, member in inspect.getmembers(ClientInterface, inspect.isfunction)
        if not name.startswith("_")
    )


def test_every_method_exists_with_the_same_parameters(pair: Pair) -> None:
    """ApiClient serves every ClientInterface method, with the same parameter names and kinds."""
    names = interface_methods()
    assert len(names) >= 28
    problems = []
    for name in names:
        theirs = getattr(pair.remote, name, None)
        if theirs is None:
            problems.append(f"{name}: missing")
            continue
        want = inspect.signature(getattr(ClientInterface, name)).parameters
        got = inspect.signature(theirs).parameters
        have = [(p.name, p.kind, p.default) for p in got.values()]
        need = [(p.name, p.kind, p.default) for p in want.values() if p.name != "self"]
        if have != need:
            problems.append(f"{name}: {have} != {need}")
    assert problems == []


def test_reads_equal_the_embedded_answers(pair: Pair) -> None:
    ids = {k: create(pair.remote, k, f"Record {k}") for k in "ABCD"}
    pair.remote.add_link(AddLink(**common(from_id=ids["A"], to_id=ids["B"], relation="requires")))
    pair.remote.add_link(AddLink(**common(from_id=ids["B"], to_id=ids["C"], relation="requires")))
    sid = ids["A"]
    e, r = pair.embedded, pair.remote
    checks = {
        "list_records": lambda c: c.list_records(SCOPE),
        "list_records_paged": lambda c: c.list_records(
            SCOPE, order_by=[("title", "desc")], limit=2, offset=1
        ),
        "get_record": lambda c: c.get_record(SCOPE, "B"),
        "get_record_missing": lambda c: c.get_record(SCOPE, "NOPE"),
        "get_record_by_id": lambda c: c.get_record_by_id(ids["C"]),
        "get_record_by_id_missing": lambda c: c.get_record_by_id("01NOSUCH"),
        "history": lambda c: c.history(sid),
        "history_missing": lambda c: c.history("01NOSUCH"),
        "form_metadata": lambda c: c.form_metadata(SCOPE, "core.Record"),
        "conformance": lambda c: c.conformance(sid),
        "links_of": lambda c: c.links_of(ids["B"]),
        "link_counts": lambda c: c.link_counts(list(ids.values())),
        "expected_links": lambda c: c.expected_links(ids["D"]),
        "search_linkable": lambda c: c.search_linkable(SCOPE, "record b"),
        "trace": lambda c: c.trace(sid),
        "trace_in": lambda c: c.trace(ids["C"], depth=1, direction="in"),
        "detect_keys": lambda c: c.detect_keys(SCOPE, "see P123-REC-0001 and A"),
        "relations": lambda c: c.relations(),
        "default_relation": lambda c: c.default_relation("core.Record", "core.Record"),
        "workflow_status": lambda c: c.workflow_status(sid),
        "workflow_status_roles": lambda c: c.workflow_status(sid, roles=["manager"]),
    }
    for name, call in checks.items():
        assert plain(call(r)) == plain(call(e)), name
    assert len(r.list_records(SCOPE)) == 4 and len(r.links_of(ids["B"])) == 2


def test_a_command_sent_remotely_has_the_embedded_effect(pair: Pair) -> None:
    e, r = pair.embedded, pair.remote
    for client, suffix in ((e, "E"), (r, "R")):
        a = create(client, f"A-{suffix}")
        b = create(client, f"B-{suffix}")
        created = client.get_record(SCOPE, f"A-{suffix}")
        assert created is not None and created["version"] == 1
        updated = client.update_record(
            UpdateRecord(**common(stream_id=a, expected_version=1, changes={"title": "New"}))
        )
        assert updated.version == 2
        edited = client.edit_record(
            EditRecord(**common(stream_id=a, expected_version=2, changes={"description": "d"}))
        )
        assert edited.version == 3
        link = client.add_link(AddLink(**common(from_id=a, to_id=b, relation="requires")))
        for command, event_type in (
            (VerifyLink(**common(link_id=link.stream_id)), "Link.Verified"),
            (
                FlagLink(**common(link_id=link.stream_id, status="stale", reason="moved")),
                "Link.Flagged",
            ),
            (RepinLink(**common(link_id=link.stream_id, pin="B")), "Link.Repinned"),
        ):
            name = type(command).__name__
            method = {
                "VerifyLink": "verify_link",
                "FlagLink": "flag_link",
                "RepinLink": "repin_link",
            }[name]
            assert getattr(client, method)(command).events[0].event_type == event_type
        assert (
            client.retract_link(RetractLink(**common(link_id=link.stream_id, reason="mistake")))
            .events[0]
            .event_type
            == "Link.Retracted"
        )
        suggested = client.suggest_link(
            SuggestLink(**common(from_id=a, to_id=b, relation="references"))
        )
        assert (
            client.accept_link(AcceptLink(**common(link_id=suggested.stream_id)))
            .events[0]
            .event_type
            == "Link.Accepted"
        )
        other = client.suggest_link(SuggestLink(**common(from_id=b, to_id=a, relation="requires")))
        assert (
            client.decline_link(DeclineLink(**common(link_id=other.stream_id))).events[0].event_type
            == "Link.Declined"
        )
        moved = client.transition(
            TransitionWorkflow(**common(stream_id=a, expected_version=3, transition="submit"))
        )
        assert moved.events[0].event_type == "Workflow.Transitioned" and moved.version == 4
        final = client.get_record(SCOPE, f"A-{suffix}")
        assert final is not None and final["status"] == "Review" and final["version"] == 4

    # the effect on the ledger is the same shape, whichever client sent the commands
    def shape(key: str) -> list[str]:
        record = e.get_record(SCOPE, key)
        assert record is not None
        return [ev.event_type for ev in e.history(record["id"])]

    assert shape("A-E") == shape("A-R")


def test_failures_raise_the_same_exception_classes(pair: Pair) -> None:
    bad_edit = PsetEdit(pset="no_such_pset", layer="standard", values={"a": 1})
    for client in (pair.embedded, pair.remote):
        sid = create(client, f"K-{type(client).__name__}")
        with pytest.raises(DuplicateKeyError):
            create(client, f"K-{type(client).__name__}")
        with pytest.raises(ConcurrencyError):
            client.update_record(
                UpdateRecord(**common(stream_id=sid, expected_version=7, changes={"title": "x"}))
            )
        with pytest.raises(RecordNotFoundError):
            client.links_of("01NOSUCH")
        with pytest.raises(UnknownPsetError):
            client.set_pset_values(
                SetPsetValues(
                    **common(
                        stream_id=sid,
                        expected_version=1,
                        pset="no_such_pset",
                        layer="standard",
                        values={"a": 1},
                    )
                )
            )
        with pytest.raises(UnknownPsetError):  # atomic: the title change must not survive
            client.edit_record(
                EditRecord(
                    **common(
                        stream_id=sid,
                        expected_version=1,
                        changes={"title": "Changed"},
                        pset_edits=[bad_edit],
                    )
                )
            )
        assert client.get_record_by_id(sid)["title"] == "Record"  # type: ignore[index]
        client.transition(
            TransitionWorkflow(**common(stream_id=sid, expected_version=1, transition="submit"))
        )
        with pytest.raises(GuardFailedError) as blocked:
            client.transition(
                TransitionWorkflow(
                    **common(stream_id=sid, expected_version=2, transition="approve")
                )
            )
        assert blocked.value.results and any(not r.passed for r in blocked.value.results)
