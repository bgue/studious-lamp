"""The client interface every TUI screen uses (P0-I2 contract; brief 4, 10).

Screens never import tl_core services directly. The embedded implementation (P0-I2) calls tl_core in
process; the remote implementation (P0-I4) calls the API. Same methods, same return shapes.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal, Protocol

from pydantic import BaseModel
from tl_core.ledger import Event
from tl_core.links.expected import MissingLink
from tl_core.numbering.detect import KeyChip
from tl_core.services.commands import CommandResult, CreateRecord, UpdateRecord
from tl_core.services.edit import EditRecord
from tl_core.services.feed import EditPost, PostToFeed
from tl_core.services.feed_actions import ReactToPost, RetractPost
from tl_core.services.feed_queries import Completion, FeedPage
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
from tl_core.services.psets import SetPsetValues
from tl_core.services.workflow import TransitionWorkflow, WorkflowStatus
from tl_schema.forms import ConformanceReport, FormMetadata


class RelationInfo(BaseModel):
    """A relation of the link vocabulary, for the link picker (brief 7.1)."""

    code: str  # forward code, e.g. "raised_against"
    label: str  # "raised against"
    inverse_code: str
    inverse_label: str  # "has raised"


class ClientInterface(Protocol):
    def list_records(
        self,
        scope: str,
        *,
        record_type: str | None = None,
        status: str | None = None,
        include_voided: bool = False,
        limit: int = 500,
        offset: int = 0,
        order_by: list[tuple[str, Literal["asc", "desc"]]] | None = None,
    ) -> list[dict[str, Any]]: ...

    def query_records(
        self,
        scope: str,
        q: str,
        *,
        limit: int = 500,
        offset: int = 0,
        order_by: list[tuple[str, Literal["asc", "desc"]]] | None = None,
    ) -> list[dict[str, Any]]:
        """Records of ``scope`` matching the query-language text ``q`` (the filter bar, P0-I4).

        Blank ``q`` matches every record. Raises ``QuerySyntaxError`` (with ``position``) for text
        that does not parse. Unlike ``list_records`` it does not filter on a record type: say
        ``type:...`` in the text.
        """
        ...

    def count_records(self, scope: str, q: str) -> int:
        """How many records of ``scope`` match ``q``; ``limit`` and ``offset`` do not apply."""
        ...

    def get_record(self, scope: str, key: str) -> dict[str, Any] | None: ...

    def get_record_by_id(self, record_id: str) -> dict[str, Any] | None: ...

    def history(self, record_id: str) -> list[Event]: ...

    def create_record(self, cmd: CreateRecord) -> CommandResult: ...

    def update_record(self, cmd: UpdateRecord) -> CommandResult: ...

    def set_pset_values(self, cmd: SetPsetValues) -> CommandResult: ...

    def edit_record(self, cmd: EditRecord) -> CommandResult:
        """Field changes and pset edits as one atomic save: all of them are applied or none."""
        ...

    def form_metadata(self, scope: str, record_type: str) -> FormMetadata: ...

    def conformance(self, record_id: str) -> ConformanceReport: ...

    # --- links (P0-I3; brief 7) ---------------------------------------------------------------

    def links_of(self, record_id: str, *, include_retracted: bool = False) -> list[LinkView]:
        """Both directions of a record's links, each with its label as read from the record."""
        ...

    def link_counts(self, record_ids: Sequence[str]) -> dict[str, LinkCounts]:
        """Link counts per record (zeros when none): for grid columns and header badges."""
        ...

    def expected_links(self, record_id: str) -> list[MissingLink]:
        """Expected links the record does not have yet (all states)."""
        ...

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
        ...

    def trace(
        self, record_id: str, *, depth: int = 2, direction: TraceDirection = "both"
    ) -> TraceNode:
        """The n-hop tree of records reachable through links."""
        ...

    def detect_keys(self, scope: str, text: str, *, linked_to: str | None = None) -> list[KeyChip]:
        """Keys found in ``text`` that fit a numbering pattern of the scope, resolved to records."""
        ...

    def relations(self) -> list[RelationInfo]:
        """The relation vocabulary in display order."""
        ...

    def default_relation(self, from_type: str, to_type: str) -> str:
        """The relation to pre-select for a pair of record types."""
        ...

    def add_link(self, cmd: AddLink) -> CommandResult: ...

    def suggest_link(self, cmd: SuggestLink) -> CommandResult: ...

    def accept_link(self, cmd: AcceptLink) -> CommandResult: ...

    def decline_link(self, cmd: DeclineLink) -> CommandResult: ...

    def repin_link(self, cmd: RepinLink) -> CommandResult: ...

    def verify_link(self, cmd: VerifyLink) -> CommandResult: ...

    def flag_link(self, cmd: FlagLink) -> CommandResult: ...

    def retract_link(self, cmd: RetractLink) -> CommandResult: ...

    # --- workflow (P0-I3; brief 8) ------------------------------------------------------------

    def workflow_status(self, record_id: str, *, roles: Sequence[str] = ()) -> WorkflowStatus:
        """State, state-entered time and every transition with its guard results."""
        ...

    def transition(self, cmd: TransitionWorkflow) -> CommandResult:
        """Run a transition; raises ``GuardFailedError`` (with ``results``) when blocked."""
        ...

    # --- feed (P0-I6; brief 21) ---------------------------------------------------------------

    def feed_page(
        self,
        scope: str,
        *,
        record_id: str | None = None,
        include_linked: bool = False,
        tag: str | None = None,
        item_type: Literal["post", "card"] | None = None,
        limit: int = 50,
        before_seq: int | None = None,
    ) -> FeedPage:
        """Posts and cards of a project, newest first, with record labels and `#hold` suggestions.

        ``record_id`` narrows to a record's feed (``include_linked``: and the records one link
        away); ``tag`` to a hashtag (``hold``, ``area:A12``) or a mention (``@party:fab-a``);
        ``item_type`` to posts or cards. ``before_seq`` is ``FeedPage.next_before`` of the
        previous page.
        """
        ...

    def feed_post(self, cmd: PostToFeed) -> CommandResult:
        """Post to the project feed; resolved record tags get a suggested `references` link."""
        ...

    def feed_edit(self, cmd: EditPost) -> CommandResult: ...

    def feed_retract(self, cmd: RetractPost) -> CommandResult: ...

    def feed_react(self, cmd: ReactToPost) -> CommandResult: ...

    def feed_complete(
        self, scope: str, sigil: Literal["#", "@"], prefix: str, *, limit: int = 8
    ) -> list[Completion]:
        """Composer candidates after ``#`` (keys, signal tags, codes, topics) or ``@`` (people)."""
        ...
