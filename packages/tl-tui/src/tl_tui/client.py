"""The client interface every TUI screen uses (P0-I2 contract; brief 4, 10).

Screens never import tl_core services directly. The embedded implementation (P0-I2) calls tl_core in
process; the remote implementation (P0-I4) calls the API. Same methods, same return shapes.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from typing import Any, Literal, Protocol

from pydantic import BaseModel
from tl_core.auth.types import AccountKind, AccountView, AgentTokenView
from tl_core.extypes.service import BodyStoredOut, BodyView, TypeDetail, TypeSummary
from tl_core.extypes.types import TypeStatus
from tl_core.ledger import Event
from tl_core.links.expected import MissingLink
from tl_core.numbering.detect import KeyChip
from tl_core.services.commands import Command, CommandResult, CreateRecord, UpdateRecord
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
from tl_core.settings.types import SettingChange
from tl_core.settings.views import SettingView
from tl_core.threads.dispatch import DispatchFromThread
from tl_core.threads.messages import EditThreadMessage, PostThreadMessage, RetractThreadMessage
from tl_core.threads.planner import PreviewResult
from tl_core.threads.queries import ThreadPage
from tl_mod_correspondence import evidence as correspondence_evidence
from tl_mod_correspondence import reports_commercial, reports_technical
from tl_mod_correspondence import views as correspondence_views
from tl_mod_correspondence import views_domain as correspondence_domain_views
from tl_mod_cost import views as cost_views
from tl_mod_documents import reports as document_reports
from tl_mod_documents import views as document_views
from tl_mod_documents.derivation import views as derivation_views
from tl_mod_documents.derivation.derived import (
    CancelJob,
    OpenDerivedDocument,
    StartExtraction,
    ValidateDerived,
    VoidDerivedDocument,
)
from tl_mod_documents.derivation.diff import DerivedDiff
from tl_mod_documents.derivation.publish import (
    CompensatePublication,
    CompensationPlan,
    PublishDerivedDocuments,
    PublishDerivedTags,
    PublishPlan,
)
from tl_mod_documents.derivation.validation import ValidationReport
from tl_mod_documents.handlers.transmittals import CreateTransmittal, IssueTransmittal
from tl_mod_documents.resolver import RepinDocumentLink
from tl_mod_engineering.views import TagView
from tl_mod_schedule import views as schedule_views
from tl_mod_schedule.compare import Comparison
from tl_mod_schedule.handlers.activity import LinkActivity
from tl_mod_schedule.handlers.publish import PublishScheduleSnapshot
from tl_mod_schedule.lookahead import LookAhead
from tl_mod_schedule.resolver import ActivityLink, OrphanedLink, Resolution
from tl_mod_schemareg import views as schemareg_views
from tl_mod_schemareg.impact_types import ImpactReport
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

    # --- extension record types (P0-I8; brief 31) ---------------------------------------------

    def list_types(self, status: TypeStatus | None = None) -> list[TypeSummary]:
        """Registered extension type versions by type ref, optionally of one status."""
        ...

    def get_type(self, type_ref: str) -> TypeDetail:
        """One version with its generated form (``TypeDetail.form``); ``UnknownTypeError``."""
        ...

    def create_instance(
        self,
        type_name: str,
        *,
        scope: str,
        title: str,
        key: str | None = None,
        description: str | None = None,
        psets: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        numbering: dict[str, str] | None = None,
    ) -> CommandResult:
        """Create an instance: ``psets`` for a managed type, ``body`` for an object-backed one."""
        ...

    def get_record_body(self, record_id: str) -> BodyView:
        """The verified body of an object-backed record; a damaged one is quarantined and raises."""
        ...

    def put_record_body(
        self,
        record_id: str,
        *,
        scope: str,
        body: dict[str, Any],
        expected_version: int | None = None,
    ) -> BodyStoredOut:
        """Store a new body; the index fields follow. ``ConcurrencyError`` for a stale version."""
        ...

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

    def workflow_status(self, record_id: str) -> WorkflowStatus:
        """State, state-entered time and every transition with its guard results.

        Role guards are judged for the signed-in account: the roles are derived from it, never
        chosen by the caller (ADR-0013, addendum P1-SEC1).
        """
        ...

    def transition(self, cmd: TransitionWorkflow) -> CommandResult:
        """Run a transition; raises ``GuardFailedError`` (with ``results``) when blocked.

        The command carries no roles: the server (or the embedded client) derives them from the
        signed-in account.
        """
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

    # --- record threads (P1-I7 WS-B; brief 21.5) ----------------------------------------------
    #
    # Same names and signatures as ``tl_api.client.ApiClient``. A message never dispatches; a slash
    # command is previewed with ``thread_preview`` and confirmed with ``thread_dispatch``.

    def thread_page(
        self, record_id: str, *, limit: int = 50, before_seq: int | None = None
    ) -> ThreadPage:
        """The newest messages of the record's thread (oldest first), its participants and whether
        threads and dispatch are on for it. ``before_seq`` is ``ThreadPage.next_before``."""
        ...

    def thread_post(self, cmd: PostThreadMessage) -> CommandResult:
        """Post a message. The result's ``key`` is the message id."""
        ...

    def thread_edit(self, cmd: EditThreadMessage) -> CommandResult: ...

    def thread_retract(self, cmd: RetractThreadMessage) -> CommandResult: ...

    def thread_preview(self, record_id: str, text: str) -> PreviewResult:
        """Plan a slash command as the signed-in person: a preview, or the parse problem."""
        ...

    def thread_dispatch(self, cmd: DispatchFromThread) -> CommandResult:
        """Run a previewed command (``cmd.token`` from the preview) in one transaction."""
        ...

    # --- engineering tags (P1-I1; brief 9 M2) ------------------------------------------------
    #
    # The same names and signatures as ``tl_api.client.ApiClient`` (the remote client passes them
    # through). ``project`` is the project id (scope ``project:<id>``).

    def list_tags(
        self,
        project: str,
        *,
        class_code: str | None = None,
        status: str | None = None,
        number_status: str | None = None,
        include_ended: bool = False,
        limit: int = 1000,
    ) -> list[TagView]:
        """A project's tags by number; ``issues`` is empty in a listing."""
        ...

    def get_tag(self, project: str, number: str) -> TagView:
        """One tag with its conformance issues. Raises ``TagNotFoundError`` when unknown."""
        ...

    # --- documents (P1-I2; brief 9 M1) -------------------------------------------------------
    #
    # The same names and signatures as ``tl_api.client.ApiClient``. ``project`` is the project id.
    # Unknown numbers raise ``DocumentNotFoundError`` / ``TransmittalNotFoundError``; a diff of a
    # code that is not an issued revision raises ``InvalidPinError``. Changes are the module's
    # commands (``tl_mod_documents.commands``), not methods here.

    def list_documents(
        self,
        project: str,
        *,
        doc_type: str | None = None,
        discipline: str | None = None,
        state: str | None = None,
        include_void: bool = False,
        limit: int = 1000,
    ) -> list[document_views.DocumentView]:
        """A project's documents by number; no revisions or links in a listing."""
        ...

    def get_document(self, project: str, number: str) -> document_views.DocumentView:
        """One document with its revisions, renditions and links."""
        ...

    def document_diff(
        self, project: str, number: str, from_code: str, to_code: str
    ) -> document_views.RevisionDiffView:
        """What changed between two issued revisions of a document."""
        ...

    def list_stale_links(self, project: str) -> list[document_reports.StalePinLine]:
        """Links to documents that are stale, with what replaced the pinned revision."""
        ...

    def list_overdue_reviews(
        self, project: str, *, on: date | None = None
    ) -> list[document_reports.OverdueLine]:
        """Open reviews with a reviewer who has not answered by their date."""
        ...

    def list_transmittals(
        self,
        project: str,
        *,
        state: str | None = None,
        direction: str | None = None,
        limit: int = 500,
    ) -> list[document_views.TransmittalView]:
        """A project's transmittals by number; no items in a listing."""
        ...

    def get_transmittal(self, project: str, number: str) -> document_views.TransmittalView:
        """One transmittal with its items."""
        ...

    # Two changes a person makes from the document screens are open to any signed-in person
    # (ADR-0011, ADR-0013). Issuing the transmittal is a controlling act: the server refuses it to
    # anyone but a document controller or an admin, and the screens offer it only to them.

    def repin_document_link(self, cmd: RepinDocumentLink) -> CommandResult:
        """Move a link to another revision of its document (``pin`` ``current`` for the latest)."""
        ...

    def create_transmittal(self, cmd: CreateTransmittal) -> CommandResult:
        """Draft a transmittal of issued revisions to named recipients."""
        ...

    def issue_transmittal(self, cmd: IssueTransmittal) -> CommandResult:
        """Issue a draft transmittal (a controller's act: ``ForbiddenError`` for anyone else)."""
        ...

    # --- correspondence (P1-I5; brief 9 M10) -------------------------------------------------
    #
    # The same names and signatures as ``tl_api.client.ApiClient``. ``project`` is the project id.
    # An item the person may not read is not in a list and raises ``ItemNotFoundError`` by number,
    # with the text of an item that does not exist (ADR-0016). ``correspondence_command`` runs a
    # command of ``tl_mod_correspondence.commands`` by name; issuing, setting a class, voiding a
    # received item, replacing an item, parties, clauses and the sweep are a document
    # controller's (``ForbiddenError`` for anyone else).

    def list_correspondence(
        self,
        project: str,
        *,
        state: str | None = None,
        direction: str | None = None,
        domain: str | None = None,
        subtype: str | None = None,
        awaiting_response: bool = False,
        include_void: bool = False,
        sources: bool = True,
        limit: int = 500,
        offset: int = 0,
    ) -> list[correspondence_views.RegisterLineView]:
        """The master register: items plus the lines of the domains' register sources."""
        ...

    def get_correspondence(self, project: str, number: str) -> correspondence_views.ItemView:
        """One item with its clocks."""
        ...

    def get_correspondence_suggestion(
        self, project: str, number: str
    ) -> correspondence_views.SuggestionView:
        """The domain and subtype the suggestion engine proposes for an item."""
        ...

    def suggest_domain(
        self, project: str, subject: str, body: str | None = None
    ) -> correspondence_views.SuggestionView:
        """The proposal of the suggestion engine for a text."""
        ...

    def list_threads(
        self, project: str, *, state: str | None = None
    ) -> list[correspondence_views.ThreadView]:
        """A project's threads, newest first."""
        ...

    def get_thread(self, project: str, number: str) -> correspondence_views.ThreadView:
        """One thread with the items the person may read."""
        ...

    def list_clocks(
        self,
        project: str,
        *,
        open_only: bool = True,
        overdue_only: bool = False,
        due_to: date | None = None,
    ) -> list[correspondence_views.ClockView]:
        """Response clocks, soonest due first, with days left as of today."""
        ...

    def get_clock(self, project: str, clock_id: str) -> correspondence_views.ClockView:
        """One clock."""
        ...

    def list_parties(
        self, project: str, *, include_inactive: bool = False
    ) -> list[correspondence_views.PartyView]:
        """A project's parties with their contacts."""
        ...

    def get_party(self, project: str, code: str) -> correspondence_views.PartyView:
        """One party with its contacts."""
        ...

    def list_clauses(
        self, project: str, *, include_inactive: bool = False
    ) -> list[correspondence_views.ClauseView]:
        """A project's contract clauses."""
        ...

    def list_correspondence_domains(self, project: str) -> list[correspondence_views.DomainView]:
        """The domain definitions in force for a project."""
        ...

    def correspondence_command(self, name: str, cmd: Command) -> CommandResult:
        """Run a correspondence command by name (the token's or the signed-in person's actor)."""
        ...

    # --- Technical and Commercial items (P1-I6; brief 9 M10) ---------------------------------
    #
    # The same names and signatures as ``tl_api.client.ApiClient``. The RFI log and the Commercial
    # register are the lists of the two domains; an item the person may not read is not in them
    # (Commercial items are restricted, so a plain user's register is empty). The evidence trail
    # replays the ledger to the end of a day (``as_of``, default today).

    def list_rfis(
        self,
        project: str,
        *,
        subtype: str | None = None,
        state: str | None = None,
        discipline: str | None = None,
        only_open: bool = False,
        only_overdue: bool = False,
        only_impact: bool = False,
        limit: int = 500,
    ) -> reports_technical.RfiLog:
        """The RFI log: Technical items with response times and impact flags."""
        ...

    def get_rfi(self, project: str, number: str) -> correspondence_domain_views.TechnicalView:
        """One RFI, technical query or deviation request."""
        ...

    def list_commercial(
        self,
        project: str,
        *,
        subtype: str | None = None,
        state: str | None = None,
        only_open: bool = False,
        time_bars_only: bool = False,
        limit: int = 500,
    ) -> reports_commercial.CommercialRegister:
        """The Commercial register: values by currency and time bars."""
        ...

    def get_commercial(
        self, project: str, number: str
    ) -> correspondence_domain_views.CommercialView:
        """One Commercial item."""
        ...

    def get_evidence_trail(
        self,
        project: str,
        number: str,
        *,
        as_of: date | None = None,
        depth: int = 2,
        max_nodes: int = 100,
    ) -> correspondence_evidence.EvidenceTrail:
        """The chain of records around an item as it stood at the end of ``as_of``."""
        ...

    # --- derivation (P1-I3; ADR-0014) --------------------------------------------------------
    #
    # The same names and signatures as ``tl_api.client.ApiClient``. ``project`` is the project id;
    # ``ref`` is a derived document's id or key (``ISD-001@A/instrument-index``). Unknown names
    # raise the module's ``DerivedNotFoundError`` / ``JobNotFoundError`` / ``SchemaNotFoundError``;
    # a read that needs a stage the document has not reached (rows before a pass, a report before
    # a validation) raises ``DerivedStateError``. The commands are the module's
    # (``tl_mod_documents.derivation``): starting, validating and cancelling are open to any
    # signed-in person; publishing into tags and compensating are admin acts and publishing into
    # documents a document controller's, refused with ``ForbiddenError`` to anyone else. Registering
    # a schema is not offered here (it is an admin command, ``tl derive schema``).

    def list_derived_documents(
        self,
        project: str,
        *,
        state: str | None = None,
        document: str | None = None,
        schema: str | None = None,
        include_void: bool = False,
        limit: int = 200,
    ) -> list[derivation_views.DerivedSummary]:
        """A project's derived documents, newest first; no content revisions in a listing."""
        ...

    def get_derived_document(self, project: str, ref: str) -> derivation_views.DerivedView:
        """One derived document with its content revisions and its running job."""
        ...

    def list_processing_jobs(
        self,
        project: str,
        *,
        state: str | None = None,
        derived: str | None = None,
        limit: int = 200,
    ) -> list[derivation_views.JobView]:
        """A project's jobs, newest first (``state``: queued, running, succeeded, failed, ...)."""
        ...

    def get_processing_job(self, project: str, job_id: str) -> derivation_views.JobView:
        """One job."""
        ...

    def get_derived_rows(
        self,
        project: str,
        ref: str,
        *,
        content_rev: int | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> derivation_views.RowsPage:
        """A page of the extracted rows of a content revision (the latest by default)."""
        ...

    def get_derived_report(
        self, project: str, ref: str, *, content_rev: int | None = None
    ) -> ValidationReport:
        """The stored validation report of a content revision."""
        ...

    def get_derived_diff(
        self,
        project: str,
        ref: str,
        *,
        against: str = "previous_pass",
        content_rev: int | None = None,
    ) -> DerivedDiff:
        """What changed against the previous pass or the previous revision of the document."""
        ...

    def get_publish_preview(
        self, project: str, ref: str, *, target: str | None = None
    ) -> PublishPlan:
        """What publishing would do with each row now; writes nothing."""
        ...

    def get_compensation_preview(self, project: str, ref: str) -> CompensationPlan:
        """What compensating the publication in force would reverse; writes nothing."""
        ...

    def open_derived_document(self, cmd: OpenDerivedDocument) -> CommandResult:
        """Open the derived document of a revision for a schema (the person's, no job yet)."""
        ...

    def start_extraction(self, cmd: StartExtraction) -> CommandResult:
        """Queue an extraction job (any signed-in person)."""
        ...

    def validate_derived(self, cmd: ValidateDerived) -> CommandResult:
        """Queue a validation job over a content revision (any signed-in person)."""
        ...

    def cancel_job(self, cmd: CancelJob) -> CommandResult:
        """Cancel a queued job."""
        ...

    def void_derived_document(self, cmd: VoidDerivedDocument) -> CommandResult:
        """Void a derived document that is not published (controller or admin)."""
        ...

    def publish_derived_tags(self, cmd: PublishDerivedTags) -> CommandResult:
        """Create the tags of a valid derived document (admin; ``ForbiddenError`` otherwise)."""
        ...

    def publish_derived_documents(self, cmd: PublishDerivedDocuments) -> CommandResult:
        """Register the documents of a valid derived document (controller or admin)."""
        ...

    def compensate_publication(self, cmd: CompensatePublication) -> CommandResult:
        """Roll back the publication in force (admin; all or nothing)."""
        ...

    # --- schedules and cost (P1-I4; brief 9 M11) ---------------------------------------------
    #
    # The same names and signatures as ``tl_api.client.ApiClient``. ``project`` is the project id,
    # ``code`` a schedule's code, snapshots are named by their number within the schedule (left
    # out: the current one). A missing schedule, snapshot, activity or cost code raises the
    # module's ``ScheduleNotFoundError`` / ``SnapshotNotFoundError`` / ``ActivityNotFoundError`` /
    # ``CostCodeNotFoundError``; a snapshot that is not built has no activities
    # (``SnapshotStateError``). Publishing is a document controller's act (``ForbiddenError`` for
    # anyone else); linking is any signed-in person's. Uploading, building and importing are CLI
    # operations (``tl xer``, ``tl cost``).

    def list_schedules(self, project: str) -> list[schedule_views.ScheduleView]:
        """A project's schedules by code, without snapshots."""
        ...

    def get_schedule(
        self,
        project: str,
        code: str,
        *,
        limit: int = schedule_views.DEFAULT_SNAPSHOT_PAGE,
        offset: int = 0,
    ) -> schedule_views.ScheduleDetailView:
        """One schedule with a page of its snapshots, newest first (`snapshot_count`: all)."""
        ...

    def get_schedule_snapshot(
        self, project: str, code: str, number: int
    ) -> schedule_views.SnapshotView:
        """One snapshot by number."""
        ...

    def list_activities(
        self,
        project: str,
        code: str,
        *,
        snapshot: int | None = None,
        critical: bool | None = None,
        status: str | None = None,
        q: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> schedule_views.ActivityPage:
        """A page of a built snapshot's activities in file order, and how many matched."""
        ...

    def compare_snapshots(
        self,
        project: str,
        code: str,
        *,
        new: int | None = None,
        old: int | None = None,
        limit: int = schedule_views.DEFAULT_COMPARE_LIMIT,
    ) -> Comparison:
        """What changed between two built snapshots (default: the current and the one before)."""
        ...

    def get_look_ahead(
        self, project: str, code: str, *, snapshot: int | None = None, weeks: int = 4
    ) -> LookAhead:
        """What is under way and what starts in the next ``weeks`` (1 to 26) of the data date."""
        ...

    def list_orphaned_links(self, project: str, code: str) -> list[OrphanedLink]:
        """Links the last publication flagged because their activity left the schedule."""
        ...

    def get_schedule_activity(
        self, project: str, code: str, activity_id: str, *, snapshot: int | None = None
    ) -> schedule_views.ActivityDetail:
        """One activity with the relationships that name it."""
        ...

    def get_activity_trend(
        self, project: str, code: str, activity_id: str
    ) -> list[schedule_views.TrendPoint]:
        """The activity's float and dates in every published snapshot, oldest first."""
        ...

    def resolve_activity(
        self, project: str, code: str, activity_id: str, *, as_of: str | None = None
    ) -> Resolution:
        """What the activity is now, or as of a snapshot number or a date (``state`` says which)."""
        ...

    def list_activity_links(self, project: str, record_id: str) -> list[ActivityLink]:
        """The activity links of a record and what each resolves to now."""
        ...

    def link_activity(self, cmd: LinkActivity) -> CommandResult:
        """Link a record to an activity by its stable id (any signed-in person)."""
        ...

    def publish_schedule_snapshot(self, cmd: PublishScheduleSnapshot) -> CommandResult:
        """Make a valid snapshot the current one (controller or admin)."""
        ...

    def list_cost_snapshots(self, project: str) -> list[cost_views.CostSnapshotView]:
        """A project's cost snapshots, newest period and revision first."""
        ...

    def list_cost_codes(
        self,
        project: str,
        *,
        parent: str | None = None,
        q: str | None = None,
        limit: int = 1000,
    ) -> list[cost_views.CostCodeView]:
        """A project's cost codes by code with the latest figures stated for each."""
        ...

    def get_cost_code(self, project: str, code: str) -> cost_views.CostCodeDetailView:
        """One cost code with its children and the figures of every snapshot."""
        ...

    # --- the schema workbench (P1-I8; brief 27.8) ----------------------------------------------
    #
    # The same names and signatures as ``tl_api.client.ApiClient``. A package is named by its record
    # id or ``name@version``. A missing one raises ``SchemaPackageNotFoundError``. The writes are
    # one call: ``schemareg_command(name, cmd)`` runs a command of ``tl_mod_schemareg.commands`` by
    # name (the draft, analyse, submit, review, publish, adopt and waiver commands), as the
    # signed-in person; an admin's act by anyone else raises ``ForbiddenError``.

    def list_schema_packages(
        self,
        *,
        scope: str | None = None,
        state: str | None = None,
        package: str | None = None,
        limit: int = 200,
    ) -> list[schemareg_views.PackageSummary]:
        """Package versions by name and version, highest first."""
        ...

    def get_schema_package(self, ref: str) -> schemareg_views.PackageDetail:
        """One package with its reports, lint and the diff against its base."""
        ...

    def sample_test_schema_package(
        self, ref: str, sample: int = 1000
    ) -> schemareg_views.SampleTestView:
        """Test on sample: records that would newly be non-conformant under the draft."""
        ...

    def list_schema_adoptions(
        self, project: str | None = None
    ) -> list[schemareg_views.AdoptionView]:
        """The pins of every project, or of one."""
        ...

    def list_schema_waivers(
        self, project: str | None = None, state: str | None = None
    ) -> list[schemareg_views.WaiverView]:
        """Waivers by project and path."""
        ...

    def get_schema_drift(self, project: str) -> list[schemareg_views.DriftView]:
        """The project's version of each company package against the company's."""
        ...

    def get_project_schema_impact(self, project: str, package: str, version: str) -> ImpactReport:
        """What pinning ``package@version`` does to the project."""
        ...

    def schemareg_command(self, name: str, cmd: Command) -> CommandResult:
        """Run a schema registry command by name."""
        ...

    # --- settings (P0-I8; brief 30) -----------------------------------------------------------
    #
    # The same names and signatures as ``tl_api.client.ApiClient`` (the remote client passes them
    # through). A write answers with the key as seen at the layer it changed. Failures raise the
    # ``tl_core.services.errors`` classes (``UnknownSettingError``, ``SettingLockedError``,
    # ``InvalidSettingValueError``, ``ReasonRequiredError``, ``RiskNotAcceptedError`` ...); the
    # actor is the signed-in person.

    def list_settings(
        self,
        *,
        project: str | None = None,
        user: str | None = None,
        prefix: str | None = None,
        modified_only: bool = False,
    ) -> list[SettingView]:
        """Every setting with its definition and state, sorted by key."""
        ...

    def get_setting(
        self, key: str, *, project: str | None = None, user: str | None = None
    ) -> SettingView:
        """One setting with its definition and state."""
        ...

    def setting_history(self, key: str, *, layer: str | None = None) -> list[SettingChange]:
        """Every change of the key (at ``layer`` when given), oldest first."""
        ...

    def set_setting(
        self,
        key: str,
        *,
        layer: str,
        value: Any,
        reason: str | None = None,
        accept_risk: bool = False,
        applies_at: datetime | None = None,
    ) -> SettingView:
        """Set a key at ``company``, ``project:<id>`` or ``user:<id>``."""
        ...

    def reset_setting(
        self,
        key: str,
        *,
        layer: str,
        reason: str | None = None,
        accept_risk: bool = False,
        applies_at: datetime | None = None,
    ) -> SettingView:
        """Take the layer's own value away so it inherits again."""
        ...

    def lock_setting(
        self,
        key: str,
        *,
        locked: bool,
        reason: str,
        bounds: dict[str, Any] | None = None,
    ) -> SettingView:
        """Lock a key for projects (or unlock it) and/or bound their values; company layer."""
        ...

    def revert_setting(
        self,
        key: str,
        *,
        layer: str,
        seq: int,
        reason: str | None = None,
        accept_risk: bool = False,
    ) -> SettingView:
        """Undo the latest change of the key at ``layer`` (``seq`` is that change's number)."""
        ...

    # --- accounts and agent tokens (P1-I0; ADR-0009) ------------------------------------------
    #
    # The same names and signatures as ``tl_api.client.AdminApi`` (the remote client passes them
    # through). Only an admin may call them: the API answers 403 ``forbidden`` to anyone else and
    # the embedded client raises ``ForbiddenError`` unless its actor is an active admin account.
    # Failures raise the ``tl_core.auth.errors`` classes (``AccountNotFoundError``,
    # ``UsernameTakenError``, ``LastAdminError``, ``WeakPasswordError`` with ``issues``,
    # ``AccountStateError`` ...). A password or a token is passed in and never returned, except
    # that ``issue_agent_token`` returns the new token once.

    def list_accounts(self) -> list[AccountView]:
        """Every account with its roles, status and any lock in force, oldest first."""
        ...

    def get_account(self, account_id: str) -> AccountView:
        """One account by id; ``AccountNotFoundError``."""
        ...

    def create_account(
        self,
        username: str,
        display_name: str,
        *,
        kind: AccountKind = "person",
        roles: Sequence[str] = ("user",),
        password: str | None = None,
    ) -> AccountView:
        """Create an account. A person or sim account needs a password; an agent takes none."""
        ...

    def set_roles(
        self,
        account_id: str,
        roles: Sequence[str],
        *,
        reason: str | None = None,
        expected_roles: Sequence[str] | None = None,
    ) -> AccountView:
        """Replace the roles. The last active admin cannot be demoted (``LastAdminError``).

        ``expected_roles`` are the roles the caller read; if they changed since, nothing is
        written (``AccountStateError``).
        """
        ...

    def disable_account(self, account_id: str, *, reason: str | None = None) -> AccountView:
        """Disable an account: its sessions and agent tokens stop working."""
        ...

    def enable_account(self, account_id: str, *, reason: str | None = None) -> AccountView:
        """Enable a disabled account again."""
        ...

    def reset_password(self, account_id: str, new_password: str) -> AccountView:
        """Set a new password without the old one; ends the account's sessions, clears its lock."""
        ...

    def list_agent_tokens(
        self, account_id: str | None = None, *, include_revoked: bool = True
    ) -> list[AgentTokenView]:
        """Agent token metadata, oldest first. The tokens themselves cannot be read back."""
        ...

    def issue_agent_token(
        self, account_id: str, label: str, *, expires_in_days: int | None = 90
    ) -> tuple[AgentTokenView, str]:
        """Issue a token (``None`` days: no expiry). Returns the view and the token, once."""
        ...

    def revoke_agent_token(self, token_id: str, *, reason: str | None = None) -> AgentTokenView:
        """Revoke a token at once."""
        ...

    # --- the integration layer (P1-I7) --------------------------------------------------------
    # The same names and signatures as ``tl_api.client.IntegrationApi``. Rows are dicts of the
    # projection tables with their JSON columns parsed (``tl_core.integration.registry``); no
    # secret, payload or executor configuration is in them. ``kind`` is one of apps, actions,
    # rules, endpoints, enrichers, invocations, enrichments or deliveries (an admin's). A command
    # is one of ``tl_api.client.integration.SCREEN_COMMANDS``: the service judges the access of the
    # signed-in person and raises the service errors (``ForbiddenError``, ``IntegrationStateError``,
    # ``IntegrationNotFoundError`` ...).

    def list_integration(
        self, kind: str, *, state: str | None = None, limit: int = 200
    ) -> list[dict[str, Any]]: ...

    def integration_command(self, name: str, scope: str, **fields: Any) -> CommandResult: ...
