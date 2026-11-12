"""The server entry point: ``uv run python -m tl_api`` (or ``just serve``).

    --db TARGET       SQLite ledger file or postgresql:// URL (default TL_DB or ./dev/data/tl.db;
                      create it with `tl init`). Prefer TL_DB for a URL: a command line is visible
                      in the process list and the URL carries the password.
    --tokens PATH     dev token file (default TL_TOKENS or ./dev/data/tokens.json)
    --host / --port   bind address (default 127.0.0.1:8765)
    --insecure-dev    allow a non-loopback bind; every request logs a warning (ADR-0005)

A non-loopback bind is also allowed when TL_ENV names a deployment (not dev, test, ci or demo): then
TL_OBJECT_SECRET is required, the dev token file is ignored and TLS is the proxy's job.

Object storage comes from the environment like the CLI (`TL_OBJECT_STORE`, `TL_OBJECT_ROOT`,
`TL_OBJECT_SECRET` or `TL_ENV=dev`). Without it the server starts and the file routes answer 503.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from tl_adapters.db import DbTarget, as_target, display_target
from tl_core.auth.env import prod_like
from tl_core.files.service import FileService
from tl_core.files.types import ObjectStore

from tl_api.backend import Backend
from tl_api.settings import DEFAULT_TOKENS, ApiSettings, check_bind, is_loopback

log = logging.getLogger("tl_api")


def _database(text: str) -> DbTarget:
    """``--db`` as a target; a bad value is reported without repeating it (a URL has a password)."""
    try:
        return as_target(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from None


def parse_args(argv: Sequence[str] | None = None) -> ApiSettings:
    base = ApiSettings.from_env()
    parser = argparse.ArgumentParser(prog="tl-api", description="Throughline dev API server.")
    parser.add_argument("--db", type=_database, default=base.db_path)
    parser.add_argument("--tokens", type=Path, default=base.tokens_path)
    parser.add_argument("--host", default=base.host)
    parser.add_argument("--port", type=int, default=base.port)
    parser.add_argument("--insecure-dev", action="store_true")
    ns = parser.parse_args(argv)
    return replace(
        base,
        db_path=ns.db,
        tokens_path=ns.tokens,
        host=ns.host,
        port=ns.port,
        insecure_dev=ns.insecure_dev,
    )


def file_service_from_env() -> FileService | None:
    """The upload service on the configured store, or ``None`` (with a warning) if unconfigured."""
    from tl_adapters.objectstore import make_object_store, object_secret

    try:
        return FileService(make_object_store(), secret=object_secret())
    except ValueError as exc:
        log.warning("file routes disabled: %s", exc)
        return None


def object_store_from_env() -> ObjectStore | None:
    """The configured object store (bodies of object-backed extension records), or ``None``."""
    from tl_adapters.objectstore import make_object_store

    try:
        return make_object_store()
    except ValueError as exc:
        log.warning("extension record bodies disabled: %s", exc)
        return None


def mark_server_started(backend: Backend) -> None:
    """Record that the settings that need a restart (``effect: restart``) are now in force.

    Called only once the server is listening (see :func:`started_server`): an app that failed to
    build or a port that could not be bound has restarted nothing.
    """
    from tl_core.settings.effects import mark_applied

    with backend(False) as uow:
        mark_applied(uow.conn(), ["restart"], applied_by="server")


def started_server(app: Any, settings: ApiSettings, on_started: Callable[[], None]) -> Any:
    """A uvicorn server for ``app`` that calls ``on_started`` once its sockets are bound.

    uvicorn runs the app's lifespan startup before it binds, so the app cannot tell when the server
    is really up; this subclass calls ``on_started`` after uvicorn's own startup succeeded
    (``started`` is true). A bind error exits before that and nothing is marked.
    """
    import uvicorn

    class StartedServer(uvicorn.Server):
        async def startup(self, sockets: Any = None) -> None:
            await super().startup(sockets=sockets)
            if self.started:
                on_started()

    config = uvicorn.Config(app, host=settings.host, port=settings.port, log_level="info")
    return StartedServer(config)


def check_server_mode(settings: ApiSettings, env: Mapping[str, str] | None = None) -> str | None:
    """Start-up checks for a prod-like, non-loopback server (ADR-0009 section 9).

    Returns the refusal text, or ``None`` to go on. The dev token file is not read: a value given
    for it is ignored with one log line. ``TL_OBJECT_SECRET`` must be set (the dev secret is
    public). One line says whether a trusted proxy header is configured.
    """
    source = os.environ if env is None else env
    if source.get("TL_TOKENS") or str(settings.tokens_path) != DEFAULT_TOKENS:
        log.info("TL_ENV is %s: the dev token file is ignored", source.get("TL_ENV", "").strip())
    if not source.get("TL_OBJECT_SECRET"):
        return (
            "TL_OBJECT_SECRET is not set: set it to a long random value "
            "(the dev secret is public and only for TL_ENV=dev)"
        )
    proxy = "yes" if settings.trusted_proxy_header else "no"
    log.info("serving on %s:%s behind TLS proxy: %s", settings.host, settings.port, proxy)
    return None


def main(argv: Sequence[str] | None = None) -> int:
    from tl_core.offline import NodeKindNotBuiltError, require_node_built

    try:
        require_node_built()  # before any ledger is opened
    except (NodeKindNotBuiltError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    try:
        settings = parse_args(argv)
    except ValueError as exc:  # TL_DB holds a value that is not a database target
        print(f"error: {exc}", file=sys.stderr)
        return 2
    try:
        check_bind(settings.host, insecure_dev=settings.insecure_dev)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    from tl_adapters.backend import BackendUnavailableError, ledger_exists

    try:
        found = ledger_exists(settings.db_path)
    except (BackendUnavailableError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not found:
        print(
            f"error: no ledger at {display_target(settings.db_path)}; run `uv run tl init` first",
            file=sys.stderr,
        )
        return 2

    from tl_api.tokens import TokenStore

    logging.basicConfig(level=logging.INFO)
    server_mode = prod_like() and not is_loopback(settings.host)
    if server_mode:
        refusal = check_server_mode(settings)
        if refusal is not None:
            print(f"error: {refusal}", file=sys.stderr)
            return 2
    else:
        try:
            TokenStore(settings.tokens_path).check()
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    from tl_api.app import create_app
    from tl_api.backend import open_backend

    if settings.insecure_dev:
        log.warning("--insecure-dev: bound to %s with no real authentication", settings.host)
    try:
        backend = open_backend(settings.db_path)
    except (BackendUnavailableError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    try:
        from tl_api.startup import StartupRefused, check_demo_account

        try:
            check_demo_account(backend, host=settings.host)
        except StartupRefused as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        app = create_app(
            backend,
            settings=settings,
            files_service=file_service_from_env(),
            object_store=object_store_from_env(),
        )
        server = started_server(app, settings, lambda: mark_server_started(backend))
        server.run()
        if not server.started:
            # uvicorn.run exits 3 here; run() alone returns when the app's startup failed
            print("error: the server did not start (see the log above)", file=sys.stderr)
            return 3
    finally:
        backend.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
