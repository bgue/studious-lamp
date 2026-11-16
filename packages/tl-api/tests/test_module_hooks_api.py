"""The API command table and read routers come from the module hooks (P2-X4 S2).

``OLD_COMMANDS`` and ``expected/route_order.txt`` were captured from the tree before the hand lists
went; they pin what the hooks must reproduce, plus the requisitions commands (decision Q2).
"""

from __future__ import annotations

import importlib
import logging
import sys
import types
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import tl_api.commands as commands_module
from fastapi import APIRouter
from harness import Harness
from test_api_requisitions import PROJECT, Rig, load_world, rig  # noqa: F401
from tl_api.app import create_app
from tl_api.tokens import TokenStore, add_token
from tl_core import intent
from tl_core import modules as tl_modules
from tl_core.modules import ModuleSpec, use_modules
from tl_core.services.commands import Command
from tl_mod_requisitions.module import REQUISITIONS_COMMANDS

ORDER_FILE = Path(__file__).parent / "expected" / "route_order.txt"
REQUISITION_NAMES = [
    "RaiseRequisition",
    "EditRequisition",
    "ApproveRequisition",
    "RejectRequisition",
    "CancelRequisition",
    "ScheduleWorkOrder",
    "AssignWorkOrder",
    "StartWorkOrder",
    "CompleteWorkOrder",
    "CloseWorkOrder",
]

# Baseline of ``tl_api.commands.COMMANDS`` before the hook table: sorted
# ``(name, access, module, needs_holds, takes_roles)``.
OLD_COMMANDS = [
    ("AcceptEnrichment", "user", None, False, False),
    ("AcceptLink", "user", None, False, False),
    ("AcceptReceipt", "materials.receipt.decide", "materials", False, False),
    ("AddCodeValue", "company", "engineering", False, False),
    ("AddContact", "controller", "correspondence", False, False),
    ("AddIwpScope", "awp.iwp.edit", "awp", False, False),
    ("AddLink", "user", None, False, False),
    ("AdjustStock", "materials.adjust", "materials", False, False),
    ("AdminFlagLink", "admin", None, False, False),
    ("AdminRetractLink", "admin", None, False, False),
    ("AdoptItem", "materials.item.adopt", "materials", False, False),
    ("AdoptSchemaPackage", "admin", "schemareg", False, False),
    ("AdoptSchemaSet", "controller", "schemareg", False, False),
    ("AllocateCwpToWbs", "awp.cwp.edit", "awp", False, False),
    ("AnalyseSchemaPackage", "user", "schemareg", False, False),
    ("AnswerTechnical", "user", "correspondence", False, False),
    ("ApproveSchemaPackage", "admin", "schemareg", False, False),
    ("ApproveWaiver", "admin", "schemareg", False, False),
    ("AssessCommercial", "controller", "correspondence", False, False),
    ("AssignConstraint", "core.constraint.edit", None, False, False),
    ("AssignMtoLines", "materials.mto.assign", "materials", False, False),
    ("AssignThread", "user", "correspondence", False, False),
    ("AttachRendition", "user", "documents", False, False),
    ("CancelClock", "user", "correspondence", False, False),
    ("CancelInspection", "quality.inspection.cancel", "quality", False, False),
    ("CancelIwp", "awp.void", "awp", False, False),
    ("CancelJob", "user", "documents", False, False),
    ("ChangeSetting", "user", None, False, False),
    ("ClearConstraint", "core.constraint.edit", None, False, False),
    ("ClearPunchItem", "quality.punch.clear", "quality", False, False),
    ("CloseCodeValue", "company", "engineering", False, False),
    ("CloseCommercial", "controller", "correspondence", False, False),
    ("CloseCorrespondence", "user", "correspondence", False, False),
    ("CloseCwp", "awp.cwp.close", "awp", False, False),
    ("CloseReviewCycle", "user", "documents", False, False),
    ("CloseStandard", "admin", "engineering", False, False),
    ("CloseTagClass", "admin", "engineering", False, False),
    ("CloseTechnical", "user", "correspondence", False, False),
    ("CloseTransmittal", "user", "documents", False, False),
    ("CloseWeek", "awp.week.close", "awp", False, False),
    ("CommitIwpToWeek", "awp.week.commit", "awp", False, False),
    ("CompensatePublication", "admin", "documents", False, False),
    ("CompleteCwp", "awp.cwp.edit", "awp", False, False),
    ("CompleteIwpField", "awp.iwp.edit", "awp", False, False),
    ("ConfirmTriage", "user", "correspondence", False, False),
    ("CreateChecklist", "quality.checklist.edit", "quality", False, False),
    ("CreateCwp", "awp.cwp.edit", "awp", False, False),
    ("CreateIwp", "awp.iwp.edit", "awp", False, False),
    ("CreateReceipt", "materials.receive", "materials", False, False),
    ("CreateRecord", "user", None, False, False),
    ("CreateRevision", "user", "documents", False, False),
    ("CreateRule", "admin", None, False, False),
    ("CreateScopeItem", "awp.iwp.edit", "awp", False, False),
    ("CreateTag", "user", "engineering", False, False),
    ("CreateTransmittal", "user", "documents", False, False),
    ("DeclineLink", "user", None, False, False),
    ("DefineClause", "controller", "correspondence", False, False),
    ("DefineCwa", "awp.cwa.edit", "awp", False, False),
    ("DefineItem", "materials.library.edit", "materials", False, False),
    ("DefineLocation", "materials.location.configure", "materials", False, False),
    ("DefinePathOfConstruction", "awp.path.configure", "awp", False, False),
    ("DefineSchedule", "controller", "schedule", False, False),
    ("DefineTagClass", "admin", "engineering", False, False),
    ("DefineWbsNode", "awp.wbs.configure", "awp", False, False),
    ("DeprecateSchemaPackage", "admin", "schemareg", False, False),
    ("DisableRule", "admin", None, False, False),
    ("DraftCorrespondence", "user", "correspondence", False, False),
    ("DraftSchemaPackage", "user", "schemareg", False, False),
    ("EditChecklist", "quality.checklist.edit", "quality", False, False),
    ("EditPost", "user", None, False, False),
    ("EditPunchItem", "quality.punch.edit", "quality", False, False),
    ("EditRecord", "user", None, False, False),
    ("EditThreadMessage", "user", None, False, False),
    ("EnableRule", "admin", None, False, False),
    ("EndContact", "controller", "correspondence", False, False),
    ("EscalateTechnical", "controller", "correspondence", False, False),
    ("FlagLink", "user", None, False, False),
    ("GrantClearance", "controller", "correspondence", False, False),
    ("HoldIwp", "awp.iwp.hold", "awp", False, False),
    ("ImportCostSnapshot", "admin", "cost", False, False),
    ("InspectReceipt", "materials.receive", "materials", False, False),
    ("InstallScopeItem", "awp.progress.record", "awp", False, False),
    ("InvokeAction", "user", None, True, False),
    ("IssueCommercial", "controller", "correspondence", False, False),
    ("IssueCorrespondence", "controller", "correspondence", False, False),
    ("IssueIwp", "awp.iwp.issue", "awp", False, False),
    ("IssueRevision", "controller", "documents", False, False),
    ("IssueScanCode", "qr.issue", "qr", False, False),  # P2-QR S2
    ("IssueStock", "materials.move", "materials", False, False),
    ("IssueTechnical", "controller", "correspondence", False, False),
    ("IssueTransmittal", "controller", "documents", False, False),
    ("LinkActivity", "user", "schedule", False, False),
    ("LinkToDocument", "user", "documents", False, False),
    ("MapWbsToCostCodes", "awp.wbs.configure", "awp", False, False),
    ("MeetClock", "user", "correspondence", False, False),
    ("MergeTags", "user", "engineering", False, False),
    ("MoveCwaInPath", "awp.path.configure", "awp", False, False),
    ("OpenDerivedDocument", "user", "documents", False, False),
    ("OpenReviewCycle", "user", "documents", False, False),
    ("OpenScheduleSnapshot", "user", "schedule", False, False),
    ("OpenWeeklyPlan", "awp.week.plan", "awp", False, False),
    ("OverrideReviewOutcome", "controller", "documents", False, False),
    ("PauseClock", "user", "correspondence", False, False),
    ("PinIwpDocument", "awp.iwp.edit", "awp", False, False),
    ("PlanInspection", "quality.inspection.plan", "quality", False, False),
    ("PostThreadMessage", "user", None, False, False),
    ("PostToFeed", "user", None, False, False),
    ("PublishChecklist", "quality.checklist.publish", "quality", False, False),
    ("PublishDerivedDocuments", "controller", "documents", False, False),
    ("PublishDerivedMto", "materials.mto.publish", "materials", False, False),
    ("PublishDerivedTags", "admin", "documents", False, False),
    ("PublishScheduleSnapshot", "controller", "schedule", False, False),
    ("PublishSchemaPackage", "admin", "schemareg", False, False),
    ("RaiseCommercial", "controller", "correspondence", False, False),
    ("RaiseConstraint", "core.constraint.edit", None, False, False),
    ("RaisePunchItem", "quality.punch.raise", "quality", False, False),
    ("RaiseTechnical", "user", "correspondence", False, False),
    ("ReactToPost", "user", None, False, False),
    ("ReceiveCorrespondence", "user", "correspondence", False, False),
    ("ReclassifyCorrespondence", "user", "correspondence", False, False),
    ("ReclassifyTag", "user", "engineering", False, False),
    ("RecordExternalPackage", "awp.package.edit", "awp", False, False),
    ("RecordInspectionResult", "quality.inspection.record", "quality", False, False),
    ("RecordManualProgress", "awp.progress.record", "awp", False, False),
    ("RecordPoLine", "materials.po.edit", "materials", False, False),
    ("RecordResponse", "user", "correspondence", False, False),
    ("RecordReviewOutcome", "user", "documents", False, False),
    ("RecordReviewOutcomeOnBehalf", "controller", "documents", False, False),
    ("RecordTag", "admin", "engineering", False, False),
    ("RecordTransmittalResponse", "user", "documents", False, False),
    ("RecordWeekOutcome", "awp.week.commit", "awp", False, False),
    ("ReferCommercialToLegal", "controller", "correspondence", False, False),
    ("RegisterCodeList", "admin", "engineering", False, False),
    ("RegisterDocument", "user", "documents", False, False),
    ("RegisterDocumentSchema", "admin", "documents", False, False),
    ("RegisterEnricher", "admin", None, False, False),
    ("RegisterIntegrationApp", "admin", None, False, False),
    ("RegisterMnemonic", "admin", "engineering", False, False),
    ("RegisterNumberingPattern", "admin", "engineering", False, False),
    ("RegisterParty", "controller", "correspondence", False, False),
    ("RegisterSignedRendition", "controller", "documents", False, False),
    ("ReinspectInspection", "quality.inspection.plan", "quality", False, False),
    ("ReinstateWbsNode", "awp.wbs.configure", "awp", False, False),
    ("ReissueTechnical", "user", "correspondence", False, False),
    ("RejectEnrichment", "user", None, False, False),
    ("RejectReceipt", "materials.receipt.decide", "materials", False, False),
    ("ReleaseCwp", "awp.cwp.release", "awp", False, False),
    ("ReleaseHold", "awp.iwp.hold", "awp", False, False),
    ("RemoveIwpScope", "awp.iwp.edit", "awp", False, False),
    ("RenameTag", "user", "engineering", False, False),
    ("ReopenCwp", "awp.cwp.close", "awp", False, False),
    ("ReopenPunchItem", "quality.punch.reopen", "quality", False, False),
    ("RepinDocumentLink", "user", "documents", False, False),
    ("RepinLink", "user", None, False, False),
    ("ReplaceSignedRendition", "controller", "documents", False, False),
    ("RequestRollup", "awp.cwp.edit", "awp", False, False),
    ("RequestSchemaChanges", "admin", "schemareg", False, False),
    ("RequestWaiver", "user", "schemareg", False, False),
    ("ReserveStock", "materials.reserve", "materials", False, False),
    ("RestartClock", "user", "correspondence", False, False),
    ("ResumeAgent", "admin", None, False, False),
    ("ResumeClock", "user", "correspondence", False, False),
    ("RetireAction", "admin", None, False, False),
    ("RetireChecklist", "quality.checklist.publish", "quality", False, False),
    ("RetireClause", "controller", "correspondence", False, False),
    ("RetireCwa", "awp.wbs.configure", "awp", False, False),
    ("RetireDocumentSchema", "admin", "documents", False, False),
    ("RetireItem", "materials.library.edit", "materials", False, False),
    ("RetireLocation", "materials.location.configure", "materials", False, False),
    ("RetireParty", "controller", "correspondence", False, False),
    ("RetireSchemaPackage", "admin", "schemareg", False, False),
    ("RetireWbsNode", "awp.wbs.configure", "awp", False, False),
    ("RetractLink", "user", None, False, False),
    ("RetractPost", "user", None, False, False),
    ("RetractThreadMessage", "user", None, False, False),
    ("RetryInboundDelivery", "admin", None, False, False),
    ("ReturnCommercial", "controller", "correspondence", False, False),
    ("ReturnCwp", "awp.cwp.release", "awp", False, False),
    ("ReturnIwpToDevelopment", "awp.iwp.edit", "awp", False, False),
    ("ReturnScopeItem", "awp.progress.record", "awp", False, False),
    ("ReturnStock", "materials.move", "materials", False, False),
    ("ReturnTechnical", "user", "correspondence", False, False),
    ("ReviewCommercial", "controller", "correspondence", False, False),
    ("ReviewTechnicalAnswer", "user", "correspondence", False, False),
    ("ReviseAction", "admin", None, False, False),
    ("ReviseChecklist", "quality.checklist.publish", "quality", False, False),
    ("ReviseCwa", "awp.cwa.edit", "awp", False, False),
    ("ReviseCwp", "awp.cwp.edit", "awp", False, False),
    ("ReviseEnricher", "admin", None, False, False),
    ("ReviseInboundEndpoint", "admin", None, False, False),
    ("ReviseIntegrationApp", "admin", None, False, False),
    ("ReviseItem", "materials.library.edit", "materials", False, False),
    ("ReviseLocation", "materials.location.configure", "materials", False, False),
    ("ReviseReceipt", "materials.receive", "materials", False, False),
    ("ReviseRule", "admin", None, False, False),
    ("ReviseSchemaPackage", "user", "schemareg", False, False),
    ("ReviseTagClass", "admin", "engineering", False, False),
    ("ReviseWbsNode", "awp.wbs.configure", "awp", False, False),
    ("RevokeScanCode", "qr.revoke", "qr", False, False),  # P2-QR S2
    ("RevokeWaiver", "admin", "schemareg", False, False),
    ("RotateScanCode", "qr.issue", "qr", False, False),  # P2-QR S2
    ("RunEnricher", "user", None, False, False),
    ("ScheduleInspection", "quality.inspection.plan", "quality", False, False),
    ("ScrapStock", "materials.adjust", "materials", False, False),
    ("SendIwpToConstraintCheck", "awp.iwp.edit", "awp", False, False),
    ("SetCorrespondenceConfidentiality", "controller", "correspondence", False, False),
    ("SetDocumentConfidentiality", "controller", "documents", False, False),
    ("SetEnricherEnabled", "admin", None, False, False),
    ("SetInboundEndpointEnabled", "admin", None, False, False),
    ("SetIntegrationAppEnabled", "admin", None, False, False),
    ("SetPsetValues", "user", None, False, False),
    ("SignOffIwp", "awp.iwp.signoff", "awp", False, False),
    ("SplitIwp", "awp.iwp.edit", "awp", False, False),
    ("StartClock", "user", "correspondence", False, False),
    ("StartCwpDevelopment", "awp.cwp.edit", "awp", False, False),
    ("StartCwpExecution", "awp.cwp.edit", "awp", False, False),
    ("StartExtraction", "user", "documents", False, False),
    ("StartIwpDevelopment", "awp.iwp.edit", "awp", False, False),
    ("StartIwpWork", "awp.iwp.edit", "awp", False, False),
    ("StartScheduleSnapshot", "user", "schedule", False, False),
    ("StopAgent", "admin", None, False, False),
    ("SubmitCommercial", "controller", "correspondence", False, False),
    ("SubmitSchemaPackage", "user", "schemareg", False, False),
    ("SubmitTechnical", "user", "correspondence", False, False),
    ("SuggestLink", "user", None, False, False),
    ("SupersedeCorrespondence", "controller", "correspondence", False, False),
    ("SupersedeDocument", "controller", "documents", False, False),
    ("SupersedeRevision", "controller", "documents", False, False),
    ("SweepClocks", "controller", "correspondence", False, False),
    ("TransferStock", "materials.move", "materials", False, False),
    ("TransitionWorkflow", "user", None, False, True),
    ("UnreserveStock", "materials.reserve", "materials", False, False),
    ("UpdateCommercial", "controller", "correspondence", False, False),
    ("UpdateCorrespondence", "user", "correspondence", False, False),
    ("UpdateDocument", "user", "documents", False, False),
    ("UpdateExternalPackage", "awp.package.edit", "awp", False, False),
    ("UpdatePoLine", "materials.po.edit", "materials", False, False),
    ("UpdateRecord", "user", None, False, False),
    ("UpdateTechnical", "user", "correspondence", False, False),
    ("ValidateDerived", "user", "documents", False, False),
    ("VerifyInspection", "quality.inspection.verify", "quality", False, False),
    ("VerifyLink", "user", None, False, False),
    ("VerifyPunchItem", "quality.punch.verify", "quality", False, False),
    ("VerifyScopeItem", "awp.progress.record", "awp", False, False),
    ("VoidCorrespondence", "controller", "correspondence", False, False),
    ("VoidCwp", "awp.void", "awp", False, False),
    ("VoidDerivedDocument", "controller", "documents", False, False),
    ("VoidDocument", "controller", "documents", False, False),
    ("VoidDraft", "user", "correspondence", False, False),
    ("VoidExternalPackage", "awp.void", "awp", False, False),
    ("VoidPunchItem", "quality.punch.void", "quality", False, False),
    ("VoidReceipt", "materials.void", "materials", False, False),
    ("VoidRevision", "user", "documents", False, False),
    ("VoidScheduleSnapshot", "controller", "schedule", False, False),
    ("VoidTransmittal", "user", "documents", False, False),
    ("WithdrawClearance", "controller", "correspondence", False, False),
    ("WithdrawConstraint", "core.constraint.edit", None, False, False),
    # forms rows served through the forms commands hook (P2-IP-X4 F2), captured at that merge
    ("AcceptFormSubmission", "forms.review", "forms", False, False),
    ("AcceptIntakeItem", "forms.intake.review", "forms", False, False),
    ("DiscardFormDraft", "forms.submit", "forms", False, False),
    ("DraftFormTemplate", "forms.template.edit", "forms", False, False),
    ("EditFormTemplate", "forms.template.edit", "forms", False, False),
    ("IssueIntakeCode", "forms.intake.issue", "forms", False, False),
    ("PublishFormTemplate", "forms.template.publish", "forms", False, False),
    ("RejectIntakeItem", "forms.intake.review", "forms", False, False),
    ("RetireFormTemplate", "forms.template.publish", "forms", False, False),
    ("ReturnFormSubmission", "forms.review", "forms", False, False),
    ("ReviseFormTemplate", "forms.template.edit", "forms", False, False),
    ("RevokeIntakeCode", "forms.intake.issue", "forms", False, False),
    ("SaveFormDraft", "forms.submit", "forms", False, False),
    ("SubmitForm", "forms.submit", "forms", False, False),
    ("VoidFormSubmission", "forms.void", "forms", False, False),
]


def flat(container: Any) -> list[Any]:
    """The routes of an app or router in order; an included router is one entry with its own."""
    found: list[Any] = []
    for route in container:
        inner = getattr(route, "original_router", None)
        if inner is not None:
            found.extend(flat(inner.routes))
        else:
            found.append(route)
    return found


def route_lines(app: Any) -> list[str]:
    """``<METHODS> <path>`` per route in order; the web client's pages are mounted by ``TL_WEB``
    (on in test, off in the capture) and are not part of this table."""
    return [
        f"{','.join(sorted(getattr(r, 'methods', None) or []))} {r.path}"
        for r in flat(app.routes)
        if not r.path.startswith("/web")
    ]


def old_lines() -> list[str]:
    return ORDER_FILE.read_text().splitlines()


def can_match(a: str, b: str) -> bool:
    """Whether two route paths can match one URL: same segment count, each pair equal or a param."""
    sa, sb = a.split("/"), b.split("/")
    return len(sa) == len(sb) and all(
        x == y or x.startswith("{") or y.startswith("{") for x, y in zip(sa, sb, strict=True)
    )


# --- 1 and 2: the same table and the same routes, plus the requisitions commands ---------------


def test_the_command_rows_are_the_old_rows_plus_the_requisitions_commands() -> None:
    new = sorted(
        (c.name, c.access, c.module, c.needs_holds, c.takes_roles) for c in commands_module.COMMANDS
    )
    added = [row for row in new if row not in OLD_COMMANDS]
    assert [r for r in OLD_COMMANDS if r not in new] == []
    assert sorted(r[0] for r in added) == sorted(REQUISITION_NAMES)
    assert all(r[2] == "requisitions" for r in added)
    assert {(r[0], r[1]) for r in added} == {
        (c.model.__name__, c.access) for c in REQUISITIONS_COMMANDS
    }
    assert len(new) == len(OLD_COMMANDS) + 10


def test_the_route_set_is_the_old_set_plus_the_requisitions_command_routes(
    harness: Harness,
) -> None:
    new = set(route_lines(harness.app))
    old = set(old_lines())
    assert old <= new
    assert new - old == {f"POST /commands/{n}" for n in REQUISITION_NAMES}
    assert len(route_lines(harness.app)) == len(old_lines()) + 10


# --- 3: the requisitions commands are served ---


def _post(client: Any, name: str, body: dict[str, Any]) -> Any:
    return client.post(f"/commands/{name}", json=body)


RAISE_BODY = {
    "scope": "project:P123",
    "requisition": {
        "kind": "labor",
        "subject": "Four welders",
        "craft": "Welder",
        "headcount": 4,
        "start_date": "2026-11-02",
        "end_date": "2026-11-13",
    },
}


def test_a_person_with_the_word_raises_a_requisition(rig: Rig) -> None:  # noqa: F811
    response = _post(rig.client("uma"), "RaiseRequisition", RAISE_BODY)
    assert response.status_code in (200, 201), response.text


def test_a_person_without_the_word_is_refused_as_on_another_module_command(
    rig: Rig,  # noqa: F811
) -> None:
    refused = _post(rig.client("uma"), "ApproveRequisition", {"scope": "project:P123"})
    other = _post(rig.client("uma"), "IssueRevision", {"scope": "project:P123"})
    assert refused.status_code == other.status_code == 403
    assert refused.json()["error"] == other.json()["error"]


def test_an_agent_token_is_refused_on_a_requisition_command(rig: Rig) -> None:  # noqa: F811
    token = add_token(rig.h.settings.tokens_path, "agent:triage")
    client = rig.h.client_for(None)
    client.headers.update({"Authorization": f"Bearer {token}"})
    for name in ("RaiseRequisition", "ApproveRequisition"):
        response = _post(client, name, RAISE_BODY)
        assert response.status_code == 403, name


# --- 4: the order of routes that can meet one URL survives -------------------------------------


def test_routes_that_can_match_one_url_keep_their_old_relative_order(harness: Harness) -> None:
    old = old_lines()
    position = {line: i for i, line in enumerate(route_lines(harness.app))}
    for i, first in enumerate(old):
        for second in old[i + 1 :]:
            (m1, p1), (m2, p2) = first.split(" ", 1), second.split(" ", 1)
            if m1 == m2 and can_match(p1, p2) and first != second:
                assert position[first] < position[second], (first, second)


def test_the_awp_progress_routes_precede_the_awp_routes(harness: Harness) -> None:
    where: dict[str, list[int]] = {"awp_progress": [], "awp_weeks": [], "awp": []}
    for i, route in enumerate(flat(harness.app.routes)):
        module = getattr(getattr(route, "endpoint", None), "__module__", "")
        name = module.removeprefix("tl_api.routes.")
        if name in where:
            where[name].append(i)
    assert all(where.values())
    assert max(where["awp_progress"]) < min(where["awp"])
    assert max(where["awp_weeks"]) < min(where["awp"])


# --- 5 and 6: a fake module, and resolution once ---


class X4Ping(Command):
    pass


class X4Pong(Command):
    pass


def _handler(uow: Any, command: Any) -> Any:
    raise AssertionError("never run")


def _spec(name: str, **hooks: Any) -> ModuleSpec:
    return ModuleSpec(
        name=name, record_types=frozenset({f"{name}.Thing"}), projectors=list, **hooks
    )


@pytest.fixture
def reimport() -> Iterator[Any]:
    """Re-import ``tl_api.commands`` inside a block and put the real table back afterwards."""
    bodies = set(commands_module.COMMAND_BODIES)
    registered = set(intent._REGISTERED)  # noqa: SLF001

    def run() -> Any:
        return importlib.reload(commands_module)

    try:
        yield run
    finally:
        importlib.reload(commands_module)
        for name in set(commands_module.COMMAND_BODIES) - bodies:
            commands_module.COMMAND_BODIES.pop(name)
        intent._REGISTERED.intersection_update(registered)  # noqa: SLF001


@pytest.fixture
def fake_packages() -> Iterator[None]:
    fake = types.ModuleType("tl_mod_x4fake")
    fake.COMMANDS = (  # type: ignore[attr-defined]
        types.SimpleNamespace(model=X4Ping, handler=_handler, access="user"),
        types.SimpleNamespace(
            model=X4Pong, handler=_handler, access="admin", needs_holds=True, takes_roles=True
        ),
    )
    router = APIRouter()

    @router.get("/x4fake/ping", name="x4fake_ping")
    def ping() -> dict[str, str]:
        return {"ok": "yes"}

    fake.ROUTER = router  # type: ignore[attr-defined]
    other = types.ModuleType("tl_mod_x4other")
    other.COMMANDS = ()  # type: ignore[attr-defined]
    sys.modules["tl_mod_x4fake"] = fake
    sys.modules["tl_mod_x4other"] = other
    try:
        yield
    finally:
        sys.modules.pop("tl_mod_x4fake", None)
        sys.modules.pop("tl_mod_x4other", None)


def _fresh_app(h: Harness) -> Any:
    return create_app(h.backend, settings=h.settings, tokens=TokenStore(h.settings.tokens_path))


def test_a_new_module_gets_its_command_and_read_route_and_a_broken_one_loses_only_its_own(
    harness: Harness,
    fake_packages: None,
    reimport: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    good = _spec(
        "x4fake",
        commands="tl_mod_x4fake:COMMANDS",
        read_routers=("tl_mod_x4fake:ROUTER",),
        command_words={"X4Ping": "user", "X4Pong": "admin"},
    )
    broken = _spec(
        "x4other",
        commands="tl_mod_x4other:COMMANDS",
        read_routers=("tl_mod_x4other:MISSING",),
    )
    with use_modules([good, broken]):
        reimport()
        with caplog.at_level(logging.WARNING, logger="tl_api"):
            lines = route_lines(_fresh_app(harness))
    assert "POST /commands/X4Ping" in lines
    rows = {c.name: c for c in commands_module.COMMANDS}
    assert (rows["X4Ping"].module, rows["X4Ping"].access) == ("x4fake", "user")
    assert rows["X4Pong"].access == "admin"  # the declared word, not the default
    assert rows["X4Pong"].needs_holds and rows["X4Pong"].takes_roles
    assert not rows["X4Ping"].needs_holds and not rows["X4Ping"].takes_roles
    assert "GET /x4fake/ping" in lines
    assert not any("x4other" in line for line in lines)
    messages = [r.getMessage() for r in caplog.records if r.name == "tl_api"]
    assert len(messages) == 1
    assert "x4other" in messages[0] and "MISSING" not in messages[0]
    assert "tl_mod_x4other" not in messages[0]


def test_module_commands_is_resolved_once_per_import_not_per_request(
    rig: Rig,  # noqa: F811
    reimport: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []
    real = tl_modules.module_commands

    def counting() -> Any:
        calls.append(1)
        return real()

    monkeypatch.setattr(tl_modules, "module_commands", counting)
    reimport()
    assert calls == [1]
    app = create_app(
        rig.h.backend, settings=rig.h.settings, tokens=TokenStore(rig.h.settings.tokens_path)
    )
    client = rig.h.client_for(None)
    for _ in range(3):
        client.post("/commands/RaiseRequisition", json=RAISE_BODY)
    assert app is not None
    assert calls == [1]
