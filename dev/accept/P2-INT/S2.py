"""P2-INT-S2 acceptance: demo clauses 1, 4, 5, 6, 7 through the API on one scratch database.

``--keep PATH`` leaves the SQLite database at PATH. Postgres runs as well when ``TL_PG_URL`` is set.
One PASS per check; the first failure exits 1.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import text
from tl_adapters.backend import open_backend
from tl_adapters.db import DbTarget, create_schema
from tl_api.app import create_app
from tl_api.settings import ApiSettings
from tl_api.tokens import TokenStore, add_token
from tl_core.intent import Intent
from tl_core.services import proposals
from tl_core.services.commands import CreateRecord

SCOPE = "project:ACC"
AGENT = "agent:accept"
ALICE = "user:alice"
BOB = "user:bob"


def passed(label: str, ok: bool) -> None:
    print(f"{'PASS' if ok else 'FAIL'} {label}")
    if not ok:
        raise SystemExit(1)


def create(client: TestClient, key: str, **extra: Any) -> Any:
    body = {"scope": SCOPE, "record_type": "core.Record", "title": "T " + key, "key": key}
    return client.post("/commands/CreateRecord", json={**body, **extra})


def intents(backend: Any, stream: str) -> list[str | None]:
    with backend(True) as uow:
        rows = uow.conn().execute(
            text("SELECT intent FROM events WHERE stream_id = :s ORDER BY stream_version"),
            {"s": stream},
        ).all()  # fmt: skip
    return [r[0] for r in rows]


def run(name: str, target: DbTarget, root: Path) -> None:
    create_schema(target)
    backend: Any = open_backend(target)
    tokens_path = root / f"{name}-tokens.json"
    tokens = {ALICE: add_token(tokens_path, ALICE), BOB: add_token(tokens_path, BOB)}
    settings = ApiSettings(db_path=root / f"{name}.db", tokens_path=tokens_path)
    app = create_app(backend, settings=settings, tokens=TokenStore(tokens_path))
    alice = TestClient(app, raise_server_exceptions=False)
    alice.headers.update({"Authorization": f"Bearer {tokens[ALICE]}"})
    try:
        base = create(alice, "ACC-1").json()["stream_id"]
        # 1. a command with an intent stores its canonical JSON; without, NULL
        toward = {"target": "ACC-1", "condition": "cured"}
        made = create(alice, "ACC-2", intent={"why": "pour on Monday", "toward": toward})
        rid = made.json()["stream_id"]
        stored = intents(backend, rid)[0]
        ids_only = stored is not None and json.loads(stored)["toward"]["target"] == base
        passed(f"{name} 1 intent column holds canonical JSON, the key stored as an id",
               ids_only and "ACC-1" not in str(stored))  # fmt: skip
        passed(f"{name} 1 no intent leaves NULL", intents(backend, base) == [None])
        # 4. a bad intent refuses the whole command; an unknown reference has one code and text
        count = len(alice.get("/events").json()["events"])
        long = create(alice, "ACC-3", intent={"why": "x" * 501})
        bad_name = create(alice, "ACC-3", intent={"next": [{"command": "NoSuchCommand"}]})
        unknown = create(alice, "ACC-3", intent={"toward": {"target": "NOPE", "condition": "x"}})
        codes = {long.json()["error"], bad_name.json()["error"]}
        passed(f"{name} 4 bad intents give intent_invalid", codes == {"intent_invalid"})
        fixed = unknown.json()
        passed(f"{name} 4 unknown reference gives intent_reference_unknown, fixed text",
               (fixed["error"], fixed["message"])
               == ("intent_reference_unknown", "intent reference not found"))  # fmt: skip
        after = len(alice.get("/events").json()["events"])
        passed(f"{name} 4 nothing was appended", after == count)
        # 5. {} and all-null store NULL
        one = create(alice, "ACC-4", intent={}).json()["stream_id"]
        two = create(alice, "ACC-5", intent={"why": None, "next": []}).json()["stream_id"]
        empties = intents(backend, one) + intents(backend, two)
        passed(f"{name} 5 empty intents store NULL", empties == [None, None])
        # 6. an agent proposes with an intent; accepting carries it; actor = the accepting person
        command = CreateRecord(
            actor=AGENT, source="mcp:accept", scope=SCOPE, record_type="core.Record",
            title="Agent NCR", key="ACC-6",
            intent=Intent.model_validate({"why": "agent saw a defect"}),
        )  # fmt: skip
        proposal = proposals.submit(
            backend, tool="create_record", agent=AGENT, command=command, summary="NCR"
        )
        with backend(True) as uow:
            payload = (
                uow.conn()
                .execute(
                    text("SELECT payload FROM events WHERE stream_id = :s"),
                    {"s": proposal.proposal_id},
                )
                .scalar_one()
            )
        no_key = "intent" not in json.loads(payload)["command"]
        passed(f"{name} 6 Proposal.Created payload has no intent key", no_key)
        created = intents(backend, proposal.proposal_id)[0]
        passed(f"{name} 6 Proposal.Created column has it", created is not None)
        done = alice.post(f"/proposals/{proposal.proposal_id}/accept").json()
        first = alice.get(f"/records/{done['result_stream_id']}/history").json()[0]
        same = first["intent"] == {**json.loads(created or "null"), "next": [], "toward": None,
                                   "goal_ref": None}  # fmt: skip
        who = (first["actor"], first["source"], done["decided_by"])
        passed(f"{name} 6 accepted event: same intent, actor the person, agent named",
               same and who == (ALICE, "mcp:accept", ALICE))  # fmt: skip
        # 7. reads return intent
        history = alice.get(f"/records/{rid}/history").json()[0]["intent"]
        listed = alice.get("/events").json()["events"]
        in_list = any(e["stream_id"] == rid and e["intent"] == history for e in listed)
        passed(f"{name} 7 history and events return intent",
               history["why"] == "pour on Monday" and in_list)  # fmt: skip
    finally:
        alice.close()
        backend.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep", type=Path, default=None)
    args = parser.parse_args()
    os.environ.setdefault("TL_ENV", "dev")  # the dev token file is honoured here only
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        keep = args.keep
        if keep is not None:
            keep.parent.mkdir(parents=True, exist_ok=True)
            keep.unlink(missing_ok=True)
        run("sqlite", keep or base / "a.db", base)
        url = os.environ.get("TL_PG_URL")
        if url:
            from tl_adapters.postgres import admin

            schema = "tl_s2_" + uuid.uuid4().hex[:12]
            admin.create_schema_namespace(url, schema)
            try:
                run("postgres", admin.schema_url(url, schema), base)
            finally:
                admin.drop_schema_namespace(url, schema)
        else:
            print("SKIP postgres (TL_PG_URL not set)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
