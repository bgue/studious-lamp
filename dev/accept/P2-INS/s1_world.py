"""The world of S1.py and the activity tests: one IWP that has every kind of activity, a related
record, and a record the viewer may not read (P2-INS-S1)."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "dev/accept/P2-I2"))
import c2_checks as c2  # noqa: E402  # pyright: ignore[reportMissingImports]
from awp_world import SCOPE, hidden_record  # noqa: E402  # pyright: ignore[reportMissingImports]
from tl_adapters.db import as_target, open_uow  # noqa: E402
from tl_core import confidentiality as cf  # noqa: E402
from tl_core import settings  # noqa: E402
from tl_core.ledger import NewEvent  # noqa: E402
from tl_core.services import proposals  # noqa: E402
from tl_core.services.commands import CreateRecord  # noqa: E402
from tl_core.services.links import AddLink, handle_add_link  # noqa: E402
from tl_core.services.records import handle_create_record  # noqa: E402
from tl_core.threads.messages import PostThreadMessage, handle_post_thread_message  # noqa: E402
from tl_core.util import new_ulid  # noqa: E402
from tl_mod_awp.readiness.engine import evaluate_now  # noqa: E402

AGENT = "agent:triage"


@dataclass
class World:
    w: Any  # the C2 world (a SQLite or Postgres target and its helpers)
    iwp: str
    ids: dict[str, str]


def make_record(w: Any, key: str, title: str) -> str:
    with open_uow(w.db) as uow:
        return handle_create_record(
            uow,
            CreateRecord(
                actor="user:user",
                source="test",
                scope=SCOPE,
                record_type="core.Record",
                title=title,
                key=key,
                psets={},
            ),  # fmt: skip
        ).stream_id


def link(w: Any, from_id: str, to_id: str, relation: str) -> None:
    with cf.system_view(), open_uow(w.db) as uow:
        handle_add_link(
            uow,
            AddLink(
                actor="user:user",
                source="test",
                scope=SCOPE,
                from_id=from_id,
                to_id=to_id,
                relation=relation,
            ),  # fmt: skip
        )


def build(root: Path, target: Any = None) -> World:
    """The world on a new SQLite file under ``root``, or on ``target`` (schema in place)."""
    if target is None:
        w, _ = c2.build(root / "s1.db")
    else:
        w = c2.C2(as_target(str(target)))
        w.people()
        w.editions()
        w.person("user", ("user",))
        w.person("controller", ("document_controller",))
        w.documents(root / "objects", *c2.s2.ISO)
    iwp = c2.iwp_in_check(w)
    ids: dict[str, str] = {}
    with open_uow(w.db) as uow:
        for key, value in (
            ("threads.enabled", True),
            ("threads.enabled_types", ["awp.IWP", "core.Record"]),
        ):
            settings.set_setting(
                uow, key=key, layer="company", value=value, actor="user:a", source="t", reason="t"
            )
    with open_uow(w.db) as uow:
        evaluate_now(uow, iwp, date(2026, 11, 2))
    ids["from"], ids["to"] = (
        make_record(w, "S1-FROM", "points at it"),
        make_record(w, "S1-TO", "it"),
    )
    ids["prop"] = make_record(w, "S1-PROP", "proposed link target")
    link(w, ids["from"], iwp, "references")
    link(w, iwp, ids["to"], "references")
    with open_uow(w.db) as uow:
        handle_post_thread_message(
            uow,
            PostThreadMessage(actor="user:user", source="t", scope=SCOPE, record_id=iwp, body="hi"),
        )
    ids["constraint"] = str(w.raise_(iwp).stream_id)
    w.run("user", "ClearConstraint", constraint=ids["constraint"], reason="seen")
    ids["far"] = c2.iwp_in_check(w)  # a linked record that moved: the related rows
    link(w, ids["far"], iwp, "blocks")
    return World(w, iwp, ids)


def add_hidden(world: World) -> str:
    """A restricted record that blocks the IWP and has an event a related row could carry."""
    from tl_mod_correspondence.testing import CorrWorld  # noqa: PLC0415

    hidden = hidden_record(world.w)
    link(world.w, hidden, world.iwp, "blocks")
    link(world.w, world.iwp, hidden, "targets")  # and the other way: both ends are tested
    CorrWorld(world.w.db, Path("/nonexistent")).forge_item_event(
        hidden, "Correspondence.Responded", {"responded_on": "2026-10-20"}
    )
    world.ids["hidden"] = hidden
    return hidden


def upload(world: World) -> str:
    """A ``File.Uploaded`` event for the IWP (forged: the IWP has no file slot to upload to)."""
    file_id = new_ulid()
    payload = {
        "file_id": file_id, "record_id": world.iwp, "slot": "plan", "revision": 1,
        "sha256": "a" * 64, "size": 7, "content_type": "text/plain", "filename": "a.txt",
        "status": "quarantined", "deduplicated": False,
    }  # fmt: skip
    with open_uow(world.w.db) as uow:
        uow.append(
            stream_id=file_id, stream_type="core.File", scope=SCOPE, expected_version=0,
            events=[NewEvent(event_type="File.Uploaded", payload=payload)],
            actor="user:user", source="test", correlation_id=new_ulid(),
        )  # fmt: skip
    return file_id


def propose_link(world: World, *, accept: bool) -> str:
    """An agent proposes a link from the IWP; a person accepts or rejects it."""
    with open_uow(world.w.db) as uow:
        cmd = AddLink(
            actor=AGENT, source="mcp:triage", scope=SCOPE, from_id=world.iwp,
            to_id=world.ids["prop"], relation="references",
        )  # fmt: skip
        view = proposals.propose(uow, tool="link_records", agent=AGENT, command=cmd, summary="s1")
    with open_uow(world.w.db) as uow:
        if accept:
            proposals.accept_proposal(uow, proposal_id=view.proposal_id, by="user:user")
        else:
            proposals.reject_proposal(
                uow, proposal_id=view.proposal_id, by="user:user", reason="no"
            )
    return view.proposal_id
