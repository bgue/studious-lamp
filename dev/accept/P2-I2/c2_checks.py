"""The checks and the seed of C2.py (core constraint commands); kept here so the script stays
short."""

from __future__ import annotations

import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages/tl-modules/awp/tests"))
import s2_checks as s2  # noqa: E402
from awp_world import SCOPE, World, hidden_record, refuses  # noqa: E402
from sqlalchemy import text  # noqa: E402
from tl_adapters.db import as_target, create_schema, open_uow, rebuild_projections  # noqa: E402
from tl_core import confidentiality as cf  # noqa: E402
from tl_core.auth.errors import ForbiddenError  # noqa: E402
from tl_core.auth.module_grants import GrantModuleRole, grant_module_role  # noqa: E402
from tl_core.constraints import (  # noqa: E402
    ConstraintRuleError,
    ConstraintSourceError,
    ConstraintStateError,
    PhaseNotGatedError,
    clear_constraint,
    command_table,
    open_blocking,
    queries,
    raise_constraint,
)
from tl_core.services.errors import GuardFailedError, RecordNotFoundError  # noqa: E402
from tl_core.services.workflow import TransitionWorkflow, handle_transition_workflow  # noqa: E402

CMDS = {c.model.__name__: c for c in command_table()}
H1, H2, H3 = "a" * 64, "b" * 64, "c" * 64
VIEWERS = {  # the five readers: default, user, agent, controller, admin
    "default": cf.LOWEST,
    "user": cf.Viewer("user:user", 0, "user:user"),
    "agent": cf.Viewer("agent:bot", 0, ""),
    "controller": cf.Viewer("user:controller", 1, "user:controller"),
    "admin": cf.Viewer("user:ada", 1, "user:ada"),
}


def ok(name: str, cond: bool = True) -> None:
    sys.exit(f"FAIL {name}") if not cond else print(f"PASS {name}")


class C2(World):
    def run(self, who: str, name: str, **f: Any) -> Any:
        spec = CMDS[name]
        cmd = spec.model(actor=f"user:{who}", source="test", scope=SCOPE, **f)
        with open_uow(self.db) as uow, cf.use_viewer(cf.viewer_for_actor(uow.conn(), cmd.actor)):
            return spec.handler(uow, cmd)

    def mod(self, fn: Any, **f: Any) -> Any:
        with open_uow(self.db) as uow:
            return fn(uow, **f)

    def raise_(self, subject: str, phase: str = "ready", **f: Any) -> Any:
        base = dict(
            severity="blocking", category="materials", owner="user:user", due_at="2026-12-01"
        )
        return self.run(
            f.pop("who", "user"), "RaiseConstraint", subject=subject, phase=phase, **{**base, **f}
        )

    def row(self, cid: str) -> dict[str, Any]:
        return self.rows("SELECT * FROM cur_core_constraint WHERE id = :i", i=cid)[0]

    def modraise(self, subject: str, source: str, **f: Any) -> Any:
        d = dict(
            phase="ready",
            severity="advisory",
            category="other",
            check_name=None,
            facts_hash=None,
            by_module="awp",
        )
        return self.mod(raise_constraint, subject_id=subject, source=source, **{**d, **f})

    def move(self, record: str, transition: str) -> None:
        cmd = TransitionWorkflow(
            actor="user:user",
            source="test",
            scope=SCOPE,
            stream_id=record,
            expected_version=self.version(record),
            transition=transition,
        )
        with open_uow(self.db) as uow:
            handle_transition_workflow(uow, cmd, by_module=True)

    def read(self, fn: Any, who: str, *a: Any, **k: Any) -> Any:
        with open_uow(self.db, readonly=True) as uow:
            return fn(uow.conn(), *a, viewer=VIEWERS[who], **k)


def build(db: Path) -> tuple[C2, dict[str, str]]:
    w = C2(as_target(str(db)))
    create_schema(w.db)
    w.people()
    w.editions()
    for name, roles in (("user", ("user",)), ("controller", ("document_controller",))):
        w.person(name, roles)
    w.person("viewer", ("user",))
    with open_uow(w.db) as uow:
        acct = (
            uow.conn()
            .execute(text("SELECT account_id FROM cur_account WHERE username='viewer'"))
            .scalar_one()
        )
        grant_module_role(
            uow,
            GrantModuleRole(
                actor="user:ada",
                source="test",
                account_id=acct,
                project=SCOPE,
                module="*",
                role="viewer",
                reason="test",
            ),
        )
    return w, w.documents(db.parent / "objects", *s2.ISO)


def iwp_in_check(w: C2) -> str:
    i = str(w.call("user", "CreateIwp", discipline="PIP", title="T").stream_id)
    w.call("user", "AddIwpScope", iwp=i, items=w.items(["10.0"] * 8))
    w.call("user", "StartIwpDevelopment", iwp=i)
    w.call("user", "SendIwpToConstraintCheck", iwp=i)
    return i


def checks(w: C2, docs: dict[str, str]) -> None:
    i = iwp_in_check(w)
    m = w.raise_(
        i, effective_at="2020-01-01", target_ref_type="purchase_order", target_ref_text="PO-1"
    )
    k1 = w.row(m.stream_id)
    ok(
        "manual raise numbers, due_at as given",
        m.key == "P123-CON-0001" and k1["due_at"] == "2026-12-01",
    )
    ok("envelope effective_at is capture time", all(e.effective_at.year >= 2026 for e in m.events))
    for name, f in (
        ("RaiseConstraint", dict(subject=i, phase="ready", severity="advisory", category="other")),
        ("AssignConstraint", dict(constraint=m.stream_id, owner="user:user")),
        ("ClearConstraint", dict(constraint=m.stream_id, reason="r")),
        ("WithdrawConstraint", dict(constraint=m.stream_id, reason="r")),
    ):
        refuses(ForbiddenError, lambda n=name, g=f: w.run("viewer", n, **g))
    ok("viewer refused every command")
    for src in ("check", "rule", "feed_hold", "thread_hold"):
        refuses(
            ConstraintSourceError, lambda s=src: w.raise_(i, severity="advisory", source_kind=s)
        )
    ok("user refused the four module sources")
    outs = [
        w.modraise(i, s, **({"check_name": "c1", "facts_hash": H1} if s == "check" else {})).action
        for s in ("check", "rule", "feed_hold", "thread_hold")
    ]
    ok(
        "five sources, module raise",
        outs == ["raised"] * 4 and w.scalar("SELECT COUNT(*) FROM cur_core_constraint") == 5,
    )
    refuses(PhaseNotGatedError, lambda: w.raise_(i, "pour"))
    w.raise_(i, "pour", severity="advisory")
    ok("phase_not_gated (blocking) and advisory anywhere")
    again = w.modraise(i, "check", check_name="c1", facts_hash=H2)
    ok("exists for the same subject, phase and check", again.action == "exists")
    chk = w.mod(
        lambda u: raise_constraint(
            u,
            subject_id=i,
            phase="start",
            severity="blocking",
            category="materials",
            source="check",
            check_name="c2",
            facts_hash=H1,
            by_module="awp",
        )
    )
    w.run("user", "ClearConstraint", constraint=chk.constraint_id, reason="seen")
    ok("person clear keeps suppress_hash", w.row(chk.constraint_id)["suppress_hash"] == H1)
    sup = w.modraise(i, "check", phase="start", check_name="c2", facts_hash=H1)
    new = w.modraise(i, "check", phase="start", check_name="c2", facts_hash=H3)
    ok(
        "suppressed for an equal hash, raised for a new one",
        (sup.action, new.action) == ("suppressed", "raised"),
    )
    w.mod(clear_constraint, constraint_id=new.constraint_id, reason="ok", by_module="awp")
    ok("module clear drops the hash", w.row(new.constraint_id)["suppress_hash"] is None)
    refuses(
        ConstraintSourceError,
        lambda: w.mod(clear_constraint, constraint_id=m.stream_id, reason="x", by_module="awp"),
    )
    ok("module cannot clear a manual constraint")
    target = w.run(
        "user",
        "RaiseConstraint",
        subject=i,
        phase="ready",
        severity="advisory",
        category="rfi",
        owner="user:user",
        target=docs[s2.ISO[0]],
    )
    ok(
        "targets link",
        w.scalar(
            "SELECT COUNT(*) FROM cur_links WHERE relation='targets' AND from_id=:c AND to_id=:d",
            c=target.stream_id,
            d=docs[s2.ISO[0]],
        )
        == 1,
    )
    ok(
        "blocks link",
        w.scalar(
            "SELECT COUNT(*) FROM cur_links WHERE relation='blocks' AND from_id=:c AND to_id=:i",
            c=m.stream_id,
            i=i,
        )
        == 1,
    )
    refuses(
        ConstraintRuleError,
        lambda: w.run(
            "user", "ClearConstraint", constraint=m.stream_id, reason="r", cleared_at="2019-01-01"
        ),
    )
    ok("cleared_at before effective_at refused")
    w.run(
        "user",
        "ClearConstraint",
        constraint=m.stream_id,
        reason="r",
        resolved_by=docs[s2.ISO[1]],
        cleared_at="2026-01-01",
    )
    ok(
        "resolves link and cleared_at stored",
        w.scalar(
            "SELECT COUNT(*) FROM cur_links WHERE relation='resolves' AND to_id=:c", c=m.stream_id
        )
        == 1
        and w.row(m.stream_id)["cleared_at"] == "2026-01-01",
    )
    refuses(
        ConstraintStateError,
        lambda: w.run("user", "WithdrawConstraint", constraint=m.stream_id, reason="x"),
    )
    ok("a cleared constraint takes no withdraw")
    guard_checks(w, i)
    walk(w, i, docs)
    tables = ("cur_core_constraint", "cur_core_record", "cur_links")
    before = [w.rows(f"SELECT * FROM {t} ORDER BY 1") for t in tables]
    rebuild_projections(w.db)
    ok(
        "rebuild equals incremental",
        before == [w.rows(f"SELECT * FROM {t} ORDER BY 1") for t in tables],
    )


def guard_checks(w: C2, _used: str) -> None:
    i = iwp_in_check(w)
    block = w.raise_(i, description="Spool secret text")
    got = refuses(GuardFailedError, lambda: w.move(i, "ready"))
    msg = str(got)
    ok(
        "guard blocks ready; message has keys only",
        block.key in msg and "secret" not in msg and "user:user" not in msg,
    )
    ok(
        "open_blocking is keys only",
        w.mod(lambda u: open_blocking(u.conn(), i, "ready")) == [block.key],
    )
    w.run("user", "ClearConstraint", constraint=block.stream_id, reason="done")
    adv = w.raise_(i, severity="advisory")
    w.move(i, "ready")
    ok("guard passes after clear and with an advisory one", w.state(i) == "Ready" and bool(adv.key))
    j = iwp_in_check(w)
    w.run("user", "WithdrawConstraint", constraint=w.raise_(j).stream_id, reason="wrong")
    w.move(j, "ready")
    ok("guard passes after withdraw", w.state(j) == "Ready")
    cwp = w.seed()["Rack 12 piping"]
    held = w.raise_(cwp, "start_execution")
    refuses(GuardFailedError, lambda: w.call("uma", "StartCwpExecution", cwp=cwp))
    w.run("user", "ClearConstraint", constraint=held.stream_id, reason="ok")
    w.call("uma", "StartCwpExecution", cwp=cwp)
    ok("CWP start_execution blocked then passes", w.state(cwp) == "Executing")


def walk(w: C2, i: str, docs: dict[str, str]) -> None:
    secret = hidden_record(w)
    made = w.raise_(secret, severity="advisory", who="controller", owner="user:controller")
    seen = {}
    for who in VIEWERS:
        seen[who] = (
            len(w.read(queries.list_constraints, who, SCOPE, subject_id=secret)),
            w.read(queries.count_constraints, who, SCOPE, subject_id=secret),
            w.read(queries.get_constraint, who, made.stream_id) is not None,
        )
    ok(
        "five readers: restricted subject's constraint absent below the class",
        seen
        == {
            "default": (0, 0, False),
            "user": (0, 0, False),
            "agent": (0, 0, False),
            "controller": (1, 1, True),
            "admin": (1, 1, True),
        },
    )
    refuses(RecordNotFoundError, lambda: w.raise_(secret, severity="advisory", owner="user:user"))
    refuses(
        RecordNotFoundError,
        lambda: w.run("user", "ClearConstraint", constraint=made.stream_id, reason="r"),
    )
    ok("hidden subject answers as an unknown id on commands")
    tgt = w.raise_(i, severity="advisory", who="controller", owner="user:controller", target=secret)
    twin = w.raise_(i, severity="advisory", who="controller", owner="user:controller")
    a, b = (w.read(queries.get_constraint, "user", x.stream_id) for x in (tgt, twin))
    strip = lambda v: {k: x for k, x in asdict(v).items() if k not in ("id", "key")}  # noqa: E731
    ok(
        "hidden target: no target, identical to the no-target twin",
        strip(a) == strip(b) and a.target_id is None,
    )
    c = w.read(queries.get_constraint, "controller", tgt.stream_id)
    ok(
        "controller sees the target",
        c is not None and c.target_id == secret and c.target_kind == "record",
    )
    ok(
        "history absent below the class",
        not w.read(
            queries.constraint_history,
            "user",
            w.mod(lambda u: u.ledger.read_stream(made.stream_id)),
        ),
    )


def seed(w: C2, docs: dict[str, str]) -> None:
    """The S2 seed plus 3 constraints (open manual, Assigned, Cleared) by core commands."""
    s2.seed(w, docs)
    ids = [r["id"] for r in w.rows("SELECT id FROM cur_awp_iwp ORDER BY id")]
    w.raise_(ids[0], description="Spools late")
    two = w.raise_(ids[1], category="permit", description="Hot work permit")
    w.run("user", "AssignConstraint", constraint=two.stream_id, owner="user:uma")
    three = w.raise_(
        ids[2], category="engineering", description="Drawing open", effective_at="2026-10-01"
    )
    w.run(
        "user",
        "ClearConstraint",
        constraint=three.stream_id,
        reason="Issued",
        cleared_at="2026-10-20",
    )
    print("PASS seed: 3 constraints (open, Assigned, Cleared)")
