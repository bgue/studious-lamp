"""Acceptance script for P2-W0 OC-T1: GET /record-types and record_types() on the clients.

Runs on SQLite with a temp ledger. Prints one ``PASS <check>`` line per check; exits 0 when every
check passes, 1 on the first failure. Every expectation is computed from the generated offline table
(``tl_schema.generated.offline_classes``) or stated as a fact of the offline-classes spec (5.6).
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Any

os.environ.setdefault("TL_ENV", "test")  # dev tokens and the dev ledger rule

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages" / "tl-tui" / "tests"))  # the fake client and its helpers

from fastapi.testclient import TestClient  # noqa: E402
from tl_adapters.backend import open_backend  # noqa: E402
from tl_adapters.db import create_schema  # noqa: E402
from tl_api.app import create_app  # noqa: E402
from tl_api.settings import ApiSettings  # noqa: E402
from tl_api.tokens import TokenStore  # noqa: E402
from tl_core.auth import accounts, sessions  # noqa: E402
from tl_core.auth.password import prepare_password  # noqa: E402
from tl_core.offline import record_type_rows  # noqa: E402
from tl_schema.generated.offline_classes import OFFLINE_CLASSES  # noqa: E402

PASSWORD = "correct horse battery"
FIELDS = {"record_type", "label", "module", "offline", "drafting_commands"}


def passed(check: str) -> None:
    print(f"PASS {check}")


def by_type(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {row["record_type"]: row for row in rows}


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        db = work / "api.db"
        create_schema(db)
        backend = open_backend(db)
        tokens = work / "tokens.json"
        app = create_app(
            backend,
            settings=ApiSettings(db_path=db, tokens_path=tokens),
            tokens=TokenStore(tokens),
        )

        with backend() as uow:
            accounts.create_account(
                uow,
                username="pat",
                display_name="Pat",
                kind="person",
                roles=["user"],
                password=prepare_password(PASSWORD, username="pat"),
                by="svc:accept",
            )
        _, token = sessions.sign_in(backend, username="pat", password=PASSWORD)

        signed_in = TestClient(app, raise_server_exceptions=False)
        signed_in.headers.update({"Authorization": f"Bearer {token}"})
        anonymous = TestClient(app, raise_server_exceptions=False)

        response = signed_in.get("/record-types")
        assert response.status_code == 200, response.text
        rows = response.json()
        table = by_type(rows)
        missing = sorted(set(OFFLINE_CLASSES) - set(table))
        assert not missing, f"record types without a row: {missing}"
        assert len(rows) == len(OFFLINE_CLASSES), (len(rows), len(OFFLINE_CLASSES))
        passed("(a) GET /record-types answers 200 with a row per OFFLINE_CLASSES key")

        tag = table["engineering.Tag"]
        assert tag["offline"] == "full", tag
        assert tag["module"] == "engineering", tag
        assert tag["drafting_commands"] == [], tag
        passed("(b) engineering.Tag is full, module engineering, drafting_commands []")

        document = table["documents.Document"]
        assert document["offline"] == "draft_only", document
        assert document["drafting_commands"], document
        passed("(c) documents.Document is draft_only with drafting_commands not empty")

        cycle = table["documents.ReviewCycle"]
        assert cycle["offline"] == "none", cycle
        passed("(d) documents.ReviewCycle is none")

        extra = [row for row in rows if set(row) != FIELDS]
        assert not extra, f"rows with other fields: {extra[:2]}"
        passed("(e) every row has exactly the five fields")

        expected = [r.model_dump() for r in record_type_rows()]
        assert rows == expected, "route differs from the builder"
        passed("(f) the response equals [r.model_dump() for r in record_type_rows()]")

        anon = anonymous.get("/record-types")
        assert anon.status_code in (401, 403), anon.status_code
        passed(f"(g) an unauthenticated call is refused ({anon.status_code})")

    print("ALL PASS")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as exc:
        print(f"FAIL {exc!r}")
        raise SystemExit(1) from exc
