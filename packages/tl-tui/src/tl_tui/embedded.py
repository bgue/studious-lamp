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
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from tl_api.auth import AGENT_MUST_PROPOSE
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
from tl_schema.forms import ConformanceReport, FormMetadata

from tl_tui.client import RelationInfo
from tl_tui.live import ChangeFeed, EmbeddedFeed, OwnWrites

#: The actor of settings changes when none is given (the dev person; the header shows the same).
DEFAULT_ACTOR = "user:dev"
#: The ``source`` recorded on settings this client changes.
SOURCE = "tui"

# A callable that opens a unit of work: `factory(readonly)` returns a context manager yielding it.
UowFactory = Callable[[bool], AbstractContextManager[UnitOfWork]]


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

    def workflow_status(self, record_id: str, *, roles: Sequence[str] = ()) -> WorkflowStatus:
        with self._uow(True) as uow:
            return workflow_status(uow, record_id, roles=tuple(roles))

    def transition(self, cmd: TransitionWorkflow) -> CommandResult:
        with self._uow(False) as uow:
            return self.own_writes.note(handle_transition_workflow(uow, cmd))

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
