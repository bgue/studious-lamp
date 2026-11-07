"""``WebReadClient``: the server's own read functions behind the terminal's read method names.

Every method of the client mirrors one JSON route (``MIRRORS``: method name -> ``operation_id``) and
calls that route's function with the caller's actor and viewer. A page can therefore show nothing
the JSON route would not. Twin tickets raise the number pinned here in their own ticket.
"""

from __future__ import annotations

import json
import re
from typing import Any
from unittest import mock

import pytest
from pydantic_core import to_jsonable_python
from tl_api.errors import body_for
from tl_core.auth.errors import ForbiddenError
from tl_web import present
from tl_web.reads import MIRRORS, UnsupportedRead, WebReadClient

P = "P123"
SCOPE = "project:P123"
#: Public attributes of ``WebReadClient`` that are not reads (none today).
NOT_READS: frozenset[str] = frozenset()
#: Reads of one awp record: this world holds none, so the route and the mirror both refuse (404).
ABSENT = frozenset(
    {
        "get_cwp",
        "get_iwp",
        "list_iwp_scope",
        "get_constraint",
        "get_wbs_node",
        "get_path",
        "get_materials_lot",
        "get_materials_receipt",
        "get_materials_mto_line",
    }
)


def public_methods() -> set[str]:
    return {
        name
        for name, member in vars(WebReadClient).items()
        if not name.startswith("_") and callable(member)
    }


def dropping_none(value: Any) -> Any:
    """JSON with the null members left out (the API leaves them out of some bodies)."""
    if isinstance(value, dict):
        return {k: dropping_none(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [dropping_none(v) for v in value]
    return value


def as_json(value: Any) -> Any:
    return dropping_none(json.loads(json.dumps(to_jsonable_python(value), sort_keys=True)))


# --- the table ----------------------------------------------------------------------------------


def test_the_mirror_count_is_pinned(k: Any) -> None:
    assert len(MIRRORS) == 47, (
        "MIRRORS in tl_web/reads.py changed size: twin tickets raise this number in their own "
        "ticket (and add the read to this test's CASES)"
    )


def test_the_two_reads_of_the_record_screen_have_their_rows() -> None:
    assert MIRRORS["conformance"] == "get_conformance"
    assert MIRRORS["trace"] == "get_record_trace"


def test_every_key_is_a_public_method_and_every_method_is_a_key() -> None:
    assert set(MIRRORS) <= public_methods(), sorted(set(MIRRORS) - public_methods())
    assert public_methods() - NOT_READS == set(MIRRORS), sorted(public_methods() ^ set(MIRRORS))


def test_every_value_is_a_route_function_of_tl_api_routes(world: Any, k: Any) -> None:
    by_operation: dict[str, Any] = {}
    for _, route in k.iter_routes(world.app.routes):
        operation = getattr(route, "operation_id", None)
        if operation:
            by_operation[operation] = route
    for method, operation in MIRRORS.items():
        route = by_operation.get(operation)
        assert route is not None, f"{method}: no route with operation_id {operation}"
        assert route.endpoint.__module__.startswith("tl_api.routes."), (method, route.endpoint)


# --- the reads equal the JSON routes ------------------------------------------------------------


def cases(w: Any) -> dict[str, tuple[tuple[Any, ...], dict[str, Any], dict[str, Any]]]:
    """method -> (args, kwargs, path and query parameters of the JSON route)."""
    rfi, item, doc = w.ids["open_rfi"], w.ids["open"], w.ids["open_document"]
    return {
        "list_rfis": ((P,), {}, {"project": P}),
        "get_rfi": (
            (P, w.numbers["open_rfi"]),
            {},
            {"project": P, "number": w.numbers["open_rfi"]},
        ),
        "list_correspondence": ((P,), {}, {"project": P}),
        "get_correspondence": (
            (P, w.numbers["open"]),
            {},
            {"project": P, "number": w.numbers["open"]},
        ),
        "list_documents": ((P,), {}, {"project": P}),
        "get_document": ((P, "ISO-9002"), {}, {"project": P, "number": "ISO-9002"}),
        "list_clocks": ((P,), {}, {"project": P}),
        "get_clock": (
            (P, w.hidden.extra_ids["open_clock"]),
            {},
            {"project": P, "clock_id": w.hidden.extra_ids["open_clock"]},
        ),
        "list_correspondence_domains": ((P,), {}, {"project": P}),
        "form_metadata": (
            (SCOPE, "correspondence.TechnicalItem", rfi),
            {},
            {"scope": SCOPE, "record_type": "correspondence.TechnicalItem", "record_id": rfi},
        ),
        "workflow_status": ((rfi,), {}, {"record_id": rfi}),
        "allowed_actions": ((rfi,), {}, {"record_id": rfi}),
        "history": ((item,), {}, {"record_id": item}),
        "links_of": ((item,), {}, {"record_id": item}),
        "link_counts": (([item, rfi],), {}, {"record_id": [item, rfi]}),
        "list_record_files": (
            (item,),
            {},
            {"record_id": item, "scope": SCOPE, "current_only": "true"},
        ),
        "file_info": (
            (SCOPE, w.hidden.extra_ids["open_file"]),
            {},
            {"file_id": w.hidden.extra_ids["open_file"], "scope": SCOPE},
        ),
        "thread_page": ((item,), {}, {"record_id": item}),
        "get_record": ((SCOPE, w.numbers["open"]), {}, {"scope": SCOPE, "key": w.numbers["open"]}),
        "get_record_by_id": ((doc,), {}, {"record_id": doc}),
        "conformance": ((rfi,), {}, {"record_id": rfi}),
        "trace": ((item,), {}, {"record_id": item}),
        "list_accounts": ((), {}, {}),
        "list_cwps": ((P,), {}, {"project": P}),
        "get_cwp": ((P, "CWP-1"), {}, {"project": P, "number": "CWP-1"}),
        "list_cwas": ((P,), {}, {"project": P}),
        "wbs_tree": ((P,), {}, {"project": P}),
        "get_wbs_node": ((P, "1.1"), {}, {"project": P, "code": "1.1"}),
        "get_path": ((P,), {}, {"project": P}),
        "list_path_versions": ((P,), {}, {"project": P}),
        "list_packages": ((P,), {}, {"project": P}),
        "list_materials_stock": ((P,), {}, {"project": P}),
        "get_materials_lot": ((P, "LOT-1"), {}, {"project": P, "key": "LOT-1"}),
        "list_materials_movements": ((P,), {}, {"project": P}),
        "list_materials_receipts": ((P,), {}, {"project": P}),
        "get_materials_receipt": ((P, "GR-1"), {}, {"project": P, "number": "GR-1"}),
        "list_materials_locations": ((P,), {}, {"project": P}),
        "list_materials_mto_lines": ((P,), {}, {"project": P}),
        "get_materials_mto_line": ((P, "MTO-1"), {}, {"project": P, "key": "MTO-1"}),
        "list_materials_items": ((), {"project": P}, {"project": P}),
        "list_materials_item_projects": (("ITEM-1",), {}, {"code": "ITEM-1"}),
        "list_iwps": ((P,), {}, {"project": P}),
        "get_iwp": ((P, "P123-IWP-PIP-0001"), {}, {"project": P, "number": "P123-IWP-PIP-0001"}),
        "list_iwp_scope": (
            (P, "P123-IWP-PIP-0001"),
            {},
            {"project": P, "number": "P123-IWP-PIP-0001"},
        ),
        "list_constraints": ((P,), {}, {"project": P}),
        "get_constraint": ((P, "P123-CON-0001"), {}, {"project": P, "key": "P123-CON-0001"}),
    }


def json_path(world: Any, method: str, params: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """The path of the route behind ``method`` and the query that is left over."""
    operation = MIRRORS[method]
    for path, ops in world.app.openapi()["paths"].items():
        for op in ops.values():
            if op.get("operationId") == operation:
                names = set(re.findall(r"\{(\w+)\}", path))
                filled = path.format(**{n: params[n] for n in names})
                return filled, {k: v for k, v in params.items() if k not in names}
    raise AssertionError(f"no route for {operation}")


@pytest.mark.parametrize("reader", ["boss", "bob"])
def test_each_mirror_returns_what_the_json_route_returns_for_the_same_viewer(
    world: Any, reader: str
) -> None:
    client = world.reads(reader)
    api = world.api(reader)
    table = cases(world)
    assert set(table) | {"list_code_lists"} == set(MIRRORS), "a mirror has no case here"
    for method, (args, kwargs, params) in table.items():
        if method == "list_accounts" and reader != "boss":
            continue  # the plain user is refused (test below)
        path, query = json_path(world, method, params)
        sent = api.get(path, params=query)
        if method in ABSENT:
            assert sent.status_code == 404, f"{reader} {method}: {sent.status_code}"
            with pytest.raises(Exception, match="no "):
                getattr(client, method)(*args, **kwargs)
            continue
        assert sent.status_code == 200, f"{reader} {method}: {sent.status_code} {sent.text[:200]}"
        got = as_json(getattr(client, method)(*args, **kwargs))
        assert got == dropping_none(sent.json()), f"{reader} {method} differs from {path}"


@pytest.mark.parametrize("reader", ["boss", "bob"])
def test_list_code_lists_is_every_list_with_its_usable_values(world: Any, reader: str) -> None:
    lists = world.reads(reader).list_code_lists(SCOPE)
    api = world.api(reader)
    standards = api.get("/standards", params={"kind": "code_list"})
    assert standards.status_code == 200
    names = {str(s["code"]) for s in standards.json()}
    assert set(lists) == names
    for name, values in lists.items():
        sent = api.get(f"/code-lists/{name}/values", params={"project": P})
        assert values == {str(v["code"]): str(v["label"]) for v in sent.json()}, name


def test_a_plain_user_may_not_list_accounts_and_an_admin_may(world: Any) -> None:
    with pytest.raises(ForbiddenError):
        world.reads("bob").list_accounts()
    assert len(world.reads("boss").list_accounts()) >= 5


@pytest.mark.parametrize("reader", ["boss", "ctl", "bob"])
def test_list_rfis_rows_and_count_equal_the_json_rows(world: Any, reader: str) -> None:
    mine = world.reads(reader).list_rfis(P)
    route = world.api(reader).get(f"/projects/{P}/rfis").json()
    assert [r.number for r in mine.lines] == [r["number"] for r in route["lines"]]
    assert mine.total == route["total"] == len(mine.lines)


def test_a_plain_users_rows_and_count_leave_the_hidden_out(world: Any) -> None:
    admin = [r.number for r in world.reads("boss").list_rfis(P).lines]
    plain = world.reads("bob").list_rfis(P)
    numbers = [r.number for r in plain.lines]
    assert world.numbers["restricted_rfi"] in admin
    for hidden in ("secret_rfi", "restricted_rfi"):
        assert world.numbers[hidden] not in numbers
    assert plain.total == len(plain.lines) == len(admin) - 1  # only the restricted one differs


def test_a_hidden_rfi_and_an_unknown_one_raise_the_same_error(world: Any) -> None:
    errors = []
    for number in (world.numbers["secret_rfi"], "P123-RFI-9999"):
        with pytest.raises(Exception) as caught:
            world.reads("bob").get_rfi(P, number)
        errors.append((type(caught.value), str(caught.value).replace(number, "N")))
    assert errors[0] == errors[1]
    sent = world.api("bob").get(f"/projects/{P}/rfis/{world.numbers['secret_rfi']}")
    assert sent.status_code == 404
    assert world.reads("bob").get_record_by_id(world.ids["secret_rfi"]) is None


def test_the_three_reads_that_answer_none_or_empty_do_so_for_a_hidden_record(world: Any) -> None:
    bob = world.reads("bob")
    hidden = world.ids["restricted"]
    assert bob.get_record_by_id(hidden) is None
    assert bob.get_record(SCOPE, world.numbers["restricted"]) is None
    assert bob.history(hidden) == []
    assert bob.list_record_files(hidden) == []
    with pytest.raises(Exception) as caught:  # file_info raises the route's 404
        bob.file_info(SCOPE, world.hidden.extra_ids["restricted_file"])
    mapped = body_for(caught.value)
    assert mapped is not None and mapped[0] == 404


@pytest.mark.parametrize("name", ["list_records", "get_tag", "nope", "__nope__"])
def test_any_other_read_raises_unsupported_read(world: Any, name: str) -> None:
    client = world.reads("bob")
    with pytest.raises(UnsupportedRead) as caught:
        getattr(client, name)
    assert isinstance(caught.value, AttributeError) and caught.value.name == name


def test_not_implemented_and_mapped_errors_pass_through(world: Any) -> None:
    client = world.reads("bob")

    def not_there(**_: Any) -> Any:
        raise NotImplementedError("not installed")

    with mock.patch("tl_web.reads.links_routes.get_record_trace", not_there):
        with pytest.raises(NotImplementedError):
            client.trace(world.ids["open"])
    with pytest.raises(Exception) as caught:
        client.get_correspondence(P, "P123-COR-9999")
    assert body_for(caught.value) is not None  # the table maps it: the page shows its text


def test_the_renderers_run_over_the_seeded_records_with_no_unsupported_read(world: Any) -> None:
    from tl_tui import details, labels_load

    raised: list[str] = []
    original = WebReadClient.__getattr__

    def watch(self: WebReadClient, name: str) -> Any:
        try:
            return original(self, name)
        except UnsupportedRead:
            raised.append(name)
            raise

    client = world.reads("bob")
    with mock.patch.object(WebReadClient, "__getattr__", watch):
        as_client = present.as_client(client)
        labels = labels_load.load_labels(as_client, SCOPE, ("correspondence.TechnicalItem",))
        for key in (world.numbers["open_rfi"], world.numbers["open"], "ISO-9002"):
            record = client.get_record(SCOPE, key)
            assert record is not None, key
            rows = details.details_for(as_client, P, record, labels, present.display.DisplayMode())
            assert len(rows) > 0, key
            assert not any(r.label == details.NOTE_LABEL for r in rows), f"{key}: renderer failed"
    assert not raised, f"UnsupportedRead raised for {raised}"
