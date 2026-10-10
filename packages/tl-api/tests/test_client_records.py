"""HTTP client: records, queries and record commands (P0-I4-T46)."""

from __future__ import annotations

import httpx2
import pytest
from harness import ALICE, BOB, SCOPE, Harness
from tl_api.client import ApiClient
from tl_api.client.records import format_order_by
from tl_api.errors import ApiError
from tl_core.ledger import ConcurrencyError
from tl_core.query import QuerySpec, QuerySyntaxError, count_query, parse, run_query
from tl_core.services import queries
from tl_core.services.commands import CreateRecord, UpdateRecord
from tl_core.services.edit import EditRecord, PsetEdit
from tl_core.services.errors import DuplicateKeyError, UnknownPsetError
from tl_core.services.psets import SetPsetValues


def create_cmd(key: str, title: str = "T", **extra: object) -> CreateRecord:
    return CreateRecord(
        actor="user:ignored",
        source="tui",
        scope=SCOPE,
        record_type="core.Record",
        title=title,
        key=key,
        **extra,  # type: ignore[arg-type]
    )


def seed(h: Harness) -> None:
    for key, title in [("R-1", "Gate valve"), ("R-2", "Check valve"), ("R-3", "Pump skid")]:
        h.create_record(key, title)


def test_list_records_equals_the_embedded_answer(harness: Harness) -> None:
    seed(harness)
    api = harness.api()
    with harness.backend(True) as uow:
        embedded = queries.list_records(uow, SCOPE)
        by_title = queries.list_records(uow, SCOPE, order_by=[("title", "desc")], limit=2, offset=1)
    assert api.list_records(SCOPE) == embedded and len(embedded) == 3
    assert api.list_records(SCOPE, order_by=[("title", "desc")], limit=2, offset=1) == by_title
    assert api.list_records("project:P999") == []
    assert api.list_records(SCOPE, record_type="piping.Weld") == []


def test_query_and_count_records_equal_the_embedded_query_layer(harness: Harness) -> None:
    seed(harness)
    api = harness.api()
    for text in ("valve", "title~check", "valve -title~check", "key=R-3 or key=R-1", ""):
        spec = QuerySpec(scope=SCOPE, where=parse(text))
        with harness.backend(True) as uow:
            rows, total = run_query(uow, spec), count_query(uow, spec)
        assert api.query_records(SCOPE, text) == rows, text
        assert api.count_records(SCOPE, text) == total, text
    ordered = api.query_records(SCOPE, "valve", order_by=[("key", "desc")], limit=1)
    assert [r["key"] for r in ordered] == ["R-2"]


def test_a_syntax_error_raises_with_its_position(harness: Harness) -> None:
    api = harness.api()
    with pytest.raises(QuerySyntaxError) as caught:
        api.query_records(SCOPE, "title~gate (")
    assert caught.value.position >= 0 and str(caught.value)
    with pytest.raises(QuerySyntaxError):
        api.count_records(SCOPE, "nonesuch:1")


def test_get_record_and_get_record_by_id_return_none_when_unknown(harness: Harness) -> None:
    seed(harness)
    api = harness.api()
    with harness.backend(True) as uow:
        by_key = queries.get_record(uow, SCOPE, "R-2")
        assert by_key is not None
        by_id = queries.get_record_by_id(uow, by_key["id"])
    assert api.get_record(SCOPE, "R-2") == by_key
    assert api.get_record_by_id(by_key["id"]) == by_id == by_key
    assert api.get_record(SCOPE, "NOPE") is None
    assert api.get_record("project:P999", "R-2") is None
    assert api.get_record_by_id("01NOSUCHRECORD") is None


def test_history_equals_the_ledger_stream_and_is_empty_for_unknown(harness: Harness) -> None:
    api = harness.api()
    made = api.create_record(create_cmd("H-1"))
    api.update_record(
        UpdateRecord(
            actor="u",
            source="tui",
            scope=SCOPE,
            stream_id=made.stream_id,
            expected_version=1,
            changes={"title": "New"},
        )
    )
    with harness.backend(True) as uow:
        embedded = queries.record_history(uow, made.stream_id)
    assert api.history(made.stream_id) == embedded and len(embedded) == 2
    assert api.history("01NOSUCHRECORD") == []


def test_commands_use_the_tokens_actor_and_keep_the_source(harness: Harness) -> None:
    result = harness.api(BOB).create_record(create_cmd("C-1"))
    assert result.key == "C-1" and result.version == 1
    assert result.events[0].actor == BOB and result.events[0].source == "tui"
    assert harness.api(ALICE).create_record(create_cmd("C-2")).events[0].actor == ALICE


def test_command_failures_raise_the_embedded_exception_classes(harness: Harness) -> None:
    api = harness.api()
    made = api.create_record(create_cmd("E-1"))
    with pytest.raises(DuplicateKeyError):
        api.create_record(create_cmd("E-1"))
    stale = UpdateRecord(
        actor="u",
        source="tui",
        scope=SCOPE,
        stream_id=made.stream_id,
        expected_version=5,
        changes={"title": "x"},
    )
    with pytest.raises(ConcurrencyError):
        api.update_record(stale)
    with pytest.raises(UnknownPsetError):
        api.set_pset_values(
            SetPsetValues(
                actor="u",
                source="tui",
                scope=SCOPE,
                stream_id=made.stream_id,
                expected_version=1,
                pset="no_such_pset",
                layer="standard",
                values={"a": 1},
            )
        )


def test_edit_record_is_atomic_over_http(harness: Harness) -> None:
    api = harness.api()
    made = api.create_record(create_cmd("A-1", "Before"))
    bad = EditRecord(
        actor="u",
        source="tui",
        scope=SCOPE,
        stream_id=made.stream_id,
        expected_version=1,
        changes={"title": "After"},
        pset_edits=[PsetEdit(pset="no_such_pset", layer="standard", values={"a": 1})],
    )
    with pytest.raises(UnknownPsetError):
        api.edit_record(bad)
    assert api.get_record_by_id(made.stream_id)["title"] == "Before"  # type: ignore[index]
    good = bad.model_copy(update={"pset_edits": []})
    assert api.edit_record(good).version == 2
    assert api.get_record_by_id(made.stream_id)["title"] == "After"  # type: ignore[index]


def test_a_wrong_token_and_an_unreachable_server_are_told_apart(harness: Harness) -> None:
    with pytest.raises(ApiError) as caught:
        ApiClient("http://testserver", "wrong", http=harness.client_for(None)).list_records(SCOPE)
    assert caught.value.status == 401 and caught.value.error == "unauthorized"
    gone = ApiClient("http://127.0.0.1:9", "t", timeout=2.0)
    with pytest.raises(httpx2.TransportError):
        gone.list_records(SCOPE)
    gone.close()


def test_ids_cannot_change_the_path(harness: Harness) -> None:
    """An id is one path segment: it never reaches another route (/health answers 200)."""
    api = harness.api()
    for bad in ("../health", "a/b?c=d"):
        try:
            found = api.get_record_by_id(bad)
        except ApiError as exc:
            assert exc.status == 404
        else:
            assert found is None


def test_format_order_by() -> None:
    assert format_order_by(None) is None and format_order_by([]) is None
    assert (
        format_order_by([("title", "desc"), ("psets.v.size", "asc")])
        == "title:desc,psets.v.size:asc"
    )
