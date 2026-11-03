"""The WBS commands (S3): shape rules, the allocation sum, keys, hidden ids, module-only links."""

from __future__ import annotations

from typing import Any

import pytest
from awp_world import COST, WBS, World, hidden_record, line, refuses
from pydantic import ValidationError
from tl_adapters.db import open_uow
from tl_core.auth.errors import ForbiddenError
from tl_core.services.errors import (
    NoChangesError,
    RecordNotFoundError,
    UnsupportedRecordTypeError,
)
from tl_core.services.links import RetractLink, handle_retract_link
from tl_core.util import new_ulid
from tl_mod_awp.errors import (
    AllocationError,
    CodeNotFoundError,
    DuplicateCodeError,
    InUseError,
    RetiredError,
    WbsRuleError,
)

CODES = (
    ("4210-PIP-WLD", "Welding"),
    ("4210-PIP-ERC", "Erection"),
    ("4210-PIP-TST", "Test"),
)


@pytest.fixture
def tree(world: World) -> World:
    world.cost_codes(*CODES)
    for code, parent in (("1", None), ("1.1", "1"), ("1.1.1", "1.1"), ("1.1.2", "1.1")):
        world.call("sue", "DefineWbsNode", code=code, title=f"Node {code}", parent_code=parent)
    return world


def test_define_numbers_the_nodes_by_depth_and_position(tree: World) -> None:
    nodes = tree.rows("SELECT code, depth, position FROM cur_awp_wbs_node ORDER BY code")
    assert [(n["code"], n["depth"], n["position"]) for n in nodes] == [
        ("1", 0, 1),
        ("1.1", 1, 1),
        ("1.1.1", 2, 1),
        ("1.1.2", 2, 2),
    ]


def test_a_position_beyond_the_last_sibling_is_refused(tree: World) -> None:
    refuses(
        WbsRuleError,
        lambda: tree.call(
            "sue", "DefineWbsNode", code="1.2", title="x", parent_code="1", position=3
        ),
    )
    tree.call("sue", "DefineWbsNode", code="1.2", title="x", parent_code="1", position=2)


def test_an_unknown_parent_is_refused(tree: World) -> None:
    refuses(
        CodeNotFoundError,
        lambda: tree.call("sue", "DefineWbsNode", code="9.1", title="x", parent_code="9"),
    )


def test_the_same_kind_refuses_a_second_code(tree: World) -> None:
    refuses(DuplicateCodeError, lambda: tree.call("sue", "DefineWbsNode", code="1", title="Again"))


def test_the_depth_bound_is_eight_levels(tree: World) -> None:
    parent = "1.1.2"
    for level in range(3, 8):  # depth 3..7
        parent = _child(tree, f"D{level}", parent)
    assert tree.scalar("SELECT MAX(depth) FROM cur_awp_wbs_node") == 7
    refuses(
        WbsRuleError,
        lambda: tree.call("sue", "DefineWbsNode", code="D8", title="D8", parent_code="D7"),
    )


def _child(w: World, code: str, parent: str) -> str:
    w.call("sue", "DefineWbsNode", code=code, title=code, parent_code=parent)
    return code


def test_a_move_that_pushes_a_descendant_past_depth_seven_is_refused(tree: World) -> None:
    parent = "1.1.2"
    for level in range(3, 7):  # depth 3..6: one level left
        parent = _child(tree, f"D{level}", parent)
    # node 1.1 (with 1.1.1, 1.1.2, D3..D6 below, 4 levels under it) cannot go under D6
    tree.call("sue", "DefineWbsNode", code="2", title="Other")
    tree.call("sue", "DefineWbsNode", code="2.1", title="Other child", parent_code="2")
    refuses(
        WbsRuleError,
        lambda: tree.call("sue", "ReviseWbsNode", node=tree.id_of("2"), parent_code="D6"),
    )
    # a two-level subtree still fits under the depth-6 node
    tree.call("sue", "ReviseWbsNode", node=tree.id_of("2.1"), parent_code="D6")
    assert tree.scalar("SELECT depth FROM cur_awp_wbs_node WHERE code = '2.1'") == 7


@pytest.mark.parametrize(
    ("percents", "message"),
    [
        (("60.00", "39.99"), "99.99"),
        (("60.00", "40.01"), "100.01"),
    ],
)
def test_the_allocation_must_sum_to_exactly_100(
    tree: World, percents: tuple[str, str], message: str
) -> None:
    leaf = tree.id_of("1.1.1")
    lines = [line("4210-PIP-WLD", percents[0]), line("4210-PIP-ERC", percents[1])]
    exc = refuses(
        AllocationError, lambda: tree.call("sue", "MapWbsToCostCodes", node=leaf, allocations=lines)
    )
    assert message in str(exc)


def test_an_allocation_of_exactly_100_is_taken_in_cents(tree: World) -> None:
    leaf = tree.id_of("1.1.1")
    lines = [
        line("4210-PIP-WLD", "33.33"),
        line("4210-PIP-ERC", "33.33"),
        line("4210-PIP-TST", "33.34"),
    ]
    tree.call("sue", "MapWbsToCostCodes", node=leaf, allocations=lines)
    got = tree.rows("SELECT percent FROM cur_awp_wbs_allocation WHERE node_id = :n", n=leaf)
    assert sorted(g["percent"] for g in got) == ["33.33", "33.33", "33.34"]


@pytest.mark.parametrize("percent", ["0", "0.00", "100.01", "1e1", "٥٠.00", "50.001", "-5"])
def test_a_percent_outside_0_01_to_100_or_not_ascii_digits_is_refused(
    tree: World, percent: str
) -> None:
    leaf = tree.id_of("1.1.1")
    lines = [line("4210-PIP-WLD", percent), line("4210-PIP-ERC", "50.00")]
    refuses(
        AllocationError, lambda: tree.call("sue", "MapWbsToCostCodes", node=leaf, allocations=lines)
    )


def test_a_repeated_or_unknown_cost_code_is_refused_without_the_cell_text(tree: World) -> None:
    leaf = tree.id_of("1.1.1")
    twice = [line("4210-PIP-WLD", "50.00")] * 2
    refuses(
        AllocationError, lambda: tree.call("sue", "MapWbsToCostCodes", node=leaf, allocations=twice)
    )
    exc = refuses(
        AllocationError,
        lambda: tree.call(
            "sue", "MapWbsToCostCodes", node=leaf, allocations=[line("NO-SUCH-CODE", "100.00")]
        ),
    )
    assert "NO-SUCH-CODE" not in str(exc)


def test_more_than_twenty_lines_do_not_validate(tree: World) -> None:
    lines = [line(f"C{n}", "5.00") for n in range(21)]
    with pytest.raises(ValidationError):
        tree.call("sue", "MapWbsToCostCodes", node=tree.id_of("1.1.1"), allocations=lines)


def test_only_a_leaf_takes_an_allocation_and_an_allocated_leaf_takes_no_child(tree: World) -> None:
    refuses(
        WbsRuleError,
        lambda: tree.call(
            "sue",
            "MapWbsToCostCodes",
            node=tree.id_of("1.1"),
            allocations=[line("4210-PIP-TST", "100.00")],
        ),
    )
    leaf = tree.id_of("1.1.1")
    tree.call("sue", "MapWbsToCostCodes", node=leaf, allocations=[line("4210-PIP-TST", "100.00")])
    refuses(
        WbsRuleError,
        lambda: tree.call("sue", "DefineWbsNode", code="1.1.1.1", title="C", parent_code="1.1.1"),
    )


def test_an_empty_list_clears_the_allocation_and_its_links(tree: World) -> None:
    leaf = tree.id_of("1.1.1")
    tree.call("sue", "MapWbsToCostCodes", node=leaf, allocations=[line("4210-PIP-WLD", "100.00")])
    tree.call("sue", "MapWbsToCostCodes", node=leaf, allocations=[])
    live = tree.rows("SELECT 1 FROM cur_links WHERE from_id = :n AND status <> 'retracted'", n=leaf)
    n = tree.scalar("SELECT COUNT(*) FROM cur_awp_wbs_allocation WHERE node_id = :n", n=leaf)
    assert not live
    assert n == 0


def test_node_1_and_cost_code_1_coexist(world: World) -> None:
    world.cost_codes(("1", "One"))
    world.call("sue", "DefineWbsNode", code="1", title="Plant")
    world.call("sue", "DefineCwa", code="1", title="Area one")
    key = world.scalar("SELECT key FROM cur_core_record WHERE id = :i", i=world.id_of("1"))
    assert key == "awp.wbs@1"
    assert world.id_of("1", COST) != world.id_of("1", WBS)
    # the allocation of node 1.1 may name cost code 1
    world.call("sue", "DefineWbsNode", code="1.1", title="Unit", parent_code="1")
    world.call(
        "sue",
        "MapWbsToCostCodes",
        node=world.id_of("1.1"),
        allocations=[line("1", "100.00")],
    )
    assert world.scalar("SELECT COUNT(*) FROM cur_awp_wbs_allocation") == 1


def test_a_hidden_record_answers_as_a_missing_one(tree: World) -> None:
    hidden, absent = hidden_record(tree), new_ulid()
    calls: tuple[tuple[str, dict[str, Any]], ...] = (
        ("RetireWbsNode", {"reason": "x"}),
        ("ReviseWbsNode", {"title": "x"}),
        ("MapWbsToCostCodes", {"allocations": []}),
    )
    for name, fields in calls:
        a = refuses(
            RecordNotFoundError, lambda n=name, f=fields: tree.call("sue", n, node=hidden, **f)
        )  # type: ignore[misc]
        b = refuses(
            RecordNotFoundError, lambda n=name, f=fields: tree.call("sue", n, node=absent, **f)
        )  # type: ignore[misc]
        assert str(a).replace(hidden, "ID") == str(b).replace(absent, "ID")


def test_a_node_of_another_record_type_answers_as_missing(tree: World) -> None:
    tree.call("sue", "DefineCwa", code="A1", title="Area")
    refuses(
        RecordNotFoundError,
        lambda: tree.call("sue", "RetireWbsNode", node=tree.id_of("A1", "awp.CWA"), reason="x"),
    )


def test_links_follow_the_allocation_and_a_person_cannot_retract_them(tree: World) -> None:
    leaf = tree.id_of("1.1.1")
    tree.call(
        "sue",
        "MapWbsToCostCodes",
        node=leaf,
        allocations=[line("4210-PIP-WLD", "60.00"), line("4210-PIP-ERC", "40.00")],
    )
    live = tree.rows(
        "SELECT link_id, source, relation FROM cur_links WHERE from_id = :n "
        "AND status <> 'retracted'",
        n=leaf,
    )
    assert len(live) == 2
    assert {r["source"] for r in live} == {"rule"}
    assert {r["relation"] for r in live} == {"references"}

    def person_retracts() -> Any:
        with open_uow(tree.db) as uow:
            cmd = RetractLink(
                actor="user:uma",
                source="test",
                scope="project:P123",
                link_id=live[0]["link_id"],
                reason="no longer needed",
            )
            return handle_retract_link(uow, cmd)

    refuses(UnsupportedRecordTypeError, person_retracts)
    tree.call("sue", "MapWbsToCostCodes", node=leaf, allocations=[line("4210-PIP-WLD", "100.00")])
    now = tree.rows(
        "SELECT to_id FROM cur_links WHERE from_id = :n AND status <> 'retracted'", n=leaf
    )
    assert [r["to_id"] for r in now] == [tree.id_of("4210-PIP-WLD", COST)]


def test_a_link_the_module_retracted_is_added_again_on_the_next_change(tree: World) -> None:
    leaf = tree.id_of("1.1.1")
    both = [line("4210-PIP-WLD", "60.00"), line("4210-PIP-ERC", "40.00")]
    tree.call("sue", "MapWbsToCostCodes", node=leaf, allocations=both)
    erc = tree.id_of("4210-PIP-ERC", COST)
    [gone] = tree.rows(
        "SELECT link_id FROM cur_links WHERE from_id = :n AND to_id = :t AND status <> 'retracted'",
        n=leaf,
        t=erc,
    )
    with open_uow(tree.db) as uow:
        handle_retract_link(
            uow,
            RetractLink(
                actor="user:sue",
                source="test",
                scope="project:P123",
                link_id=gone["link_id"],
                reason="test",
            ),
            by_module=True,
        )
    tree.call("sue", "MapWbsToCostCodes", node=leaf, allocations=both)
    back = tree.rows(
        "SELECT to_id FROM cur_links WHERE from_id = :n AND status <> 'retracted'", n=leaf
    )
    assert len(back) == 2
    assert erc in {r["to_id"] for r in back}


def test_revise_renames_moves_and_reorders(tree: World) -> None:
    node = tree.id_of("1.1.2")
    tree.call("sue", "ReviseWbsNode", node=node, title="Renamed")
    assert tree.scalar("SELECT title FROM cur_core_record WHERE id = :i", i=node) == "Renamed"
    tree.call("sue", "ReviseWbsNode", node=node, position=1)
    order = tree.rows(
        "SELECT code, position FROM cur_awp_wbs_node WHERE parent_id = :p ORDER BY position",
        p=tree.id_of("1.1"),
    )
    assert [(o["code"], o["position"]) for o in order] == [("1.1.2", 1), ("1.1.1", 2)]
    tree.call("sue", "ReviseWbsNode", node=node, parent_code=None)  # to the root
    assert tree.scalar("SELECT depth FROM cur_awp_wbs_node WHERE code = '1.1.2'") == 0
    left = tree.rows(
        "SELECT code, position FROM cur_awp_wbs_node WHERE parent_id = :p", p=tree.id_of("1.1")
    )
    assert [(o["code"], o["position"]) for o in left] == [("1.1.1", 1)]
    refuses(NoChangesError, lambda: tree.call("sue", "ReviseWbsNode", node=node, title="Renamed"))


def test_a_node_cannot_move_under_itself(tree: World) -> None:
    refuses(
        WbsRuleError,
        lambda: tree.call("sue", "ReviseWbsNode", node=tree.id_of("1"), parent_code="1.1.1"),
    )


def test_retire_is_refused_twice_and_while_a_package_allocates(tree: World) -> None:
    tree.areas_and_path(("A1",))
    cwp = tree.new_cwp("PIP", "Rack", "A1")
    tree.call(
        "uma",
        "AllocateCwpToWbs",
        cwp=cwp,
        allocations=[{"wbs_code": "1.1.1", "percent": "100.00"}],
    )
    node = tree.id_of("1.1.1")
    refuses(InUseError, lambda: tree.call("sue", "RetireWbsNode", node=node, reason="done"))
    tree.call("sue", "VoidCwp", id=cwp, reason="gone")
    tree.call("sue", "RetireWbsNode", node=node, reason="done")
    refuses(RetiredError, lambda: tree.call("sue", "RetireWbsNode", node=node, reason="again"))
    refuses(
        RetiredError,
        lambda: tree.call(
            "sue", "MapWbsToCostCodes", node=node, allocations=[line("4210-PIP-TST", "100.00")]
        ),
    )


def test_the_words_a_user_lacks_are_refused(tree: World) -> None:
    refuses(ForbiddenError, lambda: tree.call("uma", "DefineWbsNode", code="9", title="Nine"))
    refuses(ForbiddenError, lambda: tree.call("vera", "DefineWbsNode", code="9", title="Nine"))
    tree.call("sue", "DefineWbsNode", code="9", title="Nine")


def test_several_changes_queue_the_rollup_once(tree: World) -> None:
    tree.call(
        "sue",
        "MapWbsToCostCodes",
        node=tree.id_of("1.1.1"),
        allocations=[line("4210-PIP-TST", "100.00")],
    )
    rows = tree.rows("SELECT job_id, kind, state FROM job_queue WHERE kind = 'awp.rollup'")
    assert rows == [{"job_id": "rollup:project:P123", "kind": "awp.rollup", "state": "queued"}]
