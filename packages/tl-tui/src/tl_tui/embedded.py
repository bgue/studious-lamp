"""Embedded `ClientInterface`: calls `tl_core` services in process (brief 4, local mode).

Each call opens one unit of work (read-only for queries), runs one service function, and closes
it. There is no logic here beyond that; the remote client (`tl_tui.remote`) is the same interface
over HTTP. `for_target` opens the ledger as a `tl_adapters.backend` backend (a SQLite file or a
`postgresql://` URL) and keeps its one engine and one in-process bus for the life of the client, so
`change_feed()` can hand the app this process's own writes at once and other processes' by polling.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Iterator, Sequence
from contextlib import AbstractContextManager, contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from tl_api.auth import AGENT_MUST_PROPOSE
from tl_core.auth import accounts as account_services
from tl_core.auth import queries as account_queries
from tl_core.auth.env import current_env, demo_allowed
from tl_core.auth.errors import ForbiddenError
from tl_core.auth.password import prepare_password
from tl_core.auth.provider import PasswordIdentityProvider
from tl_core.auth.types import DEMO_USERNAME, AccountKind, AccountView, AgentTokenView
from tl_core.extypes import body as extype_bodies
from tl_core.extypes import registry as extype_registry
from tl_core.extypes.errors import BodyNotFoundError, BodyStoreUnavailableError
from tl_core.extypes.provider import attach as attach_extension_types
from tl_core.extypes.service import (
    BodyStoredOut,
    BodyView,
    TypeDetail,
    TypeSummary,
    summarise,
    type_detail,
)
from tl_core.extypes.types import TypeStatus
from tl_core.files.types import ObjectStore
from tl_core.ledger import Event
from tl_core.links.expected import MissingLink, missing_expected_links
from tl_core.links.provider import get_vocabulary
from tl_core.links.vocabulary import default_relation
from tl_core.numbering.detect import KeyChip, suggest_chips
from tl_core.query import QuerySpec, count_query, parse, run_query
from tl_core.services import (
    feed_completion,
    feed_queries,
    link_queries,
    link_trace,
    links,
    psets,
    queries,
)
from tl_core.services.commands import CommandResult, CreateRecord, UpdateRecord
from tl_core.services.edit import EditRecord, handle_edit_record
from tl_core.services.feed import EditPost, PostToFeed, handle_edit_post, handle_post
from tl_core.services.feed_actions import (
    ReactToPost,
    RetractPost,
    handle_react_to_post,
    handle_retract_post,
)
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
from tl_core.services.records import handle_create_record, handle_update_record
from tl_core.services.workflow import (
    TransitionWorkflow,
    WorkflowStatus,
    handle_transition_workflow,
    workflow_status,
)
from tl_core.settings import history as settings_history
from tl_core.settings import lock_setting as lock_in_force
from tl_core.settings import reset_setting as reset_in_force
from tl_core.settings import revert_setting as revert_in_force
from tl_core.settings import set_setting as set_in_force
from tl_core.settings.types import SettingChange
from tl_core.settings.views import SettingView, get_view, list_views, view_at
from tl_core.uow import UnitOfWork
from tl_core.util import utcnow
from tl_core.workflow.roles import workflow_roles
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
    handle_cancel_job,
    handle_open_derived_document,
    handle_start_extraction,
    handle_validate_derived,
    handle_void_derived_document,
)
from tl_mod_documents.derivation.diff import DerivedDiff
from tl_mod_documents.derivation.publish import (
    CompensatePublication,
    CompensationPlan,
    PublishDerivedDocuments,
    PublishDerivedTags,
    PublishPlan,
    handle_compensate_publication,
    handle_publish_derived_documents,
    handle_publish_derived_tags,
)
from tl_mod_documents.derivation.validation import ValidationReport
from tl_mod_documents.handlers.transmittals import (
    CreateTransmittal,
    IssueTransmittal,
    handle_create_transmittal,
    handle_issue_transmittal,
)
from tl_mod_documents.resolver import RepinDocumentLink, handle_repin_document_link
from tl_mod_engineering.views import TagView, tag_view, tag_views
from tl_mod_schedule import views as schedule_views
from tl_mod_schedule.compare import Comparison
from tl_mod_schedule.handlers.activity import LinkActivity, handle_link_activity
from tl_mod_schedule.handlers.publish import (
    PublishScheduleSnapshot,
    handle_publish_schedule_snapshot,
)
from tl_mod_schedule.lookahead import LookAhead
from tl_mod_schedule.resolver import ActivityLink, OrphanedLink, Resolution
from tl_schema.forms import ConformanceReport, FormMetadata

from tl_tui.client import RelationInfo
from tl_tui.live import ChangeFeed, EmbeddedFeed, OwnWrites
from tl_tui.sign_in import SignedIn

#: The actor of settings changes when none is given (the dev person; the header shows the same).
DEFAULT_ACTOR = "user:dev"
#: The ``source`` recorded on settings this client changes.
SOURCE = "tui"

# A callable that opens a unit of work: `factory(readonly)` returns a context manager yielding it.
UowFactory = Callable[[bool], AbstractContextManager[UnitOfWork]]


def target_uow_factory(target: str | Path) -> UowFactory:
    """A factory over the ledger ``target`` (a SQLite file or a Postgres URL), one engine per unit
    of work."""
    from tl_adapters.db import as_target, open_uow

    where = as_target(target)

    def factory(readonly: bool) -> AbstractContextManager[UnitOfWork]:
        return open_uow(where, readonly=readonly)

    return factory


class EmbeddedAuthenticator:
    """Sign-in on the ledger: checks a username and password against its accounts.

    The `Authenticator` of the embedded TUI. A failure raises the `tl_core.auth.errors` class
    (`InvalidCredentialsError`, `AccountLockedError`, `AccountDisabledError`...); lockout and the
    audit trail work as for the API. No session is created: the TUI process is the session.
    """

    def __init__(self, uow_factory: UowFactory) -> None:
        self._uow = uow_factory

    @classmethod
    def for_target(cls, target: str | Path) -> EmbeddedAuthenticator:
        """An authenticator over the ledger ``target`` (a SQLite file or a Postgres URL)."""
        return cls(target_uow_factory(target))

    @classmethod
    def for_sqlite(cls, path: str | Path) -> EmbeddedAuthenticator:
        """The same as :meth:`for_target` (the name from before Postgres support)."""
        return cls.for_target(path)

    def __call__(self, username: str, password: str) -> SignedIn:
        provider = PasswordIdentityProvider(lambda readonly=False: self._uow(readonly))
        principal = provider.authenticate_password(username, password)
        return SignedIn(
            actor=principal.actor,
            username=principal.actor.partition(":")[2],
            roles=tuple(principal.roles),
        )

    def demo_hint(self) -> str | None:
        """A line for the sign-in screen while the demo account can be used, else None."""
        if not demo_allowed(current_env()):
            return None
        with self._uow(True) as uow:
            usable = account_queries.demo_account_enabled(uow.conn())
        return f"dev setup: sign in as {DEMO_USERNAME} / {DEMO_USERNAME}" if usable else None


class EmbeddedClient:
    """`ClientInterface` over in-process services. Errors from the services propagate unchanged.

    ``own_writes`` remembers the events of every command this client ran, so a screen can tell its
    user's own saves from other writers' changes in the live feed.
    """

    def __init__(
        self,
        uow_factory: UowFactory,
        *,
        object_store: ObjectStore | None = None,
        actor: str = DEFAULT_ACTOR,
        prime_types: bool = True,
    ) -> None:
        if actor.startswith("agent:"):
            raise ValueError(
                f"{AGENT_MUST_PROPOSE}: an agent cannot use the embedded client to change records"
            )
        self._uow = uow_factory
        self._objects = object_store
        self.actor = actor  # recorded on the writes that take no command (settings, bodies)
        self.own_writes = OwnWrites()
        # the registered extension types of this ledger join the effective schema (brief 31)
        # prime_types: read the settings keys of the registered types now (the ledger must exist)
        attach_extension_types(lambda readonly=False: uow_factory(readonly), prime=prime_types)

    @classmethod
    def for_target(
        cls,
        target: str | Path,
        *,
        object_store: ObjectStore | None = None,
        actor: str = DEFAULT_ACTOR,
    ) -> EmbeddedClient:
        """A client on the ledger ``target`` (a SQLite file or a ``postgresql://`` URL).

        It keeps one engine and one in-process bus for its life (``tl_adapters.backend``). Record
        bodies of extension types need an object store: the one given, else the one the
        environment names (``TL_OBJECT_STORE``...), else none (body calls then say so).
        ``BackendUnavailableError`` says a Postgres server cannot be reached.
        """
        from tl_adapters.backend import ledger_exists, open_backend
        from tl_adapters.db import as_target
        from tl_adapters.objectstore import make_object_store

        where = as_target(target)
        store = object_store
        if store is None:
            try:
                store = make_object_store()
            except ValueError:
                store = None
        exists = ledger_exists(where)
        backend = open_backend(where)
        try:
            return cls(backend, object_store=store, actor=actor, prime_types=exists)
        except BaseException:
            backend.close()
            raise

    @classmethod
    def for_sqlite(
        cls,
        path: str | Path,
        *,
        object_store: ObjectStore | None = None,
        actor: str = DEFAULT_ACTOR,
    ) -> EmbeddedClient:
        """The same as :meth:`for_target` (the name from before Postgres support)."""
        return cls.for_target(path, object_store=object_store, actor=actor)

    def change_feed(self, scope: str | None = None) -> ChangeFeed | None:
        """The live feed for this ledger, or ``None`` when the factory has no ledger and bus."""
        ledger = getattr(self._uow, "ledger", None)
        bus = getattr(self._uow, "bus", None)
        if ledger is None or bus is None:
            return None
        return EmbeddedFeed(ledger, bus, scope=scope)

    def close(self) -> None:
        """Release the engine when the factory owns one (``for_target``)."""
        close = getattr(self._uow, "close", None)
        if callable(close):
            close()

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
    ) -> list[dict[str, Any]]:
        with self._uow(True) as uow:
            return queries.list_records(
                uow,
                scope,
                status=status,
                include_voided=include_voided,
                record_type=record_type,
                limit=limit,
                offset=offset,
                order_by=order_by,
            )

    def query_records(
        self,
        scope: str,
        q: str,
        *,
        limit: int = 500,
        offset: int = 0,
        order_by: list[tuple[str, Literal["asc", "desc"]]] | None = None,
    ) -> list[dict[str, Any]]:
        spec = QuerySpec(
            scope=scope,
            where=parse(q),  # a syntax error is raised before a transaction is opened
            order_by=list(order_by or []),
            limit=limit,
            offset=offset,
        )
        with self._uow(True) as uow:
            return run_query(uow, spec)

    def count_records(self, scope: str, q: str) -> int:
        spec = QuerySpec(scope=scope, where=parse(q))
        with self._uow(True) as uow:
            return count_query(uow, spec)

    def get_record(self, scope: str, key: str) -> dict[str, Any] | None:
        with self._uow(True) as uow:
            return queries.get_record(uow, scope, key)

    def get_record_by_id(self, record_id: str) -> dict[str, Any] | None:
        with self._uow(True) as uow:
            return queries.get_record_by_id(uow, record_id)

    def history(self, record_id: str) -> list[Event]:
        with self._uow(True) as uow:
            return queries.record_history(uow, record_id)

    def create_record(self, cmd: CreateRecord) -> CommandResult:
        with self._uow(False) as uow:
            return self.own_writes.note(handle_create_record(uow, cmd))

    def update_record(self, cmd: UpdateRecord) -> CommandResult:
        with self._uow(False) as uow:
            return self.own_writes.note(handle_update_record(uow, cmd))

    def set_pset_values(self, cmd: SetPsetValues) -> CommandResult:
        with self._uow(False) as uow:
            return self.own_writes.note(psets.handle_set_pset_values(uow, cmd))

    def edit_record(self, cmd: EditRecord) -> CommandResult:
        with self._uow(False) as uow:
            return self.own_writes.note(handle_edit_record(uow, cmd))

    def form_metadata(self, scope: str, record_type: str) -> FormMetadata:
        with self._uow(True) as uow:
            return psets.form_metadata(uow, scope, record_type)

    def conformance(self, record_id: str) -> ConformanceReport:
        with self._uow(True) as uow:
            return psets.conformance(uow, record_id)

    # --- extension record types ---------------------------------------------------------------

    def _store(self) -> ObjectStore:
        if self._objects is None:
            raise BodyStoreUnavailableError("no object store is configured for record bodies")
        return self._objects

    @contextmanager
    def _store_errors(self) -> Iterator[None]:
        """An operating-system failure of the store (no space, no permission, a missing root).

        Shown as ``BodyStoreUnavailableError``: the message names no path, which the OS error
        would, and the TUI shows ``ServiceError`` instead of stopping.
        """
        try:
            yield
        except OSError as exc:
            raise BodyStoreUnavailableError("the object store is unavailable") from exc

    def _factory(self, readonly: bool = False) -> AbstractContextManager[UnitOfWork]:
        return self._uow(readonly)

    def list_types(self, status: TypeStatus | None = None) -> list[TypeSummary]:
        with self._uow(True) as uow:
            return [summarise(v) for v in extype_registry.list_types(uow.conn(), status=status)]

    def get_type(self, type_ref: str) -> TypeDetail:
        with self._uow(True) as uow:
            return type_detail(uow, type_ref)

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
        cmd = CreateRecord(
            actor=self.actor,
            source="tui",
            scope=scope,
            record_type=type_name,
            title=title,
            key=key,
            description=description,
            psets=psets or {},
            numbering=numbering or {},
        )
        if body is None:
            with self._uow(False) as uow:
                return self.own_writes.note(handle_create_record(uow, cmd))
        store = self._store()
        with self._store_errors(), self._uow(False) as uow:
            return self.own_writes.note(
                extype_bodies.create_extension_record(uow, store, cmd, body)
            )

    def get_record_body(self, record_id: str) -> BodyView:
        store = self._store()
        with self._uow(True) as uow:
            pointer = extype_bodies.body_pointer(uow.conn(), record_id)
        if pointer is None:
            raise BodyNotFoundError(f"record {record_id!r} has no stored body")
        with self._store_errors():
            stored = extype_bodies.read_body(self._factory, store, stream_id=record_id)
        return BodyView(record_id=record_id, pointer=pointer, body=stored)

    def put_record_body(
        self,
        record_id: str,
        *,
        scope: str,
        body: dict[str, Any],
        expected_version: int | None = None,
    ) -> BodyStoredOut:
        store = self._store()
        with self._store_errors(), self._uow(False) as uow:
            return extype_bodies.store_record_body(
                uow,
                store,
                record_id=record_id,
                scope=scope,
                body=body,
                actor=self.actor,
                source="tui",
                expected_version=expected_version,
            )

    # --- links ----------------------------------------------------------------------------------

    def links_of(self, record_id: str, *, include_retracted: bool = False) -> list[LinkView]:
        with self._uow(True) as uow:
            return link_queries.links_of(uow, record_id, include_retracted=include_retracted)

    def link_counts(self, record_ids: Sequence[str]) -> dict[str, LinkCounts]:
        with self._uow(True) as uow:
            return link_queries.link_counts(uow, record_ids)

    def expected_links(self, record_id: str) -> list[MissingLink]:
        with self._uow(True) as uow:
            return missing_expected_links(uow, record_id)

    def search_linkable(
        self,
        scope: str,
        query: str,
        *,
        record_type: str | None = None,
        exclude_id: str | None = None,
        limit: int = 20,
    ) -> list[LinkTarget]:
        with self._uow(True) as uow:
            return link_queries.search_linkable(
                uow, scope, query, record_type=record_type, exclude_id=exclude_id, limit=limit
            )

    def trace(
        self, record_id: str, *, depth: int = 2, direction: TraceDirection = "both"
    ) -> TraceNode:
        with self._uow(True) as uow:
            return link_trace.trace(uow, record_id, depth=depth, direction=direction)

    def detect_keys(self, scope: str, text: str, *, linked_to: str | None = None) -> list[KeyChip]:
        with self._uow(True) as uow:
            return suggest_chips(uow, scope, text, linked_to=linked_to)

    def relations(self) -> list[RelationInfo]:
        vocabulary = get_vocabulary()
        found = (vocabulary.get(code) for code in vocabulary.codes())
        return [
            RelationInfo(
                code=r.code,
                label=r.label,
                inverse_code=r.inverse_code,
                inverse_label=r.inverse_label,
            )
            for r in found
        ]

    def default_relation(self, from_type: str, to_type: str) -> str:
        return default_relation(from_type, to_type)

    def add_link(self, cmd: AddLink) -> CommandResult:
        with self._uow(False) as uow:
            return self.own_writes.note(links.handle_add_link(uow, cmd))

    def suggest_link(self, cmd: SuggestLink) -> CommandResult:
        with self._uow(False) as uow:
            return self.own_writes.note(links.handle_suggest_link(uow, cmd))

    def accept_link(self, cmd: AcceptLink) -> CommandResult:
        with self._uow(False) as uow:
            return self.own_writes.note(links.handle_accept_link(uow, cmd))

    def decline_link(self, cmd: DeclineLink) -> CommandResult:
        with self._uow(False) as uow:
            return self.own_writes.note(links.handle_decline_link(uow, cmd))

    def repin_link(self, cmd: RepinLink) -> CommandResult:
        with self._uow(False) as uow:
            return self.own_writes.note(links.handle_repin_link(uow, cmd))

    def verify_link(self, cmd: VerifyLink) -> CommandResult:
        with self._uow(False) as uow:
            return self.own_writes.note(links.handle_verify_link(uow, cmd))

    def flag_link(self, cmd: FlagLink) -> CommandResult:
        with self._uow(False) as uow:
            return self.own_writes.note(links.handle_flag_link(uow, cmd))

    def retract_link(self, cmd: RetractLink) -> CommandResult:
        with self._uow(False) as uow:
            return self.own_writes.note(links.handle_retract_link(uow, cmd))

    # --- workflow -------------------------------------------------------------------------------

    def _workflow_roles(self, uow: UnitOfWork, actor: str) -> tuple[str, ...]:
        """The workflow roles of this client's own active account, derived from the ledger.

        Nothing the caller or a command says is used (ADR-0013, addendum P1-SEC1). The account is
        looked up by this client's actor and must be the same character for character and active;
        anything else (no such account, a disabled one, another actor in the command) holds no
        roles, so every ``roles`` guard fails.
        """
        if actor != self.actor:
            return ()
        found = account_queries.find_account(uow.conn(), username=actor.partition(":")[2])
        if found is None or account_queries.actor_of(found) != actor or found.status != "active":
            return ()
        return workflow_roles(found)

    def workflow_status(self, record_id: str) -> WorkflowStatus:
        with self._uow(True) as uow:
            return workflow_status(uow, record_id, roles=self._workflow_roles(uow, self.actor))

    def transition(self, cmd: TransitionWorkflow) -> CommandResult:
        with self._uow(False) as uow:
            roles = self._workflow_roles(uow, cmd.actor)
            return self.own_writes.note(handle_transition_workflow(uow, cmd, roles=roles))

    # --- feed -----------------------------------------------------------------------------------

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
        with self._uow(True) as uow:
            page = feed_queries.list_feed(
                uow,
                scope,
                record_id=record_id,
                include_linked=include_linked,
                tag=tag,
                item_type=item_type,
                limit=limit,
                before_seq=before_seq,
            )
            suggestions = feed_completion.feed_suggestions(uow, page.items)
            return dataclasses.replace(page, suggestions=suggestions)

    def feed_post(self, cmd: PostToFeed) -> CommandResult:
        with self._uow(False) as uow:
            return self.own_writes.note(handle_post(uow, cmd))

    def feed_edit(self, cmd: EditPost) -> CommandResult:
        with self._uow(False) as uow:
            return self.own_writes.note(handle_edit_post(uow, cmd))

    def feed_retract(self, cmd: RetractPost) -> CommandResult:
        with self._uow(False) as uow:
            return self.own_writes.note(handle_retract_post(uow, cmd))

    def feed_react(self, cmd: ReactToPost) -> CommandResult:
        with self._uow(False) as uow:
            return self.own_writes.note(handle_react_to_post(uow, cmd))

    def feed_complete(
        self, scope: str, sigil: Literal["#", "@"], prefix: str, *, limit: int = 8
    ) -> list[Completion]:
        with self._uow(True) as uow:
            return feed_completion.complete_tags(uow, scope, sigil, prefix, limit=limit)

    # --- engineering tags (P1-I1) -------------------------------------------------------------

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
        with self._uow(True) as uow:
            return tag_views(
                uow.conn(),
                f"project:{project}",
                class_code=class_code,
                status=status,
                number_status=number_status,
                include_ended=include_ended,
                limit=limit,
            )

    def get_tag(self, project: str, number: str) -> TagView:
        with self._uow(True) as uow:
            return tag_view(uow, f"project:{project}", number)

    # --- documents (P1-I2) --------------------------------------------------------------------

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
        with self._uow(True) as uow:
            return document_views.document_views(
                uow.conn(),
                f"project:{project}",
                doc_type=doc_type,
                discipline=discipline,
                state=state,
                include_void=include_void,
                limit=limit,
            )

    def get_document(self, project: str, number: str) -> document_views.DocumentView:
        with self._uow(True) as uow:
            return document_views.document_view(uow.conn(), f"project:{project}", number)

    def document_diff(
        self, project: str, number: str, from_code: str, to_code: str
    ) -> document_views.RevisionDiffView:
        with self._uow(True) as uow:
            return document_views.revision_diff_view(
                uow.conn(), f"project:{project}", number, from_code, to_code
            )

    def list_stale_links(self, project: str) -> list[document_reports.StalePinLine]:
        with self._uow(True) as uow:
            return document_views.stale_links(uow.conn(), f"project:{project}")

    def list_overdue_reviews(
        self, project: str, *, on: date | None = None
    ) -> list[document_reports.OverdueLine]:
        with self._uow(True) as uow:
            return document_views.overdue_reviews(uow.conn(), f"project:{project}", on=on)

    def list_transmittals(
        self,
        project: str,
        *,
        state: str | None = None,
        direction: str | None = None,
        limit: int = 500,
    ) -> list[document_views.TransmittalView]:
        with self._uow(True) as uow:
            return document_views.transmittal_views(
                uow.conn(), f"project:{project}", state=state, direction=direction, limit=limit
            )

    def get_transmittal(self, project: str, number: str) -> document_views.TransmittalView:
        with self._uow(True) as uow:
            return document_views.transmittal_view(uow.conn(), f"project:{project}", number)

    def repin_document_link(self, cmd: RepinDocumentLink) -> CommandResult:
        with self._uow(False) as uow:
            return self.own_writes.note(handle_repin_document_link(uow, cmd))

    def create_transmittal(self, cmd: CreateTransmittal) -> CommandResult:
        with self._uow(False) as uow:
            return self.own_writes.note(handle_create_transmittal(uow, cmd))

    def issue_transmittal(self, cmd: IssueTransmittal) -> CommandResult:
        with self._uow(False) as uow:
            self._controller_gate(uow)
            if cmd.actor != self.actor:  # the gate checked this client's actor, so must the command
                raise ForbiddenError("the command names an actor other than the signed-in person")
            return self.own_writes.note(handle_issue_transmittal(uow, cmd))

    # --- derivation (P1-I3) -------------------------------------------------------------------
    #
    # Rows, reports and the publication read and write files, so a process that embeds this client
    # must have said which file service to use (``tl_mod_documents.derivation.store.configure``);
    # without one those calls raise ``DerivationNotConfiguredError``.

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
        with self._uow(True) as uow:
            return derivation_views.derived_summaries(
                uow.conn(),
                f"project:{project}",
                state=state,
                document=document,
                schema_code=schema,
                include_void=include_void,
                limit=limit,
            )

    def get_derived_document(self, project: str, ref: str) -> derivation_views.DerivedView:
        with self._uow(True) as uow:
            return derivation_views.derived_view(uow.conn(), f"project:{project}", ref)

    def list_processing_jobs(
        self,
        project: str,
        *,
        state: str | None = None,
        derived: str | None = None,
        limit: int = 200,
    ) -> list[derivation_views.JobView]:
        with self._uow(True) as uow:
            return derivation_views.job_views(
                uow.conn(), f"project:{project}", state=state, derived=derived, limit=limit
            )

    def get_processing_job(self, project: str, job_id: str) -> derivation_views.JobView:
        with self._uow(True) as uow:
            return derivation_views.job_view(uow.conn(), f"project:{project}", job_id)

    def get_derived_rows(
        self,
        project: str,
        ref: str,
        *,
        content_rev: int | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> derivation_views.RowsPage:
        with self._uow(True) as uow:
            return derivation_views.derived_rows(
                uow, f"project:{project}", ref, content_rev=content_rev, offset=offset, limit=limit
            )

    def get_derived_report(
        self, project: str, ref: str, *, content_rev: int | None = None
    ) -> ValidationReport:
        with self._uow(True) as uow:
            return derivation_views.derived_report(
                uow, f"project:{project}", ref, content_rev=content_rev
            )

    def get_derived_diff(
        self,
        project: str,
        ref: str,
        *,
        against: str = "previous_pass",
        content_rev: int | None = None,
    ) -> DerivedDiff:
        with self._uow(True) as uow:
            return derivation_views.derived_diff(
                uow, f"project:{project}", ref, against=against, content_rev=content_rev
            )

    def get_publish_preview(
        self, project: str, ref: str, *, target: str | None = None
    ) -> PublishPlan:
        with self._uow(True) as uow:
            return derivation_views.publish_preview(uow, f"project:{project}", ref, target=target)

    def get_compensation_preview(self, project: str, ref: str) -> CompensationPlan:
        with self._uow(True) as uow:
            return derivation_views.compensation_preview(uow, f"project:{project}", ref)

    def open_derived_document(self, cmd: OpenDerivedDocument) -> CommandResult:
        with self._uow(False) as uow:
            return self.own_writes.note(handle_open_derived_document(uow, cmd))

    def start_extraction(self, cmd: StartExtraction) -> CommandResult:
        with self._uow(False) as uow:
            return self.own_writes.note(handle_start_extraction(uow, cmd))

    def validate_derived(self, cmd: ValidateDerived) -> CommandResult:
        with self._uow(False) as uow:
            return self.own_writes.note(handle_validate_derived(uow, cmd))

    def cancel_job(self, cmd: CancelJob) -> CommandResult:
        with self._uow(False) as uow:
            return self.own_writes.note(handle_cancel_job(uow, cmd))

    def void_derived_document(self, cmd: VoidDerivedDocument) -> CommandResult:
        with self._uow(False) as uow:
            self._controller_gate(uow)  # voiding another person's data is a controller's act
            self._own_command(cmd.actor)
            return self.own_writes.note(handle_void_derived_document(uow, cmd))

    def publish_derived_tags(self, cmd: PublishDerivedTags) -> CommandResult:
        with self._uow(False) as uow:
            self._admin_gate(uow)
            self._own_command(cmd.actor)
            return self.own_writes.note(handle_publish_derived_tags(uow, cmd))

    def publish_derived_documents(self, cmd: PublishDerivedDocuments) -> CommandResult:
        with self._uow(False) as uow:
            self._controller_gate(uow)
            self._own_command(cmd.actor)
            return self.own_writes.note(handle_publish_derived_documents(uow, cmd))

    def compensate_publication(self, cmd: CompensatePublication) -> CommandResult:
        with self._uow(False) as uow:
            self._admin_gate(uow)
            self._own_command(cmd.actor)
            return self.own_writes.note(handle_compensate_publication(uow, cmd))

    def _own_command(self, actor: str) -> None:
        """The gate checked this client's actor, so the command must name the same one."""
        if actor != self.actor:
            raise ForbiddenError("the command names an actor other than the signed-in person")

    # --- schedules and cost (P1-I4) -----------------------------------------------------------

    def list_schedules(self, project: str) -> list[schedule_views.ScheduleView]:
        with self._uow(True) as uow:
            return schedule_views.schedule_views(uow.conn(), f"project:{project}")

    def get_schedule(
        self,
        project: str,
        code: str,
        *,
        limit: int = schedule_views.DEFAULT_SNAPSHOT_PAGE,
        offset: int = 0,
    ) -> schedule_views.ScheduleDetailView:
        with self._uow(True) as uow:
            return schedule_views.schedule_detail(
                uow.conn(), f"project:{project}", code, limit=limit, offset=offset
            )

    def get_schedule_snapshot(
        self, project: str, code: str, number: int
    ) -> schedule_views.SnapshotView:
        with self._uow(True) as uow:
            return schedule_views.snapshot_view(uow.conn(), f"project:{project}", code, number)

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
        with self._uow(True) as uow:
            return schedule_views.activity_page(
                uow.conn(),
                f"project:{project}",
                code,
                snapshot,
                critical=critical,
                status=status,
                search=q,
                limit=limit,
                offset=offset,
            )

    def compare_snapshots(
        self,
        project: str,
        code: str,
        *,
        new: int | None = None,
        old: int | None = None,
        limit: int = schedule_views.DEFAULT_COMPARE_LIMIT,
    ) -> Comparison:
        with self._uow(True) as uow:
            return schedule_views.comparison(
                uow.conn(), f"project:{project}", code, new, old, limit=limit
            )

    def get_look_ahead(
        self, project: str, code: str, *, snapshot: int | None = None, weeks: int = 4
    ) -> LookAhead:
        with self._uow(True) as uow:
            return schedule_views.look_ahead_view(
                uow.conn(), f"project:{project}", code, snapshot, weeks
            )

    def list_orphaned_links(self, project: str, code: str) -> list[OrphanedLink]:
        with self._uow(True) as uow:
            return schedule_views.orphans(uow.conn(), f"project:{project}", code)

    def get_schedule_activity(
        self, project: str, code: str, activity_id: str, *, snapshot: int | None = None
    ) -> schedule_views.ActivityDetail:
        with self._uow(True) as uow:
            return schedule_views.activity_detail(
                uow.conn(), f"project:{project}", code, activity_id, snapshot
            )

    def get_activity_trend(
        self, project: str, code: str, activity_id: str
    ) -> list[schedule_views.TrendPoint]:
        with self._uow(True) as uow:
            return schedule_views.float_trend(uow.conn(), f"project:{project}", code, activity_id)

    def resolve_activity(
        self, project: str, code: str, activity_id: str, *, as_of: str | None = None
    ) -> Resolution:
        with self._uow(True) as uow:
            return schedule_views.resolution(
                uow.conn(),
                f"project:{project}",
                code,
                activity_id,
                schedule_views.as_of_of(as_of),
            )

    def list_activity_links(self, project: str, record_id: str) -> list[ActivityLink]:
        with self._uow(True) as uow:
            return schedule_views.activity_links(uow.conn(), f"project:{project}", record_id)

    def link_activity(self, cmd: LinkActivity) -> CommandResult:
        with self._uow(False) as uow:
            self._own_command(cmd.actor)
            return self.own_writes.note(handle_link_activity(uow, cmd))

    def publish_schedule_snapshot(self, cmd: PublishScheduleSnapshot) -> CommandResult:
        with self._uow(False) as uow:
            self._controller_gate(uow)  # what the project's schedule is: a controller's act
            self._own_command(cmd.actor)
            return self.own_writes.note(handle_publish_schedule_snapshot(uow, cmd))

    def list_cost_snapshots(self, project: str) -> list[cost_views.CostSnapshotView]:
        with self._uow(True) as uow:
            return cost_views.cost_snapshots(uow.conn(), f"project:{project}")

    def list_cost_codes(
        self,
        project: str,
        *,
        parent: str | None = None,
        q: str | None = None,
        limit: int = 1000,
    ) -> list[cost_views.CostCodeView]:
        with self._uow(True) as uow:
            return cost_views.cost_codes(
                uow.conn(), f"project:{project}", parent=parent, search=q, limit=limit
            )

    def get_cost_code(self, project: str, code: str) -> cost_views.CostCodeDetailView:
        with self._uow(True) as uow:
            return cost_views.cost_code_detail(uow.conn(), f"project:{project}", code)

    # --- settings (P0-I8) ---------------------------------------------------------------------

    def list_settings(
        self,
        *,
        project: str | None = None,
        user: str | None = None,
        prefix: str | None = None,
        modified_only: bool = False,
    ) -> list[SettingView]:
        with self._uow(True) as uow:
            return list_views(
                uow.conn(), project=project, user=user, prefix=prefix, modified_only=modified_only
            )

    def get_setting(
        self, key: str, *, project: str | None = None, user: str | None = None
    ) -> SettingView:
        with self._uow(True) as uow:
            return get_view(uow.conn(), key, project=project, user=user)

    def setting_history(self, key: str, *, layer: str | None = None) -> list[SettingChange]:
        with self._uow(True) as uow:
            return settings_history(uow.conn(), key, layer=layer)

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
        """Set a key at a layer; the answer is the key as seen there."""
        with self._uow(False) as uow:
            set_in_force(
                uow,
                key=key,
                layer=layer,
                value=value,
                actor=self.actor,
                source=SOURCE,
                reason=reason,
                accept_risk=accept_risk,
                applies_at=applies_at,
            )
            return view_at(uow.conn(), key, layer)

    def reset_setting(
        self,
        key: str,
        *,
        layer: str,
        reason: str | None = None,
        accept_risk: bool = False,
        applies_at: datetime | None = None,
    ) -> SettingView:
        """Take the layer's own value away; the answer is the key as seen there."""
        with self._uow(False) as uow:
            reset_in_force(
                uow,
                key=key,
                layer=layer,
                actor=self.actor,
                source=SOURCE,
                reason=reason,
                accept_risk=accept_risk,
                applies_at=applies_at,
            )
            return view_at(uow.conn(), key, layer)

    def lock_setting(
        self,
        key: str,
        *,
        locked: bool,
        reason: str,
        bounds: dict[str, Any] | None = None,
    ) -> SettingView:
        """Lock a key for projects (or unlock it) and bound their values; company layer."""
        with self._uow(False) as uow:
            lock_in_force(
                uow,
                key=key,
                locked=locked,
                bounds=bounds,
                actor=self.actor,
                source=SOURCE,
                reason=reason,
            )
            return view_at(uow.conn(), key, "company")

    def revert_setting(
        self,
        key: str,
        *,
        layer: str,
        seq: int,
        reason: str | None = None,
        accept_risk: bool = False,
    ) -> SettingView:
        """Undo the latest change at a layer (a change of its own in the history)."""
        with self._uow(False) as uow:
            revert_in_force(
                uow,
                key=key,
                layer=layer,
                seq=seq,
                actor=self.actor,
                source=SOURCE,
                reason=reason,
                accept_risk=accept_risk,
            )
            return view_at(uow.conn(), key, layer)

    # --- accounts and agent tokens (P1-I0; ADR-0009) ------------------------------------------

    def _admin_gate(self, uow: UnitOfWork) -> None:
        """Only an active account with the admin role may use the calls below (as the API says)."""
        name = self.actor.partition(":")[2]
        found = account_queries.find_account(uow.conn(), username=name)
        # the actor must be the account's own, character for character: `svc:root` and
        # `USER:ROOT` are not `user:root`, whatever the name lookup folds them to
        if (
            found is None
            or account_queries.actor_of(found) != self.actor
            or found.status != "active"
            or "admin" not in found.roles
        ):
            raise ForbiddenError("this action needs the admin role")

    def _controller_gate(self, uow: UnitOfWork) -> None:
        """Only an active admin or document controller may run a controlling act (ADR-0013)."""
        name = self.actor.partition(":")[2]
        found = account_queries.find_account(uow.conn(), username=name)
        if (
            found is None
            or account_queries.actor_of(found) != self.actor
            or found.status != "active"
            or found.kind == "agent"
            or not ({"admin", "document_controller"} & set(found.roles))
        ):
            raise ForbiddenError("this action needs the document_controller or admin role")

    def list_accounts(self) -> list[AccountView]:
        with self._uow(True) as uow:
            self._admin_gate(uow)
            return account_queries.list_accounts(uow.conn())

    def get_account(self, account_id: str) -> AccountView:
        with self._uow(True) as uow:
            self._admin_gate(uow)
            return account_queries.get_account(uow.conn(), account_id)

    def create_account(
        self,
        username: str,
        display_name: str,
        *,
        kind: AccountKind = "person",
        roles: Sequence[str] = ("user",),
        password: str | None = None,
    ) -> AccountView:
        with self._uow(True) as uow:
            self._admin_gate(uow)
        # the policy and the slow hash run before the write transaction opens (one global writer)
        prepared = None if password is None else prepare_password(password, username=username)
        with self._uow(False) as uow:
            self._admin_gate(uow)
            return account_services.create_account(
                uow,
                username=username,
                display_name=display_name,
                kind=kind,
                roles=list(roles),
                password=prepared,
                by=self.actor,
            )

    def set_roles(
        self,
        account_id: str,
        roles: Sequence[str],
        *,
        reason: str | None = None,
        expected_roles: Sequence[str] | None = None,
    ) -> AccountView:
        with self._uow(False) as uow:
            self._admin_gate(uow)
            return account_services.set_roles(
                uow,
                account_id=account_id,
                roles=list(roles),
                by=self.actor,
                reason=reason,
                expected_roles=expected_roles,
            )

    def disable_account(self, account_id: str, *, reason: str | None = None) -> AccountView:
        with self._uow(False) as uow:
            self._admin_gate(uow)
            return account_services.disable(
                uow, account_id=account_id, by=self.actor, reason=reason
            )

    def enable_account(self, account_id: str, *, reason: str | None = None) -> AccountView:
        with self._uow(False) as uow:
            self._admin_gate(uow)
            return account_services.enable(uow, account_id=account_id, by=self.actor, reason=reason)

    def reset_password(self, account_id: str, new_password: str) -> AccountView:
        with self._uow(True) as uow:
            self._admin_gate(uow)
            account = account_queries.get_account(uow.conn(), account_id)
        prepared = prepare_password(new_password, username=account.username)
        with self._uow(False) as uow:
            self._admin_gate(uow)
            account_services.change_password(
                uow, account_id=account_id, new_password=prepared, by=self.actor
            )
            return account_queries.get_account(uow.conn(), account_id)

    def list_agent_tokens(
        self, account_id: str | None = None, *, include_revoked: bool = True
    ) -> list[AgentTokenView]:
        with self._uow(True) as uow:
            self._admin_gate(uow)
            return account_queries.list_agent_tokens(
                uow.conn(), account_id=account_id, include_revoked=include_revoked
            )

    def issue_agent_token(
        self, account_id: str, label: str, *, expires_in_days: int | None = 90
    ) -> tuple[AgentTokenView, str]:
        expires = None if expires_in_days is None else utcnow() + timedelta(days=expires_in_days)
        with self._uow(False) as uow:
            self._admin_gate(uow)
            return account_services.issue_agent_token(
                uow, account_id=account_id, label=label, expires_at=expires, by=self.actor
            )

    def revoke_agent_token(self, token_id: str, *, reason: str | None = None) -> AgentTokenView:
        with self._uow(False) as uow:
            self._admin_gate(uow)
            return account_services.revoke_agent_token(
                uow, token_id=token_id, by=self.actor, reason=reason
            )
