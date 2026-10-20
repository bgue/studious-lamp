"""Helpers of the integration CLI tests (P1-I7 WS-A): a ledger, a runner, and seeding through the
real services. Provided and final; the tickets do not change it."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from tl_adapters.db import DbTarget, make_uow_factory, open_uow
from tl_adapters.queue import job_queue_for
from tl_api.commands import command_runner
from tl_cli.main import app
from tl_core.integration.apps import RegisterIntegrationApp, handle_register_app
from tl_core.integration.contract import (
    EnrichmentResult,
    EnrichmentSubject,
    ProposedValue,
)
from tl_core.integration.inbound.gate import accept_delivery, endpoint_view
from tl_core.integration.inbound.store import body_key, put_body
from tl_core.integration.inbound.worker import InboundMapJobKind
from tl_core.jobs.runner import JobRunner
from tl_core.services.commands import CreateRecord
from tl_core.services.feed import PostToFeed, handle_post
from tl_core.services.records import handle_create_record
from tl_core.util import new_ulid, utcnow
from typer.testing import CliRunner
from typer.testing import Result as RunResult

runner = CliRunner()
P = "P123"
SCOPE = f"project:{P}"
ADMIN = "user:dev"


def run(env: dict[str, str], *args: str, input: str | None = None) -> RunResult:
    return runner.invoke(app, list(args), env=env, input=input)


def ok(result: RunResult) -> RunResult:
    assert result.exit_code == 0, result.output + str(result.exception)
    assert result.exception is None
    return result


def refused(result: RunResult, wanted: str) -> None:
    """Exit 1, `error: ...` on stderr naming ``wanted``, and not a crash."""
    assert result.exit_code == 1, result.output
    assert not isinstance(result.exception, (NotImplementedError, AttributeError, TypeError))
    assert "error:" in result.stderr and wanted in result.stderr, result.stderr


def lines(result: RunResult) -> list[str]:
    return result.stdout.splitlines()


def fields(result: RunResult) -> dict[str, str]:
    """``name value`` lines as a dict (the first word is the name; the last line wins)."""
    found: dict[str, str] = {}
    for text_line in result.stdout.splitlines():
        name, _, value = text_line.partition(" ")
        found[name] = value
    return found


def write_json(root: Path, name: str, data: Any) -> str:
    path = root / name
    path.write_text(json.dumps(data) if not isinstance(data, str) else data)
    return str(path)


def new_env(new_db: Callable[[], DbTarget], root: Path) -> dict[str, str]:
    values = {
        "TL_DB": str(new_db()),
        "TL_ENV": "dev",
        "TL_OBJECT_ROOT": str(root / "objects"),
        "TL_WEBHOOK_ALLOWLIST": "",
    }
    ok(run(values, "init"))
    return values


def sql(env: dict[str, str], query: str, **params: Any) -> list[dict[str, Any]]:
    with open_uow(env["TL_DB"], readonly=True) as uow:
        return [dict(r) for r in uow.conn().execute(text(query), params).mappings()]


def factory(env: dict[str, str]) -> Any:
    def open_one(readonly: bool = False) -> AbstractContextManager[Any]:
        return open_uow(env["TL_DB"], readonly=readonly)

    return open_one


def make_record(env: dict[str, str], key: str, title: str = "A record") -> str:
    with open_uow(env["TL_DB"]) as uow:
        made = handle_create_record(
            uow,
            CreateRecord(
                actor=ADMIN, source="test", scope=SCOPE, record_type="core.Record", title=title,
                key=key,
            ),
        )  # fmt: skip
    return made.stream_id


def post(env: dict[str, str], body: str) -> None:
    with open_uow(env["TL_DB"]) as uow:
        handle_post(uow, PostToFeed(actor=ADMIN, source="test", scope=SCOPE, body=body))


def register_app(env: dict[str, str], name: str = "erp") -> None:
    with open_uow(env["TL_DB"]) as uow:
        handle_register_app(
            uow,
            RegisterIntegrationApp(actor=ADMIN, source="test", scope=SCOPE, name=name, label=name),
        )


# --- inbound: a delivery without HTTP ---------------------------------------------------------


def make_endpoint(
    env: dict[str, str], path: str, mapping: str, allow: tuple[str, ...] = ("PostToFeed",)
) -> str:
    """An endpoint made through the service, switched on and live; its id. (No CLI is used, so a
    test of one command does not depend on another command being written.)"""
    from tl_core.integration.inbound.service import (
        CreateInboundEndpoint,
        ReviseInboundEndpoint,
        SetInboundEndpointEnabled,
        create_endpoint,
        handle_revise_endpoint,
        handle_set_endpoint_enabled,
    )

    app_name, _, name = path.partition("/")
    with open_uow(env["TL_DB"]) as uow:
        made = create_endpoint(
            uow,
            CreateInboundEndpoint(
                actor=ADMIN, source="test", scope=SCOPE, app=app_name, name=name, mapping=mapping,
                allowed_commands=list(allow),
            ),
        )  # fmt: skip
    with open_uow(env["TL_DB"]) as uow:
        handle_revise_endpoint(
            uow,
            ReviseInboundEndpoint(
                actor=ADMIN, source="test", scope=SCOPE, endpoint_id=made.endpoint_id,
                changes={"dry_run": False}, reason="live",
            ),
        )  # fmt: skip
        handle_set_endpoint_enabled(
            uow,
            SetInboundEndpointEnabled(
                actor=ADMIN, source="test", scope=SCOPE, endpoint_id=made.endpoint_id, enabled=True
            ),
        )
    return made.endpoint_id


def revise_mapping(env: dict[str, str], endpoint_id: str, mapping: str) -> None:
    from tl_core.integration.inbound.service import ReviseInboundEndpoint, handle_revise_endpoint

    with open_uow(env["TL_DB"]) as uow:
        handle_revise_endpoint(
            uow,
            ReviseInboundEndpoint(
                actor=ADMIN, source="test", scope=SCOPE, endpoint_id=endpoint_id,
                changes={"mapping": mapping}, reason="fix",
            ),
        )  # fmt: skip


def deliver(env: dict[str, str], path: str, payload: Any) -> str:
    """Store ``payload`` and accept it as the route does (no signature); the delivery id."""
    from tl_adapters.objectstore import make_object_store

    app_name, _, name = path.partition("/")
    row = sql(
        env, "SELECT endpoint_id FROM cur_inbound_endpoint WHERE app = :a AND name = :n",
        a=app_name, n=name,
    )[0]  # fmt: skip
    store = make_object_store(env)
    delivery_id = new_ulid()
    body = json.dumps(payload).encode()
    key = body_key(row["endpoint_id"], delivery_id)
    digest = put_body(store, key, body)
    with open_uow(env["TL_DB"]) as uow:
        view = endpoint_view(uow.conn(), row["endpoint_id"])
        assert view is not None
        accept_delivery(
            uow, view, message_id=new_ulid(), delivery_id=delivery_id, object_key=key,
            payload_sha256=digest, payload_size=len(body), now=utcnow(),
        )  # fmt: skip
    return delivery_id


def work_inbound(env: dict[str, str]) -> None:
    """Run the ``inbound.map`` jobs that are waiting."""
    from tl_adapters.objectstore import make_object_store

    opened = make_uow_factory(env["TL_DB"])
    try:
        with opened(readonly=True) as uow:
            queue = job_queue_for(uow.conn())
        kind = InboundMapJobKind(command_runner(), make_object_store(env))
        JobRunner(opened, queue, [kind], worker_id="test", retry_base_s=0.0).run_until_idle()
    finally:
        opened.dispose()


# --- enrichment: a plugin of the test's own ----------------------------------------------------


class LabelEnricher:
    """Proposes the label ``alpha`` (confidence 0.95) for any record with a title."""

    name = "fake"
    version = "1.0.0"
    model_ref: str | None = None

    def accepts(self, subject: EnrichmentSubject) -> bool:
        return bool(subject.title.strip())

    def enrich(self, subject: EnrichmentSubject) -> EnrichmentResult:
        return EnrichmentResult(
            enricher=self.name,
            enricher_version=self.version,
            status="ok",
            values=[ProposedValue(property="label", value="alpha", confidence=0.95)],
        )


@pytest.fixture
def plugins() -> Iterator[None]:
    from tl_core.integration.enrichers.registry import use_enrichers

    with use_enrichers({"fake": LabelEnricher}):
        yield
