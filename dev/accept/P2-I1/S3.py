"""Acceptance for P2-I1-S3: the awp package (WBS, cost-code mapping, path of construction, CWA).

Runs on SQLite with a temp ledger; no network. Prints one ``PASS <check>`` line per check, then
``S3 ok``; exits 1 on the first failure. Commands run as a person would run them: the access word is
checked first (``require_command_access``), then the handler, one unit of work each.

Run: ``uv run python dev/accept/P2-I1/S3.py``.
"""

from __future__ import annotations

import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy import text
from tl_adapters.db import as_target, create_schema, open_uow, rebuild_projections
from tl_core import confidentiality as cf
from tl_core.auth import accounts
from tl_core.auth.errors import ForbiddenError
from tl_core.auth.module_grants import GrantModuleRole, grant_module_role
from tl_core.auth.module_roles import require_command_access
from tl_core.auth.password import prepare_password
from tl_core.schema_provider import DirectorySchemaProvider, use_provider
from tl_core.services.commands import Command
from tl_core.services.errors import RecordNotFoundError, UnsupportedRecordTypeError
from tl_core.services.links import RetractLink, handle_retract_link
from tl_core.util import new_ulid
from tl_mod_awp.commands import AWP_COMMANDS
from tl_mod_awp.common import record_key
from tl_mod_awp.errors import (
    AllocationError,
    StaleVersionError,
    WbsRuleError,
)
from tl_mod_correspondence.handlers.create import create_item
from tl_mod_correspondence.handlers.models import Recipient
from tl_mod_correspondence.testing import frozen_today
from tl_mod_cost.testing import CostWorld, row
from tl_mod_engineering.document import load_standards_file
from tl_mod_engineering.loader import load_standards

SCOPE = "project:P123"
ROOT = Path(__file__).resolve().parents[3]
STANDARDS = ROOT / "schema" / "fixtures" / "standards"
PASSWORD = "correct horse battery"
SPEC = {c.model.__name__: c for c in AWP_COMMANDS}


class Failed(Exception):
    pass


def passed(check: str) -> None:
    print(f"PASS {check}")


def need(ok: bool, what: str) -> None:
    if not ok:
        raise Failed(what)


def refuses(error: type[BaseException], call: Callable[[], Any]) -> BaseException:
    try:
        call()
    except error as exc:
        return exc
    raise Failed(f"expected {error.__name__}")


class World:
    def __init__(self, work: Path) -> None:
        self.db = as_target(str(work / "ledger.db"))
        create_schema(self.db)

    def person(self, name: str, roles: tuple[str, ...]) -> None:
        with open_uow(self.db) as uow:
            view = accounts.create_account(
                uow,
                username=name,
                display_name=name.title(),
                kind="person",
                roles=list(roles),
                password=prepare_password(PASSWORD, username=name),
                by="svc:accept",
            )
        setattr(self, f"id_{name}", view.account_id)

    def grant(self, name: str, role: str) -> None:
        with open_uow(self.db) as uow:
            grant_module_role(
                uow,
                GrantModuleRole(
                    actor="user:ada",
                    source="accept",
                    account_id=getattr(self, f"id_{name}"),
                    project=SCOPE,
                    module="awp",
                    role=role,
                    reason="acceptance",
                ),
            )

    def call(self, who: str, name: str, **fields: Any) -> Any:
        spec = SPEC[name]
        cmd = spec.model(actor=f"user:{who}", source="accept", scope=SCOPE, **fields)
        with open_uow(self.db) as uow:
            require_command_access(uow.conn(), cmd)
            return spec.handler(uow, cmd)

    def scalar(self, sql: str, **params: Any) -> Any:
        with open_uow(self.db, readonly=True) as uow:
            return uow.conn().execute(text(sql), params).scalar_one()

    def rows(self, sql: str, **params: Any) -> list[dict[str, Any]]:
        with open_uow(self.db, readonly=True) as uow:
            return [dict(r) for r in uow.conn().execute(text(sql), params).mappings()]

    def id_of(self, code: str, kind: str = "awp.WBSNode") -> str:
        """The id of the record of ``kind`` with the typed ``code`` (awp keys are namespaced)."""
        return str(self.scalar("SELECT id FROM cur_core_record WHERE scope = :s AND key = :k",
                               s=SCOPE, k=record_key(kind, code)))  # fmt: skip


def load_editions(w: World) -> None:
    """The standards editions the path reasons come from (``PathReason`` of co.acme.awp)."""
    with use_provider(DirectorySchemaProvider(ROOT / "schema" / "fixtures")):
        for name in ("co.acme.standards@1.0.0.yaml", "co.acme.awp@1.0.0.yaml"):
            doc = load_standards_file(STANDARDS / name)
            with open_uow(w.db) as uow:
                load_standards(uow, doc, actor="user:seed", source="accept")


def seed(w: World) -> None:
    load_editions(w)
    w.person("ada", ("admin",))
    w.person("vera", ("user",))  # viewer by an explicit grant
    w.person("uma", ("user",))  # the derived role: user
    w.person("sue", ("user",))  # superuser by an explicit grant
    w.grant("vera", "viewer")
    w.grant("sue", "superuser")
    CostWorld(w.db).import_snapshot(
        [
            row("4210-PIP-WLD", "Welding"),
            row("4210-PIP-ERC", "Erection"),
            row("4210-PIP-TST", "Test"),
        ]
    )


def wbs_and_allocation(w: World) -> None:
    for code, parent in (("1", None), ("1.1", "1"), ("1.1.1", "1.1"), ("1.1.2", "1.1")):
        w.call("sue", "DefineWbsNode", code=code, title=f"Node {code}", parent_code=parent)
    nodes = w.rows("SELECT code, depth, position FROM cur_awp_wbs_node ORDER BY code")
    need(
        [(n["code"], n["depth"], n["position"]) for n in nodes]
        == [("1", 0, 1), ("1.1", 1, 1), ("1.1.1", 2, 1), ("1.1.2", 2, 2)],
        f"the WBS rows are wrong: {nodes}",
    )
    passed("3-level WBS defined")
    leaf = w.id_of("1.1.1")
    lines = [
        {"cost_code": "4210-PIP-WLD", "percent": "60.00"},
        {"cost_code": "4210-PIP-ERC", "percent": "40.00"},
    ]
    w.call("sue", "MapWbsToCostCodes", node=leaf, allocations=lines)
    got = w.rows("SELECT percent FROM cur_awp_wbs_allocation WHERE node_id = :n ORDER BY percent",
                 n=leaf)  # fmt: skip
    need([g["percent"] for g in got] == ["40.00", "60.00"], f"allocation rows: {got}")
    passed("leaf mapped to two cost codes 60/40")

    bad = [{"cost_code": "4210-PIP-WLD", "percent": "60.00"},
           {"cost_code": "4210-PIP-ERC", "percent": "39.99"}]  # fmt: skip
    exc = refuses(
        AllocationError, lambda: w.call("sue", "MapWbsToCostCodes", node=leaf, allocations=bad)
    )
    need("99.99" in str(exc), "the sum message should say the sum")
    passed("sum 99.99 refused")
    refuses(WbsRuleError, lambda: w.call("sue", "MapWbsToCostCodes", node=w.id_of("1.1"),
            allocations=[{"cost_code": "4210-PIP-TST", "percent": "100.00"}]))  # fmt: skip
    passed("allocation on a parent refused")
    twice = [{"cost_code": "4210-PIP-WLD", "percent": "50.00"}] * 2
    refuses(
        AllocationError, lambda: w.call("sue", "MapWbsToCostCodes", node=leaf, allocations=twice)
    )
    passed("repeated cost code refused")
    unknown = [{"cost_code": "NO-SUCH-CODE", "percent": "100.00"}]
    exc = refuses(
        AllocationError, lambda: w.call("sue", "MapWbsToCostCodes", node=leaf, allocations=unknown)
    )
    need("NO-SUCH-CODE" not in str(exc), "the message must not hold the cell text")
    passed("unknown cost code refused, no cell text")
    refuses(WbsRuleError, lambda: w.call("sue", "DefineWbsNode", code="1.1.1.1", title="Child",
            parent_code="1.1.1"))  # fmt: skip
    passed("allocated leaf takes no child")


def depth_bound(w: World) -> None:
    parent = "1.1.2"
    for level in range(3, 8):  # depth 3..7: the eighth level
        code = f"D{level}"
        w.call("sue", "DefineWbsNode", code=code, title=code, parent_code=parent)
        parent = code
    refuses(
        WbsRuleError,
        lambda: w.call("sue", "DefineWbsNode", code="D8", title="D8", parent_code="D7"),
    )
    need(w.scalar("SELECT MAX(depth) FROM cur_awp_wbs_node") == 7, "depth 7 is the deepest")
    passed("ninth level refused")


def path_and_areas(w: World) -> None:
    for code in ("A1", "A2", "A3"):
        w.call("sue", "DefineCwa", code=code, title=f"Area {code}", location_text="North")
    w.call("uma", "DefineCwa", code="A4", title="Area A4")  # awp.cwa.edit is a user word
    made = w.call(
        "sue", "DefinePathOfConstruction", steps=[{"cwa_code": c} for c in ("A1", "A2", "A3", "A4")]
    )
    need(made.key == "P123-POC", f"path key {made.key}")
    codes = w.rows("SELECT c.code FROM cur_awp_path_step s JOIN cur_awp_cwa c ON c.id = s.cwa_id "
                   "WHERE s.version = 1 ORDER BY s.position")  # fmt: skip
    need([c["code"] for c in codes] == ["A1", "A2", "A3", "A4"], "path v1 order")
    passed("4 CWAs and path version 1")
    w.call(
        "sue",
        "MoveCwaInPath",
        cwa_code="A4",
        to_position=1,
        reason_code="Access",
        expected_version=1,
    )
    v2 = w.rows("SELECT c.code FROM cur_awp_path_step s JOIN cur_awp_cwa c ON c.id = s.cwa_id "
                "WHERE s.version = 2 ORDER BY s.position")  # fmt: skip
    need([c["code"] for c in v2] == ["A4", "A1", "A2", "A3"], "path v2 order")
    need(w.scalar("SELECT current_version FROM cur_awp_path") == 2, "current version 2")
    need(w.scalar("SELECT COUNT(*) FROM cur_awp_path_step WHERE version = 1") == 4, "v1 kept")
    passed("move with the right expected_version makes version 2, version 1 kept")
    refuses(StaleVersionError, lambda: w.call("sue", "MoveCwaInPath", cwa_code="A3", to_position=1,
            reason_code="Access", expected_version=1))  # fmt: skip
    passed("stale expected_version refused")


def words(w: World) -> None:
    refuses(ForbiddenError, lambda: w.call("uma", "DefineWbsNode", code="9", title="Nine"))
    w.call("sue", "DefineWbsNode", code="9", title="Nine")
    refuses(ForbiddenError, lambda: w.call("uma", "MoveCwaInPath", cwa_code="A1", to_position=2,
            reason_code="Access", expected_version=2))  # fmt: skip
    refuses(ForbiddenError, lambda: w.call("vera", "DefineCwa", code="A5", title="Area A5"))
    passed(
        "user refused DefineWbsNode and MoveCwaInPath, viewer refused DefineCwa, controller allowed"
    )


def hidden_id(w: World) -> None:
    cmd = Command(actor="user:ctl", source="accept", scope=SCOPE)
    with cf.system_view(), frozen_today("2026-10-19"), open_uow(w.db) as uow:
        made = create_item(
            uow, cmd, subject="Secret", direction="in", medium="letter", received_via="manual",
            to=[Recipient(name="Someone")], body="Body", confidentiality="restricted",
            received_on="2026-10-19", received=True,
        )  # fmt: skip
    hidden, absent = made.stream_id, new_ulid()
    a = refuses(
        RecordNotFoundError, lambda: w.call("sue", "RetireWbsNode", node=hidden, reason="x")
    )
    b = refuses(
        RecordNotFoundError, lambda: w.call("sue", "RetireWbsNode", node=absent, reason="x")
    )
    need(str(a).replace(hidden, "ID") == str(b).replace(absent, "ID"), "hidden and absent differ")
    passed("a hidden id answers as a missing one")


def links(w: World) -> None:
    leaf = w.id_of("1.1.1")
    live = w.rows("SELECT link_id, source, relation FROM cur_links WHERE from_id = :n "
                  "AND status <> 'retracted'", n=leaf)  # fmt: skip
    need(len(live) == 2 and {r["source"] for r in live} == {"rule"}, f"links: {live}")
    need({r["relation"] for r in live} == {"references"}, "relation references")
    passed("two rule links from the leaf to its cost codes")

    def person_retracts() -> Any:
        with open_uow(w.db) as uow:
            cmd = RetractLink(actor="user:uma", source="accept", scope=SCOPE,
                              link_id=live[0]["link_id"], reason="no longer needed")  # fmt: skip
            return handle_retract_link(uow, cmd)

    refuses(UnsupportedRecordTypeError, person_retracts)
    passed("a person cannot retract the links")
    w.call(
        "sue",
        "MapWbsToCostCodes",
        node=leaf,
        allocations=[{"cost_code": "4210-PIP-WLD", "percent": "100"}],
    )
    now = w.rows("SELECT to_id FROM cur_links WHERE from_id = :n AND status <> 'retracted'", n=leaf)
    need(
        [r["to_id"] for r in now] == [w.id_of("4210-PIP-WLD", "cost.CostCode")],
        f"links after remap: {now}",
    )
    passed("links kept in step when the allocation changes")


def rollup_queue(w: World) -> None:
    rows = w.rows("SELECT job_id, kind, state FROM job_queue WHERE kind = 'awp.rollup'")
    need(
        rows == [{"job_id": f"rollup:{SCOPE}", "kind": "awp.rollup", "state": "queued"}], f"{rows}"
    )
    passed("rollup queued once after several changes")


TABLES = (
    ("cur_awp_wbs_node", "id"),
    ("cur_awp_wbs_allocation", "row_id"),
    ("cur_awp_path", "id"),
    ("cur_awp_path_step", "row_id"),
    ("cur_awp_cwa", "id"),
    ("cur_core_record", "id"),
    ("cur_links", "link_id"),
)


def rebuild(w: World) -> None:
    before = {t: w.rows(f"SELECT * FROM {t} ORDER BY {order}") for t, order in TABLES}
    need(
        len(before["cur_awp_wbs_node"]) == 10 and len(before["cur_awp_path_step"]) == 8,
        "seeded rows",
    )
    rebuild_projections(w.db)
    after = {t: w.rows(f"SELECT * FROM {t} ORDER BY {order}") for t, order in TABLES}
    need(after == before, "a rebuild differs from the incremental tables")
    passed("rebuild equals the incremental tables")


def feed(w: World) -> None:
    cards = {
        r["event_type"]
        for r in w.rows("SELECT event_type FROM cur_feed_items WHERE item_type = 'card'")
    }
    need("Record.Created" in cards, f"Record.Created should make a card: {cards}")
    silent = {e for e in cards if e.startswith(("WBSNode.", "PathOfConstruction.", "CWP."))}
    need(not silent, f"cards for silent events: {silent}")
    need(
        w.scalar("SELECT COUNT(*) FROM events WHERE event_type = 'WBSNode.Defined'") >= 10, "events"
    )
    passed("WBSNode.Defined makes no card, Record.Created does")


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        w = World(Path(tmp))
        seed(w)
        wbs_and_allocation(w)
        depth_bound(w)
        path_and_areas(w)
        words(w)
        hidden_id(w)
        links(w)
        rollup_queue(w)
        rebuild(w)
        feed(w)
    print("S3 ok")


if __name__ == "__main__":
    try:
        main()
    except Failed as exc:
        print(f"FAIL {exc}")
        sys.exit(1)
