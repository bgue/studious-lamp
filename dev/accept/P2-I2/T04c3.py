"""Acceptance for P2-I2-T04c3: the three constraint routes check ``core.constraint.view`` before any
read, as the CLI does. Three readers against the three routes (list, groups, detail): a reader
with no role, a reader whose role lacks the word, and a reader with the word. Expected: 403, 403,
200 for each route. SQLite temp ledger, in-process TestClient, no network.

The seed is the T04a world (``t04a_checks``). The no-word readers are simulated: the shipped role
table grants ``read`` to every role, and a dev token always carries the ``user`` role, so
``holds_word`` is stubbed to False for ``user:nora`` (a dev token, "no role") and ``user:vic``
(a ``user`` account, "role without word"). ``uma`` is the reader with the word.

Prints one ``PASS <check>`` line per check, then ``T04c3 ok``. Exits 1 on the first failure.

Run: ``uv run python dev/accept/P2-I2/T04c3.py``.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Any

os.environ["TL_ENV"] = "test"  # dev tokens (the "no role" reader) are for dev, test and ci only
sys.path.insert(0, str(Path(__file__).parents[3] / "packages/tl-modules/awp/tests"))
sys.path.insert(0, str(Path(__file__).parent))

import t04a_checks as t  # noqa: E402
from awp_world import PASSWORD  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from tl_adapters.backend import open_backend  # noqa: E402
from tl_adapters.db import as_target, open_uow  # noqa: E402
from tl_api.app import create_app  # noqa: E402
from tl_api.settings import ApiSettings  # noqa: E402
from tl_api.tokens import TokenStore, add_token  # noqa: E402
from tl_core.auth import module_roles, sessions  # noqa: E402

PROJECT = "P123"
CBASE = f"/projects/{PROJECT}/constraints"
NO_WORD = {"user:nora", "user:vic"}


def ok(name: str, cond: bool = True) -> None:
    if not cond:
        print(f"FAIL {name}", flush=True)
        sys.exit(1)
    print(f"PASS {name}", flush=True)


def first_key(db: Path, subject_id: str) -> str:
    with open_uow(as_target(str(db)), readonly=True) as uow:
        return str(
            uow.conn()
            .execute(
                text(
                    "SELECT r.key FROM cur_core_constraint c JOIN cur_core_record r "
                    "ON r.id = c.id WHERE c.subject_id = :s"
                ),
                {"s": subject_id},
            )
            .scalar_one()
        )


def main() -> None:
    work = Path(tempfile.mkdtemp(prefix="t04c3-"))
    db = work / "t04c3.db"
    w, ctx = t.build(db)
    ids = t.seed(w, ctx)
    t.classed(w, {ids["i3"], ids["cwp"]})
    w.person("vic", ("user",))
    visible_key = first_key(db, ids["i1"])

    tokens = work / "tokens.json"
    backend = open_backend(db)
    app = create_app(
        backend,
        settings=ApiSettings(db_path=db, tokens_path=tokens),
        tokens=TokenStore(tokens),
    )

    real_holds = module_roles.holds_word

    def holds(conn: Any, holder: Any, **kwargs: Any) -> bool:
        if holder.actor in NO_WORD:
            return False
        return real_holds(conn, holder, **kwargs)

    module_roles.holds_word = holds  # type: ignore[assignment]

    def client_with(token: str) -> TestClient:
        client = TestClient(app, raise_server_exceptions=False)
        client.headers.update({"Authorization": f"Bearer {token}"})
        return client

    def signed_in(who: str) -> TestClient:
        _, token = sessions.sign_in(backend, username=who, password=PASSWORD)
        return client_with(token)

    readers = {
        "no role": client_with(add_token(tokens, "user:nora")),
        "role without word": signed_in("vic"),
        "role with word": signed_in("uma"),
    }
    routes = {
        "list": (CBASE, {}),
        "groups": (f"{CBASE}/groups", {"by": "owner"}),
        "detail": (f"{CBASE}/{visible_key}", {}),
    }
    expected = {"no role": 403, "role without word": 403, "role with word": 200}
    for reader, client in readers.items():
        for route, (path, params) in routes.items():
            status = client.get(path, params=params).status_code
            ok(
                f"{reader}, {route}: {status} (expected {expected[reader]})",
                status == expected[reader],
            )
    ok(
        "role with word, detail: the visible constraint is served by key",
        readers["role with word"].get(f"{CBASE}/{visible_key}").json()["key"] == visible_key,
    )
    module_roles.holds_word = real_holds  # type: ignore[assignment]
    print("T04c3 ok", flush=True)


if __name__ == "__main__":
    main()
