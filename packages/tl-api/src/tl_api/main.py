"""The server entry point: ``uv run python -m tl_api`` (or ``just serve``).

    --db PATH         SQLite ledger (default TL_DB or ./dev/data/tl.db; create it with `tl init`)
    --tokens PATH     dev token file (default TL_TOKENS or ./dev/data/tokens.json)
    --host / --port   bind address (default 127.0.0.1:8765)
    --insecure-dev    allow a non-loopback bind; every request logs a warning (ADR-0005)

Object storage comes from the environment like the CLI (`TL_OBJECT_STORE`, `TL_OBJECT_ROOT`,
`TL_OBJECT_SECRET` or `TL_ENV=dev`). Without it the server starts and the file routes answer 503.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from tl_core.files.service import FileService

from tl_api.settings import ApiSettings, check_bind

log = logging.getLogger("tl_api")


def parse_args(argv: Sequence[str] | None = None) -> ApiSettings:
    base = ApiSettings.from_env()
    parser = argparse.ArgumentParser(prog="tl-api", description="Throughline dev API server.")
    parser.add_argument("--db", type=Path, default=base.db_path)
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


def main(argv: Sequence[str] | None = None) -> int:
    settings = parse_args(argv)
    try:
        check_bind(settings.host, insecure_dev=settings.insecure_dev)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not settings.db_path.exists():
        print(
            f"error: no ledger at {settings.db_path}; run `uv run tl init` first", file=sys.stderr
        )
        return 2

    import uvicorn

    from tl_api.app import create_app
    from tl_api.backend import open_sqlite_backend

    logging.basicConfig(level=logging.INFO)
    if settings.insecure_dev:
        log.warning("--insecure-dev: bound to %s with no real authentication", settings.host)
    backend = open_sqlite_backend(settings.db_path)
    try:
        app = create_app(backend, settings=settings, files_service=file_service_from_env())
        uvicorn.run(app, host=settings.host, port=settings.port, log_level="info")
    finally:
        backend.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
