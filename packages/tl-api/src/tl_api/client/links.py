"""Links, trace, workflow, schema and reference reads and commands over HTTP (T47).

STUB (P0-I4-T47): function bodies below raise ``NotImplementedError``. Names, signatures and
docstrings are final; implement the bodies, then delete this paragraph.

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

from tl_api.client.base import ApiClientBase
from tl_api.models import RelationOut

COUNTS_CHUNK = 200  # the server accepts at most 500 ids per call


class LinksApi(ApiClientBase):
    def links_of(self, record_id: str, *, include_retracted: bool = False) -> list[LinkView]:
        """Both directions of a record's links, each with its label as read from the record."""
        raise NotImplementedError("STUB (P0-I4-T47)")

    def link_counts(self, record_ids: Sequence[str]) -> dict[str, LinkCounts]:
        """Link counts per record id (zeros when none). Large lists are sent in chunks."""
        raise NotImplementedError("STUB (P0-I4-T47)")

    def expected_links(self, record_id: str) -> list[MissingLink]:
        """Expected links the record does not have yet."""
        raise NotImplementedError("STUB (P0-I4-T47)")

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
        raise NotImplementedError("STUB (P0-I4-T47)")

    def trace(
        self, record_id: str, *, depth: int = 2, direction: TraceDirection = "both"
    ) -> TraceNode:
        """The n-hop tree of records reachable through links."""
        raise NotImplementedError("STUB (P0-I4-T47)")

    def detect_keys(self, scope: str, text: str, *, linked_to: str | None = None) -> list[KeyChip]:
        """Keys found in ``text`` that fit a numbering pattern of the scope, resolved to records."""
        raise NotImplementedError("STUB (P0-I4-T47)")

    def relations(self) -> list[RelationOut]:
        """The relation vocabulary in display order."""
        raise NotImplementedError("STUB (P0-I4-T47)")

    def default_relation(self, from_type: str, to_type: str) -> str:
        """The relation to pre-select for a pair of record types."""
        raise NotImplementedError("STUB (P0-I4-T47)")

    def add_link(self, cmd: AddLink) -> CommandResult:
        raise NotImplementedError("STUB (P0-I4-T47)")

    def suggest_link(self, cmd: SuggestLink) -> CommandResult:
        raise NotImplementedError("STUB (P0-I4-T47)")

    def accept_link(self, cmd: AcceptLink) -> CommandResult:
        raise NotImplementedError("STUB (P0-I4-T47)")

    def decline_link(self, cmd: DeclineLink) -> CommandResult:
        raise NotImplementedError("STUB (P0-I4-T47)")

    def repin_link(self, cmd: RepinLink) -> CommandResult:
        raise NotImplementedError("STUB (P0-I4-T47)")

    def verify_link(self, cmd: VerifyLink) -> CommandResult:
        raise NotImplementedError("STUB (P0-I4-T47)")

    def flag_link(self, cmd: FlagLink) -> CommandResult:
        raise NotImplementedError("STUB (P0-I4-T47)")

    def retract_link(self, cmd: RetractLink) -> CommandResult:
        raise NotImplementedError("STUB (P0-I4-T47)")

    def workflow_status(self, record_id: str, *, roles: Sequence[str] = ()) -> WorkflowStatus:
        """State, state-entered time and every transition with its guard results."""
        raise NotImplementedError("STUB (P0-I4-T47)")

    def transition(self, cmd: TransitionWorkflow) -> CommandResult:
        """Run a transition; raises ``GuardFailedError`` (with ``results``) when blocked."""
        raise NotImplementedError("STUB (P0-I4-T47)")

    def form_metadata(self, scope: str, record_type: str) -> FormMetadata:
        """Form and grid metadata for a record type under the scope's effective schema."""
        raise NotImplementedError("STUB (P0-I4-T47)")

    def conformance(self, record_id: str) -> ConformanceReport:
        """Conformance of a record's current values against its scope's effective schema."""
        raise NotImplementedError("STUB (P0-I4-T47)")
