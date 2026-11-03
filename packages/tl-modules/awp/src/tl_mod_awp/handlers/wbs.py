"""WBS commands: define, revise and retire a node, and map a leaf node to cost codes.

A node is a project record (``awp.WBSNode``) whose key is its code. The tree is read whole
(at most 5 000 nodes) so depth, leaf-only and cycle rules are checked on the rows the projector
keeps. Siblings are numbered 1..n: putting a node at a place moves the siblings after it by a
``WBSNode.Revised`` of their own. A leaf is allocated to cost codes in percent (the sum is exactly
100.00); the module keeps one ``references`` link from the node to each cost code in step with the
rows (``by_module=True``, source ``rule``), so a person never retracts them. Each handler checks
``require_project``, the visibility of every id and every code it is given, and writes events with
the feed policy ``none``. All the events of a command share one correlation id. Fixed messages.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy import Connection, text
from tl_core import confidentiality
from tl_core.ledger import NewEvent
from tl_core.services.commands import CommandResult
from tl_core.services.errors import NoChangesError
from tl_core.uow import UnitOfWork

from tl_mod_awp import rollup
from tl_mod_awp.common import (
    MSG_DUPLICATE,
    append,
    check_allocations,
    correlated,
    create_coded_record,
    cwp_allocates_to,
    key_taken,
    load_record,
    percent_text,
    require_project,
    resolve_code,
    silent,
)
from tl_mod_awp.errors import (
    AllocationError,
    CodeNotFoundError,
    DuplicateCodeError,
    InUseError,
    RetiredError,
    WbsRuleError,
)
from tl_mod_awp.limits import MAX_WBS_DEPTH, MAX_WBS_NODES
from tl_mod_awp.linking import sync_links
from tl_mod_awp.names import (
    COST_CODE,
    COST_RELATION,
    WBS_ALLOCATION_TABLE,
    WBS_COST_CODES_MAPPED,
    WBS_DEFINED,
    WBS_NODE,
    WBS_NODE_TABLE,
    WBS_RETIRED,
    WBS_REVISED,
)

if TYPE_CHECKING:
    from tl_mod_awp.commands import (
        DefineWbsNode,
        MapWbsToCostCodes,
        RetireWbsNode,
        ReviseWbsNode,
    )

MSG_DEPTH = "a WBS holds at most 8 levels"
MSG_COUNT = "a project holds at most 5000 WBS nodes"
MSG_POSITION = "the position is beyond the last sibling"
MSG_NO_PARENT = "no WBS node with that parent code in the project"
MSG_HAS_ALLOCATION = "a node with a cost code or package allocation cannot take a child"
MSG_CYCLE = "a node cannot move under itself or one of its descendants"
MSG_LEAF_ONLY = "only a leaf node takes a cost code allocation"
MSG_RETIRED = "the node is retired"
MSG_IN_USE = "a package that is not void allocates to the node"
MSG_UNKNOWN_COST_CODE = "a cost code of the list does not exist in the project"
RELINK_REASON = "the cost code allocation of the node changed"

_NODES_SQL = text(
    "SELECT t.id, t.code, r.title, t.parent_id, t.depth, t.position, t.retired "
    f"FROM {WBS_NODE_TABLE} t JOIN cur_core_record r ON r.id = t.id WHERE t.scope = :scope"
)
_LINES_SQL = text(f"SELECT cost_code_id FROM {WBS_ALLOCATION_TABLE} WHERE node_id = :node")


@dataclass(frozen=True)
class Node:
    id: str
    code: str
    title: str
    parent_id: str | None
    depth: int
    position: int
    retired: bool


class Tree:
    """Every WBS node of a project, with the lookups the rules need."""

    def __init__(self, nodes: list[Node]) -> None:
        self.by_id = {n.id: n for n in nodes}
        self.by_code = {n.code: n for n in nodes}
        self._children: dict[str | None, list[Node]] = {}
        for n in nodes:
            self._children.setdefault(n.parent_id, []).append(n)
        for group in self._children.values():
            group.sort(key=lambda n: (n.position, n.code))

    def children(self, parent_id: str | None) -> list[Node]:
        return self._children.get(parent_id, [])

    def descendants(self, node_id: str) -> list[Node]:
        found: list[Node] = []
        todo = list(self.children(node_id))
        while todo:
            n = todo.pop()
            found.append(n)
            todo.extend(self.children(n.id))
        return found

    def find(self, conn: Connection, code: str) -> Node:
        """The node with ``code``; a node the viewer may not read answers as one that is absent."""
        node = self.by_code.get(code)
        if node is None or confidentiality.is_hidden(conn, node.id):
            raise CodeNotFoundError(MSG_NO_PARENT)
        return node


def load_tree(conn: Connection, scope: str) -> Tree:
    rows = conn.execute(_NODES_SQL, {"scope": scope})
    return Tree(
        [
            Node(
                id=str(r.id),
                code=str(r.code),
                title=str(r.title),
                parent_id=None if r.parent_id is None else str(r.parent_id),
                depth=int(r.depth),
                position=int(r.position),
                retired=bool(r.retired),
            )
            for r in rows
        ]
    )


def _require_free_code(conn: Connection, scope: str, code: str) -> None:
    """The code is free among the project's WBS nodes. The key is ``awp.wbs@<code>``, so a cost
    code, an area or a record the viewer may not read never makes it look taken."""
    if key_taken(conn, scope, WBS_NODE, code):
        raise DuplicateCodeError(MSG_DUPLICATE)


def _can_take_child(conn: Connection, parent: Node) -> None:
    """A leaf that has cost code lines or package allocations stays a leaf."""
    lines = conn.execute(_LINES_SQL, {"node": parent.id}).first()
    if lines is not None or cwp_allocates_to(conn, parent.id):
        raise WbsRuleError(MSG_HAS_ALLOCATION)


def _renumber(uow: UnitOfWork, cmd: Any, others: list[Node], gap: int | None) -> list[Any]:
    """Revise the siblings ``others`` (in order, without the node that moves) to 1..n, leaving a
    gap at place ``gap`` for the node that comes in (``None``: no gap, the node left)."""
    events: list[Any] = []
    for index, sibling in enumerate(others, start=1):
        wanted = index if gap is None or index < gap else index + 1
        if wanted != sibling.position:
            made = append(
                uow,
                cmd,
                sibling.id,
                WBS_NODE,
                [
                    NewEvent(
                        event_type=WBS_REVISED,
                        payload=silent({"changes": {"position": [sibling.position, wanted]}}),
                    )
                ],
            )
            events.extend(made.events)
    return events


def handle_define_wbs_node(uow: UnitOfWork, cmd: DefineWbsNode) -> CommandResult:
    """Create a node (``Record.Created``, ``WBSNode.Defined``) at a place among its siblings.

    Raises ``DuplicateCodeError``, ``CodeNotFoundError`` (the parent), ``WbsRuleError`` (depth,
    node count, a parent that is allocated, a position past the last sibling).
    """
    require_project(cmd)
    cmd = correlated(cmd)
    conn = uow.conn()
    tree = load_tree(conn, cmd.scope)
    _require_free_code(conn, cmd.scope, cmd.code)
    if len(tree.by_id) >= MAX_WBS_NODES:
        raise WbsRuleError(MSG_COUNT)
    parent = None if cmd.parent_code is None else tree.find(conn, cmd.parent_code)
    if parent is not None:
        _can_take_child(conn, parent)
    depth = 0 if parent is None else parent.depth + 1
    if depth >= MAX_WBS_DEPTH:
        raise WbsRuleError(MSG_DEPTH)
    parent_id = None if parent is None else parent.id
    siblings = tree.children(parent_id)
    position = len(siblings) + 1 if cmd.position is None else cmd.position
    if position > len(siblings) + 1:
        raise WbsRuleError(MSG_POSITION)
    made = create_coded_record(
        uow,
        cmd,
        record_type=WBS_NODE,
        title=cmd.title,
        code=cmd.code,
        extra_events=[
            NewEvent(
                event_type=WBS_DEFINED,
                payload=silent(
                    {
                        "code": cmd.code,
                        "parent_id": parent_id,
                        "depth": depth,
                        "position": position,
                    }
                ),
            )
        ],
    )
    events = list(made.events) + _renumber(uow, cmd, siblings, position)
    return CommandResult(
        stream_id=made.stream_id, key=cmd.code, version=made.version, events=events
    )


def handle_revise_wbs_node(uow: UnitOfWork, cmd: ReviseWbsNode) -> CommandResult:
    """Rename, move to another parent (``parent_code`` sent as null: the root) or re-order a node.

    A new title also appends ``Record.Updated`` (never the generic ``UpdateRecord``). A move
    shifts the depth of the node's descendants and the places of the siblings it leaves and joins.
    Raises ``RecordNotFoundError`` (the node), ``CodeNotFoundError``, ``WbsRuleError``,
    ``NoChangesError``.
    """
    require_project(cmd)
    cmd = correlated(cmd)
    conn = uow.conn()
    ref = load_record(uow, cmd.scope, cmd.node, WBS_NODE)
    tree = load_tree(conn, cmd.scope)
    node = tree.by_id[ref.id]
    moving = "parent_code" in cmd.model_fields_set
    new_parent = None
    parent_id = node.parent_id
    if moving:
        new_parent = None if cmd.parent_code is None else tree.find(conn, cmd.parent_code)
        parent_id = None if new_parent is None else new_parent.id
    parent_changed = moving and parent_id != node.parent_id
    others = [s for s in tree.children(parent_id) if s.id != node.id]
    position = node.position
    if cmd.position is not None:
        position = cmd.position
    elif parent_changed:
        position = len(others) + 1
    if position > len(others) + 1:
        raise WbsRuleError(MSG_POSITION)
    title_changed = cmd.title is not None and cmd.title != node.title
    if not (title_changed or parent_changed or position != node.position):
        raise NoChangesError("the request changes nothing")

    changes: dict[str, list[Any]] = {}
    events: list[Any] = []
    stream_events: list[NewEvent] = []
    below = tree.descendants(node.id)
    depth = node.depth
    if title_changed:
        assert cmd.title is not None
        changes["title"] = [node.title, cmd.title]
        stream_events.append(
            NewEvent(
                event_type="Record.Updated", payload={"changes": {"title": [node.title, cmd.title]}}
            )
        )
    if parent_changed:
        if parent_id == node.id or parent_id in {d.id for d in below}:
            raise WbsRuleError(MSG_CYCLE)
        if new_parent is not None:
            _can_take_child(conn, new_parent)
        depth = 0 if new_parent is None else new_parent.depth + 1
        reach = max((d.depth - node.depth for d in below), default=0)
        if depth + reach >= MAX_WBS_DEPTH:
            raise WbsRuleError(MSG_DEPTH)
        changes["parent_id"] = [node.parent_id, parent_id]
        if depth != node.depth:
            changes["depth"] = [node.depth, depth]
    if position != node.position or parent_changed:
        changes["position"] = [node.position, position]
    stream_events.append(NewEvent(event_type=WBS_REVISED, payload=silent({"changes": changes})))
    made = append(uow, cmd, node.id, WBS_NODE, stream_events)
    events.extend(made.events)
    if parent_changed:
        events.extend(
            _renumber(uow, cmd, [s for s in tree.children(node.parent_id) if s.id != node.id], None)
        )
        if depth != node.depth:
            shift = depth - node.depth
            for d in sorted(below, key=lambda n: (n.depth, n.code)):
                done = append(
                    uow,
                    cmd,
                    d.id,
                    WBS_NODE,
                    [
                        NewEvent(
                            event_type=WBS_REVISED,
                            payload=silent({"changes": {"depth": [d.depth, d.depth + shift]}}),
                        )
                    ],
                )
                events.extend(done.events)
        rollup.request(uow, cmd.scope)
    events.extend(_renumber(uow, cmd, others, position))
    return CommandResult(stream_id=node.id, key=node.code, version=made.new_version, events=events)


def handle_retire_wbs_node(uow: UnitOfWork, cmd: RetireWbsNode) -> CommandResult:
    """Retire a node. Refused while a package that is not void allocates to it.

    Raises ``RecordNotFoundError``, ``RetiredError``, ``InUseError``.
    """
    require_project(cmd)
    cmd = correlated(cmd)
    conn = uow.conn()
    ref = load_record(uow, cmd.scope, cmd.node, WBS_NODE)
    node = load_tree(conn, cmd.scope).by_id[ref.id]
    if node.retired:
        raise RetiredError(MSG_RETIRED)
    if cwp_allocates_to(conn, node.id):
        raise InUseError(MSG_IN_USE)
    made = append(
        uow,
        cmd,
        node.id,
        WBS_NODE,
        [NewEvent(event_type=WBS_RETIRED, payload=silent({"reason": cmd.reason}))],
    )
    rollup.request(uow, cmd.scope)
    return CommandResult(
        stream_id=node.id, key=node.code, version=made.new_version, events=made.events
    )


def handle_map_wbs_to_cost_codes(uow: UnitOfWork, cmd: MapWbsToCostCodes) -> CommandResult:
    """Replace the cost code allocation of a leaf node and keep its ``references`` links in step.

    The lines are 0 to 20 (none clears the allocation), a cost code once each, each percent from
    0.01 to 100.00, the sum exactly 100.00 when there are lines, and every cost code exists in the
    project. A retired node and a node with children take none. Events:
    ``WBSNode.CostCodesMapped``, then ``Link.Retracted`` for each link of a cost code that is no
    longer allocated and ``Link.Added`` for each allocated cost code that has no live link (a link
    that went missing is added again here). Raises ``RecordNotFoundError``, ``RetiredError``,
    ``WbsRuleError``, ``AllocationError``.
    """
    require_project(cmd)
    cmd = correlated(cmd)
    conn = uow.conn()
    ref = load_record(uow, cmd.scope, cmd.node, WBS_NODE)
    tree = load_tree(conn, cmd.scope)
    node = tree.by_id[ref.id]
    if node.retired:
        raise RetiredError(MSG_RETIRED)
    if tree.children(node.id):
        raise WbsRuleError(MSG_LEAF_ONLY)
    lines = check_allocations(
        [(line.cost_code, line.percent) for line in cmd.allocations], allow_empty=True
    )
    allocations: list[dict[str, str]] = []
    for code, percent in sorted(lines, key=lambda line: line[0]):
        found = resolve_code(conn, cmd.scope, COST_CODE, code)
        if found is None:
            raise AllocationError(MSG_UNKNOWN_COST_CODE)
        allocations.append({"cost_code_id": found, "code": code, "percent": percent_text(percent)})
    made = append(
        uow,
        cmd,
        node.id,
        WBS_NODE,
        [NewEvent(event_type=WBS_COST_CODES_MAPPED, payload=silent({"allocations": allocations}))],
    )
    events = list(made.events)
    events.extend(
        sync_links(
            uow,
            cmd,
            node.id,
            COST_RELATION,
            {a["cost_code_id"] for a in allocations},
            RELINK_REASON,
        )
    )
    rollup.request(uow, cmd.scope)
    return CommandResult(stream_id=node.id, key=node.code, version=made.new_version, events=events)
