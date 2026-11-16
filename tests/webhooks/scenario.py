"""One scenario that produces every catalog event type and delivers it (shared by the contract
and parity tests)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from tl_adapters.queue import job_queue_for
from tl_core.auth import accounts
from tl_core.auth.module_grants import GrantModuleRole, grant_module_role
from tl_core.auth.queries import find_account
from tl_core.jobs import JobRunner
from tl_core.services.agent_stop import (
    ResumeAgent,
    StopAgent,
    handle_resume_agent,
    handle_stop_agent,
)
from tl_core.services.commands import CreateRecord, VoidRecord
from tl_core.services.proposals import submit
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
from tl_mod_requisitions.commands import ApproveRequisition, RaiseRequisition
from tl_mod_requisitions.module import REQUISITIONS_COMMANDS
from tl_mod_scaffold import commands as sc
from tl_mod_scaffold.inspections_due import InspectionsDueKind
from tl_mod_scaffold.inspections_due import request as request_inspections_due
from tl_mod_scaffold.module import SCAFFOLD_COMMANDS
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
    # An item of the Technical or Commercial domain is a row of the item table too, so its stream
    # begins with the item's own Defined event (without it the record has no class and is hidden).
    (
        "correspondence.TechnicalItem",
        "Correspondence.Defined",
        (
            "Technical.Defined",
            "Technical.Updated",
            "Technical.Answered",
            "Technical.Reviewed",
            "Technical.Reissued",
        ),
    ),
    (
        "correspondence.CommercialItem",
        "Correspondence.Defined",
        ("Commercial.Defined", "Commercial.Updated", "Commercial.Assessed"),
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
    (
        "schemareg.SchemaPackage",
        "SchemaPackage.Drafted",
        (
            "SchemaPackage.Revised",
            "SchemaPackage.Analysed",
            "SchemaPackage.Submitted",
            "SchemaPackage.ChangesRequested",
            "SchemaPackage.Approved",
            "SchemaPackage.Deprecated",
            "SchemaPackage.Retired",
        ),
    ),
    ("schemareg.Adoption", "Adoption.Pinned", ()),
    (
        "legacy.LoadRun",
        "LoadRun.Opened",
        (
            "LoadRun.Extracted",
            "LoadRun.Profiled",
            "LoadRun.Bronzed",
            "LoadRun.Planned",
            "LoadRun.Loaded",
            "LoadRun.Reconciled",
            "LoadRun.Compensated",
            "LoadRun.Failed",
            "LoadRun.Voided",
        ),
    ),
    ("schemareg.Waiver", "Waiver.Requested", ("Waiver.Approved", "Waiver.Revoked")),
    # awp (P2-I1): WBS, path of construction, CWAs, CWPs, external and package refs
    (
        "awp.WBSNode",
        "WBSNode.Defined",
        (
            "WBSNode.Revised",
            "WBSNode.Retired",
            "WBSNode.Reinstated",
            "WBSNode.CostCodesMapped",
            "WBSNode.BudgetRolledUp",
        ),
    ),
    (
        "awp.PathOfConstruction",
        "PathOfConstruction.Defined",
        ("PathOfConstruction.Resequenced",),
    ),
    ("awp.CWA", "CWA.Defined", ("CWA.Revised", "CWA.Retired")),
    (
        "awp.CWP",
        "CWP.Defined",
        (
            "CWP.Revised",
            "CWP.AllocatedToWbs",
            "CWP.Released",
            "Cwp.PartyAssigned",
            "Cwp.SubcontractProgressRecorded",
        ),
    ),
    ("awp.EWPRef", "EWPRef.Defined", ("EWPRef.Updated",)),
    ("awp.PWPRef", "PWPRef.Defined", ("PWPRef.Updated",)),
    # awp part 2 (P2-I2): IWPs, scope items, constraints
    (
        "awp.IWP",
        "IWP.Created",
        (
            "IWP.Revised",
            "IWP.ScopeAdded",
            "IWP.ScopeRemoved",
            "IWP.DocumentPinned",
            "IWP.ReadinessEvaluated",
            "IWP.Ready",
            "IWP.SignedOff",
            "IWP.Issued",
            "IWP.Started",
            "IWP.ProgressRecorded",
            "IWP.FieldCompleted",
            "IWP.Held",
            "IWP.HoldReleased",
            "IWP.Split",
        ),
    ),
    ("awp.ScopeItem", "ScopeItem.Created", ("ScopeItem.Revised",)),
    (
        "core.Constraint",
        "Constraint.Raised",
        ("Constraint.Assigned", "Constraint.Cleared", "Constraint.Withdrawn"),
    ),
    # materials (P2-I3): library, location tree, PO line mirror, receipts, lots and take-offs
    (
        "materials.ItemMaster",
        "ItemMaster.Defined",
        ("ItemMaster.Revised", "ItemMaster.Retired"),
    ),
    ("materials.ProjectItem", "ProjectItem.Defined", ()),
    (
        "materials.InventoryLocation",
        "InventoryLocation.Defined",
        ("InventoryLocation.Revised", "InventoryLocation.Retired"),
    ),
    ("materials.POLineRef", "POLineRef.Defined", ("POLineRef.Updated",)),
    (
        "materials.Receipt",
        "Receipt.Defined",
        ("Receipt.Revised", "Receipt.Inspected", "Receipt.Accepted", "Receipt.Rejected"),
    ),
    ("materials.StockLot", "StockLot.Defined", ("StockLot.Moved",)),
    ("materials.MTO", "MTO.Defined", ()),
    ("materials.MTOLine", "MTOLine.Defined", ("MTOLine.Assigned",)),
    # quality (P2-PUNCH): the punch item, raised, then every follow-on in a valid order
    (
        "quality.PunchItem",
        "PunchItem.Raised",
        (
            "PunchItem.Edited",
            "PunchItem.Cleared",
            "PunchItem.Verified",
            "PunchItem.Reopened",
            "PunchItem.Voided",
        ),
    ),
    # awp part 3 (P2-I5): weekly plans and closeout
    (
        "awp.WeeklyPlan",
        "WeeklyPlan.Opened",
        ("WeeklyPlan.IwpCommitted", "WeeklyPlan.OutcomeRecorded", "WeeklyPlan.Closed"),
    ),
    ("awp.IWPCloseout", "IWPCloseout.Recorded", ()),
    # requisitions (P2-I4A): the labour kind stands for the four kinds, which share the events
    (
        "requisitions.LaborRequisition",
        "Requisition.Raised",
        (
            "Requisition.Revised",
            "Requisition.Approved",
            "Requisition.Rejected",
            "Requisition.Cancelled",
            "Requisition.Fulfilled",
        ),
    ),
    (
        "requisitions.WorkOrder",
        "WorkOrder.Opened",
        (
            "WorkOrder.Scheduled",
            "WorkOrder.Assigned",
            "WorkOrder.Started",
            "WorkOrder.Completed",
            "WorkOrder.Closed",
        ),
    ),
    # permits (P2-PTW): the permit, its isolations and gas tests
    (
        "permits.Permit",
        "Permit.Requested",
        (
            "Permit.Approved",
            "Permit.Rejected",
            "Permit.Issued",
            "Permit.Revalidated",
            "Permit.Suspended",
            "Permit.Resumed",
            "Permit.HandedBack",
            "Permit.Closed",
            "Permit.Cancelled",
            "Permit.Lapsed",
            "Permit.IsolationLinked",
            "Permit.IsolationUnlinked",
        ),
    ),
    (
        "permits.Isolation",
        "Isolation.Applied",
        ("Isolation.Verified", "Isolation.Removed"),
    ),
    ("permits.GasTest", "GasTest.Recorded", ()),
    # quality (P2-INSP): checklists and inspections
    (
        "quality.Checklist",
        "Checklist.Created",
        ("Checklist.Edited", "Checklist.Published", "Checklist.Retired"),
    ),
    (
        "quality.Inspection",
        "Inspection.Planned",
        (
            "Inspection.Scheduled",
            "Inspection.ResultRecorded",
            "Inspection.Verified",
            "Inspection.Cancelled",
        ),
    ),
    # qr (P2-QR): scan codes
    ("qr.ScanCode", "ScanCode.Issued", ("ScanCode.Revoked",)),
    # forms (P2-FORMS): templates, submissions, intake codes and intake items
    (
        "forms.Template",
        "Template.Created",
        ("Template.Edited", "Template.Published", "Template.Retired"),
    ),
    (
        "forms.Submission",
        "Submission.DraftSaved",
        (
            "Submission.DraftDiscarded",
            "Submission.Submitted",
            "Submission.Accepted",
            "Submission.Returned",
            "Submission.Voided",
        ),
    ),
    ("forms.IntakeCode", "IntakeCode.Issued", ("IntakeCode.Revoked",)),
    (
        "forms.IntakeItem",
        "IntakeItem.Received",
        ("IntakeItem.Accepted", "IntakeItem.Rejected", "IntakeItem.Purged"),
    ),
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


#: The sample of these events names records that do not exist in the scenario, and the module's
#: projector keeps balances, so the scenario sends a receive into a location and a receipt with no
#: PO line (the event is the same one, the catalog's, with the references it needs).
PROJECTABLE = {
    "Receipt.Defined": {"po_line_id": None},
    "StockLot.Moved": {
        "kind": "receive",
        "from_location_id": None,
        "to_location_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P2",
        "cost_code_id": None,
    },
    # the catalog's samples of these two name an id of 27 characters (not a ULID)
    "MTOLine.Defined": {"mto_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PA"},
    "MTOLine.Assigned": {"work_package_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PB"},
}


def stream_of(index: int) -> str:
    if index < 10:
        return f"01J9Z6Q4W3X2Y1V0T9S8R7Q6M{index}"
    if index < 20:
        return f"01J9Z6Q4W3X2Y1V0T9S8R7Q6N{index - 10}"
    return f"01J9Z6Q4W3X2Y1V0T9S8R7Q7{index:02d}"


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
            override: dict[str, Any] = {
                **KEEP_INTERNAL.get(kind, {}),
                **PROJECTABLE.get(kind, {}),
            }
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


def stop_and_resume_an_agent(world: World) -> None:
    """Agent.Stopped and Agent.Resumed, through the real commands (P2-X2 S3).

    They sit on the account stream, so no subscriber is sent them (ADR-0009); the contract test
    asserts that. The agent needs an account, a filing grant and one filing; the admin is a
    person."""
    with world.factory() as uow:
        accounts.create_account(
            uow, username="gadmin", display_name="gadmin", kind="person",
            roles=["admin"], password=None, by="svc:test",
        )  # fmt: skip
        accounts.create_account(
            uow, username="bot", display_name="bot", kind="agent",
            roles=["user"], password=None, by="svc:test",
        )  # fmt: skip
        bot = find_account(uow.conn(), username="bot")
        assert bot is not None
        grant_module_role(
            uow,
            GrantModuleRole(
                actor="user:gadmin", source="test", scope="company", account_id=bot.account_id,
                project=SCOPE, module="*", role="user", reason="test",
            ),
        )  # fmt: skip
    submit(
        world.factory, tool="create_record", agent="agent:bot", summary="Create a record",
        command=CreateRecord(
            actor="agent:bot", source="mcp:x", scope=SCOPE, record_type="core.Record",
            title="filed", key="P1-FILED",
        ),
    )  # fmt: skip
    with world.factory() as uow:
        handle_stop_agent(
            uow,
            StopAgent(actor="user:gadmin", source="test", scope="company", agent="agent:bot"),
        )
    with world.factory() as uow:
        handle_resume_agent(
            uow, ResumeAgent(actor="user:gadmin", source="test", scope="company", agent="agent:bot")
        )


def run_a_scaffold_life(world: World) -> None:
    """Every scaffold event type, through the real commands (P2-I4B).

    An approved scaffold request is registered, designed, erected, tagged green, released, inspected
    (conditional), sent to Modify and back, flagged by the inspections-due job, dismantled and
    removed. The commands run as their handlers do, one unit of work each."""
    handlers = {c.model.__name__: c.handler for c in (*SCAFFOLD_COMMANDS, *REQUISITIONS_COMMANDS)}

    def call(model: Any, who: str = "alice", **fields: Any) -> Any:
        cmd = model(actor=f"user:{who}", source="test", scope=SCOPE, **fields)
        with world.factory() as uow:
            return handlers[model.__name__](uow, cmd)

    requisition = {
        "kind": "scaffold", "subject": "Scaffold at unit 4", "purpose": "Access to the valve",
        "elevation": "+12.0", "gridline": "C-4", "load_class": "Light", "duration_days": 14,
    }  # fmt: skip
    raised = call(RaiseRequisition, requisition=requisition)
    with world.factory() as uow:
        version = uow.ledger.stream_version(raised.stream_id)
    call(ApproveRequisition, "bob", requisition=raised.stream_id, expected_version=version)
    made = call(sc.RegisterScaffold, request_id=raised.stream_id, title="Scaffold A")
    scaffold = str(made.stream_id)
    call(sc.DesignScaffold, scaffold=scaffold)
    call(sc.ErectScaffold, scaffold=scaffold)
    call(sc.TagScaffoldGreen, scaffold=scaffold)
    call(sc.ReleaseScaffold, scaffold=scaffold)
    call(sc.InspectScaffold, scaffold=scaffold, result="conditional")
    call(sc.ModifyScaffold, scaffold=scaffold, reason="add a lift")
    call(sc.TagScaffoldGreen, scaffold=scaffold)
    call(sc.ReleaseScaffold, scaffold=scaffold)
    with world.factory() as uow:
        request_inspections_due(uow, "P1", (datetime.now(UTC) + timedelta(days=8)).date())
    with world.factory() as uow:
        queue = job_queue_for(uow.conn())
    JobRunner(world.factory, queue, [InspectionsDueKind()], worker_id="scenario").run_until_idle()
    call(sc.DismantleScaffold, scaffold=scaffold, reason="Done")
    call(sc.RemoveScaffold, scaffold=scaffold)


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
    stop_and_resume_an_agent(world)  # P2-X2 S3
    run_a_scaffold_life(world)  # P2-I4B
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
