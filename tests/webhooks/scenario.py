"""One scenario that produces every catalog event type and delivers it (shared by the contract
and parity tests)."""

from __future__ import annotations

import json
from typing import Any

from tl_core.services.commands import VoidRecord
from tl_core.services.records import handle_void_record
from tl_core.webhooks.subscriptions import (
    DisableWebhookSubscription,
    EnableWebhookSubscription,
    RotateWebhookSecret,
    UpdateWebhookSubscription,
    disable_subscription,
    enable_subscription,
    rotate_secret,
    update_subscription,
)
from tl_schema import catalog
from world import SCOPE, World

COMMON: dict[str, Any] = {"actor": "user:alice", "source": "test", "scope": SCOPE}
LINK = ("01J9Z6Q4W3X2Y1V0T9S8R7Q6L1", "01J9Z6Q4W3X2Y1V0T9S8R7Q6L2", "01J9Z6Q4W3X2Y1V0T9S8R7Q6L3")
FILE = "01J9Z6Q4W3X2Y1V0T9S8R7Q6F1"
POST = "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5"
PROPOSALS = {
    "Proposal.Accepted": "01J9Z6Q4W3X2Y1V0T9S8R7Q6Q1",
    "Proposal.Rejected": "01J9Z6Q4W3X2Y1V0T9S8R7Q6Q2",
    "Proposal.Failed": "01J9Z6Q4W3X2Y1V0T9S8R7Q6Q3",
}


def payload_of(event_type: str, **override: Any) -> dict[str, Any]:
    return {**catalog.sample(event_type)["payload"], **override}


def run_scenario(world: World) -> dict[str, list[dict[str, Any]]]:
    """Subscribe in all three modes, produce every catalog event type, deliver everything.

    Returns the delivered bodies per mode.
    """
    modes = {mode: world.subscribe(mode=mode, name=mode) for mode in ("thin", "delta", "full")}
    a, b = world.record("P1-A", title="Gate valve"), world.record("P1-B")
    world.retitle(a, "Gate valve 47", version=1)
    world.append("Record.Corrected", payload_of("Record.Corrected"), stream_id=b, version=1)
    world.append("Pset.ValuesSet", payload_of("Pset.ValuesSet"), stream_id=a)
    world.append("Workflow.Transitioned", payload_of("Workflow.Transitioned"), stream_id=a)
    world.append(
        "Numbering.Allocated",
        payload_of("Numbering.Allocated", record_id=a),
        stream_id="numbering:project:P1:rec:P1-REC-",
        stream_type="numbering.Counter",
    )
    for kind, payload in (
        ("File.Uploaded", payload_of("File.Uploaded", file_id=FILE, record_id=a)),
        ("File.Processed", payload_of("File.Processed", file_id=FILE)),
        ("File.Rejected", payload_of("File.Rejected", file_id=FILE)),
    ):
        world.append(kind, payload, stream_id=FILE, stream_type="core.File")
    chain = (
        (LINK[0], "Link.Suggested"),
        (LINK[0], "Link.Accepted"),
        (LINK[0], "Link.Verified"),
        (LINK[0], "Link.Repinned"),
        (LINK[0], "Link.Flagged"),
        (LINK[0], "Link.Retracted"),
        (LINK[1], "Link.Added"),
        (LINK[2], "Link.Suggested"),
        (LINK[2], "Link.Declined"),
    )
    for link_id, kind in chain:
        payload = payload_of(kind)
        if "from_ref" in payload:
            payload.update(from_ref=a, to_ref=b)
        world.append(kind, payload, stream_id=link_id, stream_type="core.Link")
    for kind in ("Feed.Posted", "Feed.Edited", "Feed.Reacted", "Feed.Retracted"):
        world.append(
            kind, payload_of(kind, post_id=POST), stream_id=POST, stream_type="core.ActivityPost"
        )
    for decision, proposal_id in PROPOSALS.items():  # each proposal: opened, then decided once
        for kind in ("Proposal.Created", decision):
            world.append(
                kind,
                payload_of(kind, proposal_id=proposal_id),
                stream_id=proposal_id,
                stream_type="core.Proposal",
            )
    world.append(
        "Schema.EffectiveChanged",
        payload_of("Schema.EffectiveChanged"),
        stream_id="schema:project:P1",
        stream_type="schema",
    )
    world.append(
        "SchemaPackage.Published",
        payload_of("SchemaPackage.Published"),
        stream_id="schema-package:co.acme.engineering",
        stream_type="schema-package",
    )
    sid = modes["delta"].subscription_id
    with world.factory() as uow:
        update_subscription(
            uow,
            UpdateWebhookSubscription(subscription_id=sid, changes={"name": "renamed"}, **COMMON),
        )
        rotate_secret(uow, RotateWebhookSecret(subscription_id=sid, **COMMON), clock=world.clock)
        disable_subscription(uow, DisableWebhookSubscription(subscription_id=sid, **COMMON))
        enable_subscription(uow, EnableWebhookSubscription(subscription_id=sid, **COMMON))
    with world.factory() as uow:
        handle_void_record(
            uow,
            VoidRecord(stream_id=b, expected_version=2, reason="duplicate", **COMMON),
        )
    world.dispatcher().run_until_idle()
    engine = world.engine()
    for _ in range(200):
        if engine.run_cycle(limit=50).claimed == 0:
            break
    by_mode: dict[str, list[dict[str, Any]]] = {mode: [] for mode in modes}
    hosts = {mode: "hook.test" for mode in modes}
    for request in world.transport.sent:
        body = json.loads(request.body)
        by_mode[mode_of(body)].append(body)
    assert hosts
    return by_mode


def mode_of(body: dict[str, Any]) -> str:
    data = body["data"]
    if "record" in data:
        return "full"
    return "delta" if "detail" in data else "thin"
