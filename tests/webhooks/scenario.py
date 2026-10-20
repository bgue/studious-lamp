"""One scenario that produces every catalog event type and delivers it (shared by the contract
and parity tests)."""

from __future__ import annotations

import json
from typing import Any

from tl_core.services.commands import VoidRecord
from tl_core.services.records import handle_void_record
from tl_core.threads.contract import THREAD_EVENT_TYPES
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


#: Record type, the event that defines it, and the events that follow on the same stream (ADR-0010).
MODULE_STREAMS = (
    ("engineering.CodeList", "Standard.Defined", ("Standard.Closed",)),
    ("engineering.CodeValue", "CodeValue.Defined", ("CodeValue.Closed",)),
    ("engineering.TagClass", "TagClass.Defined", ("TagClass.Revised", "TagClass.Closed")),
    ("engineering.Tag", "Tag.Defined", ("Tag.Reclassified", "Tag.Superseded")),
    (
        "documents.Document",
        "Document.Defined",
        ("Document.Updated", "Document.CurrentRevisionChanged", "Document.Superseded"),
    ),
    ("documents.Revision", "Revision.Defined", ("Revision.Issued", "Revision.Superseded")),
    ("documents.Rendition", "Rendition.Defined", ("Rendition.Superseded",)),
    (
        "documents.Transmittal",
        "Transmittal.Defined",
        ("Transmittal.Issued", "Transmittal.ResponseRecorded"),
    ),
    (
        "documents.ReviewCycle",
        "ReviewCycle.Defined",
        ("ReviewCycle.OutcomeRecorded", "ReviewCycle.Closed"),
    ),
    ("documents.DocumentSchema", "DocumentSchema.Defined", ("DocumentSchema.Retired",)),
    (
        "documents.DerivedDocument",
        "DerivedDocument.Defined",
        (
            "DerivedDocument.ContentRecorded",
            "DerivedDocument.Validated",
            "DerivedDocument.Published",
            "DerivedDocument.PublicationCompensated",
        ),
    ),
    (
        "documents.ProcessingJob",
        "ProcessingJob.Defined",
        (
            "ProcessingJob.Started",
            "ProcessingJob.Failed",
            "ProcessingJob.Cancelled",
            "ProcessingJob.Succeeded",
        ),
    ),
    (
        "correspondence.Correspondence",
        "Correspondence.Defined",
        (
            "Correspondence.Updated",
            "Correspondence.Triaged",
            "Correspondence.Reclassified",
            "Correspondence.ThreadAssigned",
            "Correspondence.Issued",
            "Correspondence.Responded",
            "Correspondence.Superseded",
            "Correspondence.ConfidentialityChanged",
            "Correspondence.ClearanceGranted",
            "Correspondence.ClearanceWithdrawn",
        ),
    ),
    (
        "correspondence.CorrespondenceThread",
        "CorrespondenceThread.Defined",
        ("CorrespondenceThread.ItemAdded", "CorrespondenceThread.StateChanged"),
    ),
    (
        "correspondence.ResponseClock",
        "ResponseClock.Started",
        (
            "ResponseClock.Paused",
            "ResponseClock.Resumed",
            "ResponseClock.Restarted",
            "ResponseClock.Met",
            "ResponseClock.Cancelled",
            "ResponseClock.Warned",
            "ResponseClock.Expired",
        ),
    ),
    ("correspondence.ContractClause", "ContractClause.Defined", ("ContractClause.Retired",)),
    (
        "correspondence.Party",
        "Party.Defined",
        ("Party.ContactAdded", "Party.ContactEnded", "Party.Retired"),
    ),
    (
        "cost.CostCode",
        "CostCode.Defined",
        ("CostCode.Revised", "CostCode.MeasuresRecorded"),
    ),
    ("cost.CostSnapshot", "CostSnapshot.Defined", ()),
    (
        "schedule.Schedule",
        "Schedule.Defined",
        ("Schedule.SnapshotPublished", "Schedule.OrphansChecked"),
    ),
    (
        "schedule.ScheduleSnapshot",
        "ScheduleSnapshot.Defined",
        (
            "ScheduleSnapshot.Queued",
            "ScheduleSnapshot.BuildStarted",
            "ScheduleSnapshot.BuildFailed",
            "ScheduleSnapshot.Built",
            "ScheduleSnapshot.Rejected",
            "ScheduleSnapshot.MadeCurrent",
        ),
    ),
    ("schedule.ActivityRef", "ActivityRef.Defined", ("ActivityRef.PresenceChanged",)),
)


#: A child record names its parent in its first event; the sample id is nobody's, and a record whose
#: parent cannot be found is hidden from everyone (ADR-0016). So the scenario points each child at
#: the stream it made for the parent: record type, the field that names the parent, the parent type.
PARENTS = {
    "documents.Revision": ("document_id", "documents.Document"),
    "documents.Rendition": ("document_id", "documents.Document"),
    "documents.ReviewCycle": ("document_id", "documents.Document"),
    "documents.DerivedDocument": ("source_document_id", "documents.Document"),
    "documents.ProcessingJob": ("derived_id", "documents.DerivedDocument"),
    "correspondence.CorrespondenceThread": ("governing_item_id", "correspondence.Correspondence"),
    "correspondence.ResponseClock": ("item_id", "correspondence.Correspondence"),
}
#: Events whose sample would change the class of the record to one the subscription owner may not
#: read; the scenario keeps the record internal so that every event of it is delivered.
KEEP_INTERNAL = {
    "Correspondence.ConfidentialityChanged": {"from_class": "internal", "to_class": "internal"}
}


def stream_of(index: int) -> str:
    return (
        f"01J9Z6Q4W3X2Y1V0T9S8R7Q6M{index}"
        if index < 10
        else f"01J9Z6Q4W3X2Y1V0T9S8R7Q6N{index - 10}"
    )


def append_module_events(world: World) -> None:
    """One stream per module record type: the envelope event, then the module's own events."""
    streams = {
        record_type: stream_of(index)
        for index, (record_type, _, _) in enumerate(MODULE_STREAMS, start=1)
    }
    for index, (record_type, defined, followers) in enumerate(MODULE_STREAMS, start=1):
        stream = stream_of(index)
        created = {
            "record_type": record_type,
            "key": f"MOD-{index}",
            "title": record_type,
            "description": None,
            "psets": {},
        }
        world.append("Record.Created", created, stream_id=stream, stream_type=record_type)
        for kind in (defined, *followers):
            override: dict[str, Any] = dict(KEEP_INTERNAL.get(kind, {}))
            if kind == defined and record_type in PARENTS:
                field, parent = PARENTS[record_type]
                override[field] = streams[parent]
            world.append(
                kind, payload_of(kind, **override), stream_id=stream, stream_type=record_type
            )


def append_integration_events(world: World) -> None:
    """The events of the integration layer that webhooks deliver (P1-I7 WS-A, ADR-0017).

    The configuration events (apps, definitions, rules, endpoints, enrichers) and the inbound
    bookkeeping are in the catalog but never delivered, so the scenario does not make them.
    """
    first, second = "01J9Z6Q4W3X2Y1V0T9S8R7Q6AA", "01J9Z6Q4W3X2Y1V0T9S8R7Q6AB"
    for stream, kinds in (
        (first, ("Action.Requested", "Action.Running", "Action.Completed")),
        (second, ("Action.Requested", "Action.Failed")),
    ):
        for kind in kinds:
            world.append(
                kind,
                payload_of(kind, invocation_id=stream),
                stream_id=stream,
                stream_type="core.ActionInvocation",
            )
    value = "01J9Z6Q4W3X2Y1V0T9S8R7Q6AC"
    for kind in ("Enrichment.Proposed", "Enrichment.Accepted"):
        world.append(
            kind,
            payload_of(kind, value_id=value),
            stream_id=value,
            stream_type="core.EnrichmentValue",
        )


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
    for kind, stream in (
        ("Setting.Changed", "setting:project:P1:feed.reactions.enabled"),
        ("Setting.Locked", "setting:company:feed.reactions.enabled"),
    ):
        world.append(kind, payload_of(kind), stream_id=stream, stream_type="core.Setting")
    world.append(
        "Schema.EffectiveChanged",
        payload_of("Schema.EffectiveChanged"),
        stream_id="schema:project:P1",
        stream_type="schema",
    )
    for kind, stream in (
        ("TypeRegistration.Registered", "type:co.acme.LiftPlan@1.0.0"),
        ("TypeRegistration.Deprecated", "type:co.acme.LiftPlan@1.0.0"),
        ("TypeRegistration.Quarantined", "type:co.acme.LiftPlan@1.0.1"),
    ):
        world.append(kind, payload_of(kind), stream_id=stream, stream_type="core.TypeRegistration")
    world.append(
        "Record.BodyStored",
        payload_of("Record.BodyStored", stream_id=a),
        stream_id=a,
    )
    world.append(
        "SchemaPackage.Published",
        payload_of("SchemaPackage.Published"),
        stream_id="schema-package:co.acme.engineering",
        stream_type="schema-package",
    )
    append_module_events(world)
    for kind in THREAD_EVENT_TYPES:  # edits and retractions are written but never delivered
        world.append(
            kind,
            payload_of(kind, record_id=a),
            stream_id=f"thread:{a}",
            stream_type="core.Thread",
        )
    append_integration_events(world)  # P1-I7 WS-A
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
