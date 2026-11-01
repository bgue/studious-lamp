"""Acceptance for P2-I1-S4: CWP and owner package commands, workflow, actions, seed ledger.

Runs on SQLite; no network. Prints one ``PASS <check>`` line per check, then ``S4 ok``; exits 1 on
the first failure. Commands run as a person would run them: the access word is checked first
(``require_command_access``), then the handler, one unit of work each. The checks run on a scratch
ledger; ``--keep PATH`` then writes the seed ledger at PATH (WBS of 3 levels with 6 leaves, two
mapped to cost codes; 4 CWAs; path version 1; 6 CWPs over three states) for the tickets after S4.

Run: ``uv run python dev/accept/P2-I1/S4.py [--keep .accept/p2-i1.db]``.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy import text
from tl_adapters.db import as_target, create_schema, open_uow, rebuild_projections
from tl_core import confidentiality as cf
from tl_core.actions import allowed_actions
from tl_core.auth import accounts
from tl_core.auth.errors import ForbiddenError
from tl_core.auth.module_grants import GrantModuleRole, grant_module_role
from tl_core.auth.module_roles import holder_for_actor, require_command_access
from tl_core.auth.password import prepare_password
from tl_core.links.expected import missing_expected_links, parse_expected_links
from tl_core.schema_provider import DirectorySchemaProvider, use_provider
from tl_core.services import proposals
from tl_core.services.commands import Command
from tl_core.services.errors import (
    NoChangesError,
    RecordNotFoundError,
    UnsupportedRecordTypeError,
)
from tl_core.services.links import AddLink, RetractLink, handle_add_link, handle_retract_link
from tl_core.util import new_ulid
from tl_mod_awp.actions import RULES
from tl_mod_awp.commands import AWP_COMMANDS, CreateCwp
from tl_mod_awp.common import record_key
from tl_mod_awp.errors import (
    AllocationError,
    CwpStateError,
    DuplicateCodeError,
    ReleaseRefusedError,
    StaleVersionError,
    UnknownListCodeError,
    WbsRuleError,
)
from tl_mod_correspondence.handlers.create import create_item
from tl_mod_correspondence.handlers.models import Recipient
from tl_mod_correspondence.testing import frozen_today
from tl_mod_cost.testing import CostWorld, row
from tl_mod_engineering.document import load_standards_file
from tl_mod_engineering.loader import load_standards
from tl_mod_schedule.testing import BASE as SCHEDULE_BASE
from tl_mod_schedule.testing import ScheduleWorld
from tl_xer.synth import make_xer, week_pair

SCOPE = "project:P123"
PASSWORD = "correct horse battery"
ROOT = Path(__file__).resolve().parents[3]
STANDARDS = ROOT / "schema" / "fixtures" / "standards"
SPEC = {c.model.__name__: c for c in AWP_COMMANDS}
WBS, CWA, EWP, PWP = "awp.WBSNode", "awp.CWA", "awp.EWPRef", "awp.PWPRef"
COST = "cost.CostCode"
RELEASED = "Released for IWP development"


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
    """A ledger and the people who act on it: ``vera`` (viewer), ``uma`` (user), ``sue`` (the
    awp superuser, the table word ``controller``) and ``ada`` (admin)."""

    def __init__(self, path: Path) -> None:
        self.db = as_target(str(path))
        create_schema(self.db)

    def person(self, name: str, roles: tuple[str, ...], grant: str | None = None) -> None:
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
        if grant is not None:
            with open_uow(self.db) as uow:
                grant_module_role(
                    uow,
                    GrantModuleRole(
                        actor="user:ada",
                        source="accept",
                        account_id=view.account_id,
                        project=SCOPE,
                        module="awp",
                        role=grant,
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

    def id_of(self, code: str, kind: str = WBS) -> str:
        """The id of the record of ``kind`` with the typed ``code`` (awp keys are namespaced)."""
        return str(self.scalar("SELECT id FROM cur_core_record WHERE scope = :s AND key = :k",
                               s=SCOPE, k=record_key(kind, code)))  # fmt: skip

    def cwp_id(self, number: str) -> str:
        return str(self.scalar("SELECT id FROM cur_core_record WHERE key = :k", k=number))

    def state(self, cwp: str) -> str:
        return str(self.scalar("SELECT COALESCE(status, 'Planned') FROM cur_core_record "
                               "WHERE id = :i", i=cwp))  # fmt: skip

    def version(self, record: str) -> int:
        return int(self.scalar("SELECT version FROM cur_core_record WHERE id = :i", i=record))


def people(w: World) -> None:
    w.person("ada", ("admin",))
    w.person("vera", ("user",), grant="viewer")
    w.person("uma", ("user",))  # the derived role: user
    w.person("sue", ("user",), grant="superuser")


def editions(w: World) -> None:
    """The standards editions the lists come from: Discipline, UnitOfMeasure, then the awp lists."""
    with use_provider(DirectorySchemaProvider(ROOT / "schema" / "fixtures")):
        for name in ("co.acme.standards@1.0.0.yaml", "co.acme.awp@1.0.0.yaml"):
            doc = load_standards_file(STANDARDS / name)
            with open_uow(w.db) as uow:
                load_standards(uow, doc, actor="user:seed", source="accept")


def cost_codes(w: World, *codes: tuple[str, str]) -> None:
    CostWorld(w.db).import_snapshot([row(code, name) for code, name in codes])


def line(cost_code: str, percent: str) -> dict[str, str]:
    return {"cost_code": cost_code, "percent": percent}


# --- the seed pieces, shared by the checks and the seed ledger --------------------------------


def wbs_tree(w: World) -> None:
    """3 levels, 6 leaves: 1 > (1.1, 1.2) > (1.1.1 .. 1.1.3, 1.2.1 .. 1.2.3)."""
    w.call("sue", "DefineWbsNode", code="1", title="Plant")
    for mid in ("1.1", "1.2"):
        w.call("sue", "DefineWbsNode", code=mid, title=f"Unit {mid}", parent_code="1")
        for n in (1, 2, 3):
            code = f"{mid}.{n}"
            w.call("sue", "DefineWbsNode", code=code, title=f"Area {code}", parent_code=mid)


def areas_and_path(w: World) -> None:
    for code in ("A1", "A2", "A3", "A4"):
        w.call("uma", "DefineCwa", code=code, title=f"Area {code}", location_text="North")
    w.call(
        "sue", "DefinePathOfConstruction", steps=[{"cwa_code": c} for c in ("A1", "A2", "A3", "A4")]
    )


def new_cwp(w: World, discipline: str, title: str, cwa: str, **more: Any) -> str:
    made = w.call("uma", "CreateCwp", discipline=discipline, title=title, cwa_code=cwa, **more)
    return str(made.stream_id)


def full_cwp(w: World, discipline: str, title: str, cwa: str, node: str, hours: str) -> str:
    """A package that meets every precondition of a release, still Planned."""
    cwp = new_cwp(w, discipline, title, cwa, planned_start="2026-11-02",
                  planned_finish="2027-01-29", budget_hours=hours)  # fmt: skip
    w.call(
        "uma", "AllocateCwpToWbs", cwp=cwp, allocations=[{"wbs_code": node, "percent": "100.00"}]
    )
    return cwp


# --- the checks (scratch ledger) --------------------------------------------------------------


def step_one(w: World) -> None:
    cost_codes(w, ("1", "One"), ("4210-PIP-WLD", "Welding"), ("4210-PIP-ERC", "Erection"))
    w.call("sue", "DefineWbsNode", code="1", title="Plant")
    w.call("sue", "DefineCwa", code="1", title="Area one")
    key = w.scalar("SELECT key FROM cur_core_record WHERE id = :i", i=w.id_of("1"))
    need(key == "awp.wbs@1", f"the node key is {key}")
    refuses(DuplicateCodeError, lambda: w.call("sue", "DefineWbsNode", code="1", title="Again"))
    passed("node 1, area 1 and cost code 1 coexist; the same kind refuses a second 1")

    w.call("sue", "DefineWbsNode", code="1.1", title="Unit", parent_code="1")
    leaf = w.id_of("1.1")
    two = [line("4210-PIP-WLD", "60.00"), line("4210-PIP-ERC", "40.00")]
    w.call("sue", "MapWbsToCostCodes", node=leaf, allocations=two)
    w.call("sue", "MapWbsToCostCodes", node=leaf, allocations=[])
    live = w.rows("SELECT 1 FROM cur_links WHERE from_id = :n AND status <> 'retracted'", n=leaf)
    n = w.scalar("SELECT COUNT(*) FROM cur_awp_wbs_allocation WHERE node_id = :n", n=leaf)
    need(not live and n == 0, "an empty list should clear rows and links")
    passed("0 allocation lines clear the allocation and retract its links")

    w.call("sue", "MapWbsToCostCodes", node=leaf, allocations=two)
    erc = w.id_of("4210-PIP-ERC", COST)
    [gone] = w.rows("SELECT link_id FROM cur_links WHERE from_id = :n AND to_id = :t "
                    "AND status <> 'retracted'", n=leaf, t=erc)  # fmt: skip
    with open_uow(w.db) as uow:
        handle_retract_link(
            uow,
            RetractLink(
                actor="user:sue",
                source="accept",
                scope=SCOPE,
                link_id=gone["link_id"],
                reason="test",
            ),  # fmt: skip
            by_module=True,
        )
    w.call("sue", "MapWbsToCostCodes", node=leaf, allocations=two)
    back = w.rows(
        "SELECT to_id FROM cur_links WHERE from_id = :n AND status <> 'retracted'", n=leaf
    )
    need(len(back) == 2 and erc in {r["to_id"] for r in back}, f"links: {back}")
    passed("a deleted link is added again on the next change of the node")

    w.call("sue", "DefineCwa", code="A1", title="Area A1")
    w.call("sue", "DefineCwa", code="A2", title="Area A2")
    steps = [{"cwa_code": "A1"}, {"cwa_code": "A2"}]
    refuses(UnknownListCodeError, lambda: w.call("sue", "DefinePathOfConstruction", steps=[
        {"cwa_code": "A1", "reason_code": "Nonsense"}]))  # fmt: skip
    w.call("sue", "DefinePathOfConstruction", steps=steps)
    exc = refuses(UnknownListCodeError, lambda: w.call("sue", "MoveCwaInPath", cwa_code="A2",
                  to_position=1, reason_code="Nonsense", expected_version=1))  # fmt: skip
    need("Nonsense" not in str(exc), "the message must not repeat the code")
    w.call("sue", "MoveCwaInPath", cwa_code="A2", to_position=1, reason_code="Access",
           expected_version=1)  # fmt: skip
    passed("a reason code outside PathReason is refused, a listed one is taken")


def numbering_and_allocation(w: World) -> dict[str, str]:
    for code in ("1.2", "1.3"):
        w.call("sue", "DefineWbsNode", code=code, title=f"Unit {code}", parent_code="1")
    made = [
        w.call("uma", "CreateCwp", discipline="PIP", title="Rack 12 piping", cwa_code="A1",
               planned_start="2026-11-02", planned_finish="2027-01-29", budget_hours="4200",
               quantities=[{"commodity": "piping", "qty": "480", "uom": "m"}],
               contractor_text="Acme Mechanical"),
        w.call("uma", "CreateCwp", discipline="PIP", title="Rack 13 piping", cwa_code="A1"),
        w.call("uma", "CreateCwp", discipline="CIV", title="Slab 4", cwa_code="A2"),
    ]  # fmt: skip
    keys = [m.key for m in made]
    need(keys == ["P123-CWP-PIP-0001", "P123-CWP-PIP-0002", "P123-CWP-CIV-0001"], f"{keys}")
    need(w.scalar("SELECT budget_hours FROM cur_awp_cwp WHERE id = :i", i=made[0].stream_id)
         == "4200.0", "hours are kept with one decimal")  # fmt: skip
    passed("3 CWPs in two disciplines are numbered gap-free per discipline")

    a, b, c = (str(m.stream_id) for m in made)
    out = w.rows("SELECT 1 FROM cur_links WHERE from_id = :i AND relation = 'belongs_to' "
                 "AND source = 'rule' AND status <> 'retracted'", i=a)  # fmt: skip
    need(len(out) == 1, "one rule link to the area")
    sixty = [{"wbs_code": "1.2", "percent": "60.00"}, {"wbs_code": "1.3", "percent": "40.00"}]
    w.call("uma", "AllocateCwpToWbs", cwp=a, allocations=sixty)
    short = [{"wbs_code": "1.2", "percent": "60.00"}, {"wbs_code": "1.3", "percent": "39.99"}]
    parent = [{"wbs_code": "1", "percent": "100.00"}]
    refuses(AllocationError, lambda: w.call("uma", "AllocateCwpToWbs", cwp=a, allocations=short))
    refuses(WbsRuleError, lambda: w.call("uma", "AllocateCwpToWbs", cwp=b, allocations=parent))
    got = w.rows(
        "SELECT percent FROM cur_awp_cwp_allocation WHERE cwp_id = :i ORDER BY percent", i=a
    )
    links = w.rows("SELECT 1 FROM cur_links WHERE from_id = :i AND relation = 'belongs_to' "
                   "AND status <> 'retracted'", i=a)  # fmt: skip
    need([g["percent"] for g in got] == ["40.00", "60.00"] and len(links) == 3, f"{got} {links}")
    passed("allocate 60/40 (area and node links kept), 99.99 and a parent node refused")
    return {"a": a, "b": b, "c": c}


def workflow(w: World, ids: dict[str, str]) -> None:
    a = ids["a"]
    steps: list[tuple[str, str, str, str]] = [
        ("uma", "StartCwpDevelopment", "In development", "awp.cwp.edit"),
        ("sue", "ReleaseCwp", "Released for IWP development", "awp.cwp.release"),
        ("sue", "ReturnCwp", "In development", "awp.cwp.release"),
        ("sue", "ReleaseCwp", "Released for IWP development", "awp.cwp.release"),
        ("uma", "StartCwpExecution", "Executing", "awp.cwp.edit"),
        ("uma", "CompleteCwp", "Complete", "awp.cwp.edit"),
        ("sue", "ReopenCwp", "Executing", "awp.cwp.close"),
        ("uma", "CompleteCwp", "Complete", "awp.cwp.edit"),
        ("sue", "CloseCwp", "Closed", "awp.cwp.close"),
    ]
    refuses(ForbiddenError, lambda: w.call("vera", "StartCwpDevelopment", cwp=a))
    for who, name, state, word in steps:
        need(SPEC[name].access == word, f"{name} should need {word}")
        extra: dict[str, Any] = {"cwp": a}
        if name == "ReleaseCwp":
            extra["expected_version"] = w.version(a)
            if who == "sue":
                refuses(ForbiddenError, lambda e=dict(extra): w.call("uma", "ReleaseCwp", **e))
        if name in ("ReturnCwp", "ReopenCwp"):
            extra["reason"] = "scope change"
        if name == "CloseCwp":
            refuses(ForbiddenError, lambda: w.call("uma", "CloseCwp", cwp=a))
        w.call(who, name, **extra)
        need(w.state(a) == state, f"{name} should reach {state}, not {w.state(a)}")
    passed("every workflow move runs with its word; user refused ReleaseCwp and CloseCwp")
    [rel] = w.rows("SELECT payload FROM events WHERE event_type = 'CWP.Released' "
                   "AND stream_id = :i ORDER BY seq LIMIT 1", i=a)  # fmt: skip
    need("record_hash" in rel["payload"] and "user:sue" in rel["payload"], "CWP.Released payload")
    passed("CWP.Released carries the releasing person and the record hash")
    refuses(CwpStateError, lambda: w.call("sue", "VoidCwp", id=a, reason="late"))
    passed("a Closed package cannot be voided")


def release_rules(w: World, ids: dict[str, str]) -> None:
    b, c = ids["b"], ids["c"]
    w.call("uma", "StartCwpDevelopment", cwp=b)
    exc = refuses(ReleaseRefusedError, lambda: w.call("sue", "ReleaseCwp", cwp=b,
                  expected_version=w.version(b)))  # fmt: skip
    for word in ("budget hours", "planned start", "sum to 100.00"):
        need(word in str(exc), f"the refusal should name {word}: {exc}")
    w.call("uma", "ReviseCwp", cwp=b, budget_hours="120.5", planned_start="2026-12-01",
           planned_finish="2026-12-31")  # fmt: skip
    refuses(ReleaseRefusedError, lambda: w.call("sue", "ReleaseCwp", cwp=b,
            expected_version=w.version(b)))  # fmt: skip
    passed("release refused without budget hours, dates or an allocation summing to 100")

    w.call("uma", "AllocateCwpToWbs", cwp=b, allocations=[{"wbs_code": "1.2", "percent": "100"}])
    stale = w.version(b)
    w.call("uma", "ReviseCwp", cwp=b, contractor_text="Acme")
    refuses(StaleVersionError, lambda: w.call("sue", "ReleaseCwp", cwp=b, expected_version=stale))
    w.call("sue", "ReleaseCwp", cwp=b, expected_version=w.version(b))
    passed("a stale expected_version is refused; the current one releases")
    declared = parse_expected_links((ROOT / "schema/modules/awp/cwp.yaml").read_text())
    with open_uow(w.db, readonly=True) as uow:
        miss = missing_expected_links(uow, b, registry=declared, by_state=RELEASED)
    need(len(miss) == 1 and miss[0].expectation.target_type == EWP, f"expected links: {miss}")
    passed("released with no awp.EWPRef link: reported as a missing expected link, not refused")

    for name, fields in (("ReviseCwp", {"title": "New"}), ("AllocateCwpToWbs", {"allocations": [
            {"wbs_code": "1.3", "percent": "100.00"}]})):  # fmt: skip
        refuses(CwpStateError, lambda n=name, f=fields: w.call("uma", n, cwp=b, **f))
    w.call("sue", "ReturnCwp", cwp=b, reason="rework")
    w.call("uma", "ReviseCwp", cwp=b, title="Rack 13 piping, revised")
    need(w.scalar("SELECT title FROM cur_core_record WHERE id = :i", i=b)
         == "Rack 13 piping, revised", "the title should change")  # fmt: skip
    passed("fields frozen after release; ReturnCwp opens them again")

    exc = refuses(CwpStateError, lambda: w.call("uma", "CompleteCwp", cwp=c))
    need("Planned" in str(exc), "the refusal names the state")
    w.call(
        "uma",
        "ReviseCwp",
        cwp=c,
        quantities=[{"commodity": "concrete", "qty": "12.5", "uom": "m3"}],
    )
    refuses(UnknownListCodeError, lambda: w.call("uma", "ReviseCwp", cwp=c, quantities=[
        {"commodity": "gold", "qty": "1", "uom": "m3"}]))  # fmt: skip
    refuses(UnknownListCodeError, lambda: w.call("uma", "CreateCwp", discipline="ZZZ",
            title="x", cwa_code="A1"))  # fmt: skip
    refuses(NoChangesError, lambda: w.call("uma", "ReviseCwp", cwp=c, title="Slab 4"))
    w.call("sue", "VoidCwp", id=c, reason="not needed")
    need(w.state(c) == "Void", "VoidCwp should reach Void")
    refuses(ForbiddenError, lambda: w.call("uma", "VoidCwp", id=ids["a"], reason="x"))
    passed("revise checks lists and changes; VoidCwp (superuser) voids, user refused")


def not_closed(w: World, ids: dict[str, str]) -> None:
    for name in ("a", "c"):  # a is Closed, c is Void
        link = AddLink(actor="user:uma", source="accept", scope=SCOPE, from_id=ids[name],
                       to_id=w.id_of("1.2"), relation="references")  # fmt: skip
        with open_uow(w.db) as uow:
            refuses(UnsupportedRecordTypeError, lambda lk=link, u=uow: handle_add_link(u, lk))
    passed("a Closed or Void package takes no generic link (not_closed)")


def packages(w: World) -> None:
    kinds = (("ewp", "EWP-0042", EWP), ("pwp", "PWP-0042", PWP))
    for kind, number, record_type in kinds:
        w.call("uma", "RecordExternalPackage", package_type=kind, package_no=number,
               title=f"Package {number}", status_text="In review", forecast_date="2026-11-20",
               constraint_source=True, source_system="Owner portal")  # fmt: skip
        pid = w.id_of(number, record_type)
        table = "cur_awp_ewp_ref" if kind == "ewp" else "cur_awp_pwp_ref"
        again = {"package_type": kind, "package_no": number, "title": "Again"}
        refuses(DuplicateCodeError, lambda a=again: w.call(
            "uma", "RecordExternalPackage", constraint_source=False, **a))  # fmt: skip
        w.call("uma", "UpdateExternalPackage", id=pid, status_text="Approved",
               constraint_source=False, actual_date="2026-11-18")  # fmt: skip
        got = w.rows(f"SELECT status_text, constraint_source, actual_date FROM {table}")
        need(got == [{"status_text": "Approved", "constraint_source": 0,
                      "actual_date": "2026-11-18"}], f"{got}")  # fmt: skip
        refuses(NoChangesError, lambda i=pid: w.call("uma", "UpdateExternalPackage", id=i,
                status_text="Approved"))  # fmt: skip
        refuses(
            ForbiddenError, lambda i=pid: w.call("uma", "VoidExternalPackage", id=i, reason="x")
        )
        w.call("sue", "VoidExternalPackage", id=pid, reason="withdrawn")
        need(bool(w.scalar("SELECT voided FROM cur_core_record WHERE id = :i", i=pid)), "voided")
    passed("EWP and PWP: record, update, refuse a repeat number, void by the superuser only")


def rules_words() -> None:
    for rule in RULES:
        need(rule.command in SPEC, f"{rule.command} is not a command")
        need(rule.word == SPEC[rule.command].access, f"{rule.command}: word {rule.word}")
    passed(f"RULES: the word of each of the {len(RULES)} rows equals the command's word")


def offers(w: World, ids: dict[str, str]) -> None:
    level = {"vera": 0, "uma": 1, "sue": 2}
    rank = {"user": 1, "controller": 2, "admin": 3}

    def names(who: str, record: str) -> list[str]:
        with open_uow(w.db, readonly=True) as uow:
            found = allowed_actions(
                uow, record, actor=f"user:{who}", holds=lambda want: level[who] >= rank[want]
            )
        return [o.command for o in found.actions]

    b = ids["b"]  # In development after the return
    need(names("uma", b) == ["ReviseCwp", "AllocateCwpToWbs"], f"{names('uma', b)}")
    need(names("sue", b)[2:] == ["ReleaseCwp", "VoidCwp"], f"{names('sue', b)}")
    need(names("vera", b) == [], "a viewer is offered nothing")
    need(names("sue", ids["c"]) == [], "a void package is offered nothing")
    passed("offers follow the state and the level: user, superuser, viewer, void")


def proposal(w: World) -> None:
    cmd = CreateCwp(actor="agent:planner", source="mcp:planner", scope=SCOPE,
                    discipline="PIP", title="Proposed piping", cwa_code="A2")  # fmt: skip
    with open_uow(w.db) as uow:
        made = proposals.propose(uow, tool="propose_cwp", agent="agent:planner", command=cmd,
                                 summary="A new piping package")  # fmt: skip
    before = w.scalar("SELECT COUNT(*) FROM cur_core_record WHERE type = 'awp.CWP'")
    need(made.status == "pending", "the proposal should wait")

    def accept(who: str) -> Any:
        with open_uow(w.db) as uow:
            return proposals.accept_proposal(
                uow, proposal_id=made.proposal_id, by=f"user:{who}",
                holds=lambda level: level == "user",
                holder=holder_for_actor(uow.conn(), f"user:{who}"),
            )  # fmt: skip

    refuses(proposals.ProposalAccessError, lambda: accept("vera"))
    need(w.scalar("SELECT COUNT(*) FROM cur_core_record WHERE type = 'awp.CWP'") == before, "waits")
    done = accept("uma")
    after = w.scalar("SELECT COUNT(*) FROM cur_core_record WHERE type = 'awp.CWP'")
    need(done.status == "accepted" and after == before + 1, f"{done.status} {before} {after}")
    passed("propose_cwp waits; a viewer cannot accept it; a user does and the CWP is made")


def hidden_id(w: World) -> None:
    cmd = Command(actor="user:sue", source="accept", scope=SCOPE)
    with cf.system_view(), frozen_today("2026-10-19"), open_uow(w.db) as uow:
        made = create_item(
            uow, cmd, subject="Secret", direction="in", medium="letter", received_via="manual",
            to=[Recipient(name="Someone")], body="Body", confidentiality="restricted",
            received_on="2026-10-19", received=True,
        )  # fmt: skip
    hidden, absent = made.stream_id, new_ulid()
    texts = []
    for target in (hidden, absent):
        tries = (
            ("StartCwpDevelopment", {"cwp": target}),
            ("VoidCwp", {"id": target, "reason": "x"}),
            ("UpdateExternalPackage", {"id": target, "status_text": "x"}),
        )
        for name, fields in tries:
            texts.append(
                str(refuses(RecordNotFoundError, lambda n=name, f=fields: w.call("sue", n, **f)))
            )
    half = len(texts) // 2
    same = [
        a.replace(hidden, "ID") == b.replace(absent, "ID")
        for a, b in zip(texts[:half], texts[half:], strict=True)
    ]
    need(all(same), "hidden and absent differ")
    passed("a hidden id answers as a missing one on CWP and package commands")


def link_activity(w: World, ids: dict[str, str]) -> None:
    SCHEDULE_BASE["actor"] = "user:sue"  # an account, so the schedule words are read for her
    with tempfile.TemporaryDirectory() as objects:
        world = ScheduleWorld(w.db, Path(objects))
        world.define()
        first, _ = week_pair()
        snapshot = world.upload(make_xer(first))
        world.publish(snapshot)
        activity = world.activities(snapshot)[0].activity_id
        made = world.link(ids["b"], activity)
        link = world.link_row(made.stream_id)
    need(link["from_id"] == ids["b"] and link["status"] == "active", f"{link}")
    passed("LinkActivity from a CWP is accepted by the source-end check")


def rollup_queue(w: World) -> None:
    rows = w.rows("SELECT job_id, kind, state FROM job_queue WHERE kind = 'awp.rollup'")
    need(
        rows == [{"job_id": f"rollup:{SCOPE}", "kind": "awp.rollup", "state": "queued"}], f"{rows}"
    )
    w.call("uma", "RequestRollup")
    need(len(w.rows("SELECT 1 FROM job_queue WHERE kind = 'awp.rollup'")) == 1, "one row")
    passed("the rollup is queued once after several budget and allocation changes")


TABLES = (
    ("cur_awp_wbs_node", "id"),
    ("cur_awp_wbs_allocation", "row_id"),
    ("cur_awp_path", "id"),
    ("cur_awp_path_step", "row_id"),
    ("cur_awp_cwa", "id"),
    ("cur_awp_cwp", "id"),
    ("cur_awp_cwp_allocation", "row_id"),
    ("cur_awp_ewp_ref", "id"),
    ("cur_awp_pwp_ref", "id"),
    ("cur_core_record", "id"),
    ("cur_links", "link_id"),
)


def rebuild(w: World) -> None:
    before = {t: w.rows(f"SELECT * FROM {t} ORDER BY {order}") for t, order in TABLES}
    need(len(before["cur_awp_cwp"]) == 4 and len(before["cur_awp_ewp_ref"]) == 1, "seeded rows")
    rebuild_projections(w.db)
    after = {t: w.rows(f"SELECT * FROM {t} ORDER BY {order}") for t, order in TABLES}
    need(after == before, "a rebuild differs from the incremental tables")
    passed("rebuild equals the incremental tables")


def checks(work: Path) -> None:
    w = World(work / "scratch.db")
    people(w)
    editions(w)
    step_one(w)
    ids = numbering_and_allocation(w)
    workflow(w, ids)
    release_rules(w, ids)
    not_closed(w, ids)
    packages(w)
    rules_words()
    offers(w, ids)
    proposal(w)
    hidden_id(w)
    link_activity(w, ids)
    rollup_queue(w)
    rebuild(w)


# --- the seed ledger ---------------------------------------------------------------------------


def seed_ledger(path: Path) -> None:
    """WBS (3 levels, 6 leaves, two mapped to cost codes), 4 CWAs, path v1, 6 CWPs in 3 states."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    w = World(path)
    people(w)
    editions(w)
    cost_codes(w, ("4210-PIP-WLD", "Welding"), ("4210-PIP-ERC", "Erection"),
               ("4210-PIP-TST", "Test"), ("4210-CIV-CON", "Concrete"))  # fmt: skip
    wbs_tree(w)
    w.call("sue", "MapWbsToCostCodes", node=w.id_of("1.1.1"),
           allocations=[line("4210-PIP-WLD", "60.00"), line("4210-PIP-ERC", "40.00")])  # fmt: skip
    w.call("sue", "MapWbsToCostCodes", node=w.id_of("1.2.1"),
           allocations=[line("4210-CIV-CON", "100.00")])  # fmt: skip
    areas_and_path(w)
    plan = [  # discipline, title, area, node, hours, how far it goes
        ("PIP", "Rack 12 piping", "A1", "1.1.1", "4200", "released"),
        ("PIP", "Rack 13 piping", "A1", "1.1.2", "1800", "released"),
        ("PIP", "Rack 14 piping", "A2", "1.1.3", "950", "development"),
        ("CIV", "Foundations unit 2", "A3", "1.2.1", "3100", "development"),
        ("CIV", "Slab unit 2", "A3", "1.2.2", "640", "planned"),
        ("PIP", "Tie-ins", "A4", "1.2.3", "400", "planned"),
    ]
    for discipline, title, area, node, hours, goal in plan:
        cwp = full_cwp(w, discipline, title, area, node, hours)
        if goal in ("development", "released"):
            w.call("uma", "StartCwpDevelopment", cwp=cwp)
        if goal == "released":
            w.call("sue", "ReleaseCwp", cwp=cwp, expected_version=w.version(cwp))
    states = w.rows("SELECT COALESCE(status, 'Planned') AS s, COUNT(*) AS n FROM cur_core_record "
                    "WHERE type = 'awp.CWP' GROUP BY 1 ORDER BY 1")  # fmt: skip
    need(sum(r["n"] for r in states) == 6 and len(states) == 3, f"states: {states}")
    leaves = w.scalar(
        "SELECT COUNT(*) FROM cur_awp_wbs_node n WHERE NOT EXISTS "
        "(SELECT 1 FROM cur_awp_wbs_node c WHERE c.parent_id = n.id)"
    )
    need(leaves == 6, "6 leaves")
    passed(f"seed ledger {path}: WBS 3 levels/6 leaves, 4 CWAs, path v1, 6 CWPs in 3 states")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep", type=Path, help="write the seed ledger at this path")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        checks(Path(tmp))
    if args.keep is not None:
        seed_ledger(args.keep)
    print("S4 ok")


if __name__ == "__main__":
    try:
        main()
    except Failed as exc:
        print(f"FAIL {exc}")
        sys.exit(1)
