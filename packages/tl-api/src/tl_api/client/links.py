"""Links, trace, workflow, schema and reference reads and commands over HTTP (T47).

Same method names, parameters and return types as ``tl_tui.client.ClientInterface``. The one
difference: ``relations`` returns ``tl_api.models.RelationOut`` (same fields as the TUI's
``RelationInfo``). Failures raise the exception an embedded call raises (see ``ApiClientBase``).
"""

from __future__ import annotations

from collections.abc import Sequence

from tl_core.links.expected import MissingLink
from tl_core.numbering.detect import KeyChip
from tl_core.services.commands import CommandResult
from tl_core.services.link_queries import LinkCounts, LinkTarget, LinkView
from tl_core.services.link_trace import TraceDirection, TraceNode
from tl_core.services.links import (
    AcceptLink,
    AddLink,
    DeclineLink,
    FlagLink,
    RepinLink,
    RetractLink,
    SuggestLink,
    VerifyLink,
)
from tl_core.services.workflow import TransitionWorkflow, WorkflowStatus
from tl_schema.forms import ConformanceReport, FormMetadata

from tl_api.client.base import ApiClientBase, quote
from tl_api.models import DefaultRelationOut, RelationOut

COUNTS_CHUNK = 200  # the server accepts at most 500 ids per call


class LinksApi(ApiClientBase):
    def links_of(self, record_id: str, *, include_retracted: bool = False) -> list[LinkView]:
        """Both directions of a record's links, each with its label as read from the record."""
        data = self._get_json(
            f"/records/{quote(record_id)}/links",
            {"include_retracted": include_retracted},
        )
        return self._models(LinkView, data)

    def link_counts(self, record_ids: Sequence[str]) -> dict[str, LinkCounts]:
        """Link counts per record id (zeros when none). Large lists are sent in chunks."""
        ids = list(record_ids)
        counts: dict[str, LinkCounts] = {}
        for start in range(0, len(ids), COUNTS_CHUNK):
            chunk = ids[start : start + COUNTS_CHUNK]
            data = self._get_json("/links/counts", {"record_id": chunk})
            counts.update({rid: LinkCounts.model_validate(row) for rid, row in data.items()})
        return counts

    def expected_links(self, record_id: str) -> list[MissingLink]:
        """Expected links the record does not have yet."""
        data = self._get_json(f"/records/{quote(record_id)}/expected-links")
        return self._models(MissingLink, data)

    def search_linkable(
        self,
        scope: str,
        query: str,
        *,
        record_type: str | None = None,
        exclude_id: str | None = None,
        limit: int = 20,
    ) -> list[LinkTarget]:
        """Records the link picker may offer (the scope's and the company's, never voided)."""
        data = self._get_json(
            "/links/search",
            {
                "scope": scope,
                "q": query,
                "record_type": record_type,
                "exclude_id": exclude_id,
                "limit": limit,
            },
        )
        return self._models(LinkTarget, data)

    def trace(
        self, record_id: str, *, depth: int = 2, direction: TraceDirection = "both"
    ) -> TraceNode:
        """The n-hop tree of records reachable through links."""
        data = self._get_json(
            f"/records/{quote(record_id)}/trace",
            {"depth": depth, "direction": direction},
        )
        return self._model(TraceNode, data)

    def detect_keys(self, scope: str, text: str, *, linked_to: str | None = None) -> list[KeyChip]:
        """Keys found in ``text`` that fit a numbering pattern of the scope, resolved to records."""
        data = self._post_json(
            "/keys/detect",
            {"scope": scope, "text": text, "linked_to": linked_to},
        )
        return self._models(KeyChip, data)

    def relations(self) -> list[RelationOut]:
        """The relation vocabulary in display order."""
        return self._models(RelationOut, self._get_json("/relations"))

    def default_relation(self, from_type: str, to_type: str) -> str:
        """The relation to pre-select for a pair of record types."""
        data = self._get_json(
            "/relations/default",
            {"from_type": from_type, "to_type": to_type},
        )
        return DefaultRelationOut.model_validate(data).relation

    def add_link(self, cmd: AddLink) -> CommandResult:
        return self._command("AddLink", cmd)

    def suggest_link(self, cmd: SuggestLink) -> CommandResult:
        return self._command("SuggestLink", cmd)

    def accept_link(self, cmd: AcceptLink) -> CommandResult:
        return self._command("AcceptLink", cmd)

    def decline_link(self, cmd: DeclineLink) -> CommandResult:
        return self._command("DeclineLink", cmd)

    def repin_link(self, cmd: RepinLink) -> CommandResult:
        return self._command("RepinLink", cmd)

    def verify_link(self, cmd: VerifyLink) -> CommandResult:
        return self._command("VerifyLink", cmd)

    def flag_link(self, cmd: FlagLink) -> CommandResult:
        return self._command("FlagLink", cmd)

    def retract_link(self, cmd: RetractLink) -> CommandResult:
        return self._command("RetractLink", cmd)

    def workflow_status(self, record_id: str, *, roles: Sequence[str] = ()) -> WorkflowStatus:
        """State, state-entered time and every transition with its guard results."""
        data = self._get_json(
            f"/records/{quote(record_id)}/workflow",
            {"role": list(roles)},
        )
        return self._model(WorkflowStatus, data)

    def transition(self, cmd: TransitionWorkflow) -> CommandResult:
        """Run a transition; raises ``GuardFailedError`` (with ``results``) when blocked."""
        return self._command("TransitionWorkflow", cmd)

    def form_metadata(self, scope: str, record_type: str) -> FormMetadata:
        """Form and grid metadata for a record type under the scope's effective schema."""
        data = self._get_json("/schema/forms", {"scope": scope, "record_type": record_type})
        return self._model(FormMetadata, data)

    def conformance(self, record_id: str) -> ConformanceReport:
        """Conformance of a record's current values against its scope's effective schema."""
        data = self._get_json(f"/records/{quote(record_id)}/conformance")
        return self._model(ConformanceReport, data)
