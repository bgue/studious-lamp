"""Driver for dev/demos/P2-W0.sh: the clauses of the demo that are not a `tl` command.

It opens the ledger named by TL_DB (a SQLite file or a postgresql:// URL, read with `as_target`)
and runs the API in process with the test client, the way dev/accept/P2-W0/RM-S2.py does. Each mode
checks one exit clause and prints one ``PASS clause N: <what was checked>`` line per check; a miss
prints ``FAIL <what>`` and exits 1. The people are the ones the script seeded (documented dev
passwords, as in the P1 demos).

Modes (first argument):

* ``clause3 DOC_ID``: dora, a viewer of documents on P2, is refused RegisterDocument on P2 (403)
  and is offered no action on the P2 document DOC_ID (``GET /records/{id}/actions``).
* ``clause4``: ``GET /events`` as alice shows no module-role grant; as ada it shows them.
* ``clause5 KEY``: an agent's ``propose_import_documents`` proposal publishing the valid derived
  document KEY (P1): bob's and alice's accepts are 403 ``proposal_access`` and the proposal stays
  pending; dora's accept (a document controller) runs and the proposal is accepted.
* ``clause6``: a stand-in module with ``company_roles`` (its ``awp.cwp.release`` word) takes a
  ``company`` grant; the same grant on ``documents`` is refused ``no_company_roles``.
* ``clause7``: ``OFFLINE_CLASSES`` has one entry per record type; the capture rules of section 5.
* ``clause8``: ``GET /record-types`` lists engineering.Tag as ``full``; the record screen rows show
  the Offline class line in technical mode only.
* ``clause9``: the readiness registry is empty, the contract passes on a sample check, a reserved
  identifier in a body is 422, and ``awp.iwp.ready_lead_weeks`` reads 4.
* ``doc-schema FILE``: writes the derive schema file of a documents publish target (clause 10).
"""

from __future__ import annotations

import os
import sys
import tempfile
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any, NoReturn

import yaml
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool
from tl_adapters.backend import open_backend
from tl_adapters.db import as_target
from tl_adapters.objectstore import make_object_store, object_secret
from tl_api.app import create_app
from tl_api.settings import ApiSettings
from tl_api.tokens import TokenStore
from tl_core import settings as platform_settings
from tl_core.auth import sessions
from tl_core.auth.errors import NoCompanyRolesError
from tl_core.auth.module_grants import GrantModuleRole, grant_module_role
from tl_core.auth.module_roles import command_index
from tl_core.files.service import FileService
from tl_core.modules import ModuleSpec, load_modules, use_modules
from tl_core.offline import capture_allowed, record_type_rows
from tl_core.readiness import (
    CheckResult,
    ContractWorld,
    IwpFacts,
    check_readiness_contract,
    load_checks,
)
from tl_core.services import proposals
from tl_mod_documents.derivation import store as derivation_store
from tl_mod_documents.derivation import views
from tl_mod_documents.derivation.publish import PublishDerivedDocuments
from tl_schema.generated.offline_classes import OFFLINE_CLASSES
from tl_tui.details import details_for
from tl_tui.display import DisplayMode, Labels, offline_words
from tl_tui.embedded import EmbeddedClient

PASSWORDS = {  # the documented dev passwords the script seeds the people with
    "ada": "a long passphrase for ada",
    "alice": "a long passphrase for alice",
    "bob": "a long passphrase for bob",
    "dora": "a long passphrase for dora",
}
P1, P2 = "project:P1", "project:P2"
AGENT = "agent:triage"
TODAY = date(2026, 10, 30)
RECORD_TYPES = frozenset({"awp.IWP", "documents.Revision"})
MODES = ("clause3", "clause4", "clause5", "clause6", "clause7", "clause8", "clause9", "doc-schema")


def passed(clause: int, text_: str) -> None:
    print(f"PASS clause {clause}: {text_}", flush=True)


def miss(what: str) -> NoReturn:
    print(f"FAIL {what}", flush=True)
    raise SystemExit(1)


def check(condition: bool, what: str) -> None:
    if not condition:
        miss(what)


class World:
    """The ledger in TL_DB, its API in process, and one signed-in test client per person."""

    def __init__(self) -> None:
        target = as_target(os.environ["TL_DB"])
        self.backend = open_backend(target)
        tokens = Path(tempfile.mkdtemp(prefix="p2-w0-demo-")) / "tokens.json"
        settings = ApiSettings(db_path=target, tokens_path=tokens)
        self.app = create_app(self.backend, settings=settings, tokens=TokenStore(tokens))
        # a publication reads its stored rows through the file service (as P1-I3's driver does)
        derivation_store.configure(FileService(make_object_store(), secret=object_secret()))
        self.clients: dict[str, TestClient] = {}
        self.principals: dict[str, Any] = {}

    def client(self, name: str) -> TestClient:
        if name not in self.clients:
            principal, token = sessions.sign_in(
                self.backend, username=name, password=PASSWORDS[name]
            )
            client = TestClient(self.app, raise_server_exceptions=False)
            client.headers.update({"Authorization": f"Bearer {token}"})
            self.clients[name] = client
            self.principals[name] = principal
        return self.clients[name]

    def account_id(self, name: str) -> str:
        self.client(name)
        return str(self.principals[name].account_id)

    def close(self) -> None:
        self.backend.close()


def clause3(doc_id: str) -> None:
    world = World()
    try:
        dora = world.client("dora")
        body = {"scope": P2, "number": "ISO-2003", "title": "Refused on P2"}
        refused = dora.post("/commands/RegisterDocument", json=body)
        check(refused.status_code == 403, f"dora registered on P2: {refused.status_code}")
        passed(3, f"RegisterDocument on P2 is refused for dora ({refused.status_code})")
        offered = dora.get(f"/records/{doc_id}/actions")
        check(offered.status_code == 200, f"actions on the P2 document: {offered.status_code}")
        check(offered.json()["actions"] == [], f"dora is offered {offered.json()['actions']}")
        passed(3, "GET /records/{id}/actions on the P2 document offers dora nothing")
    finally:
        world.close()


def grant_events(client: TestClient) -> list[str]:
    response = client.get("/events", params={"limit": 1000})
    check(response.status_code == 200, f"GET /events: {response.status_code} {response.text[:120]}")
    return [e["event_type"] for e in response.json()["events"] if "ModuleRole" in e["event_type"]]


def clause4() -> None:
    world = World()
    try:
        alice_events = grant_events(world.client("alice"))
        check(alice_events == [], f"alice sees grant events: {alice_events[:3]}")
        passed(4, "GET /events as alice shows no module-role grant event")
        ada_events = grant_events(world.client("ada"))
        check(len(ada_events) > 0, "GET /events as ada shows no module-role grant event")
        passed(4, f"GET /events as ada shows {len(ada_events)} module-role grant events")
    finally:
        world.close()


def proposal_status(client: TestClient, proposal_id: str) -> str:
    response = client.get(f"/proposals/{proposal_id}", params={"scope": P1})
    check(response.status_code == 200, f"GET /proposals/{proposal_id}: {response.status_code}")
    return str(response.json()["status"])


def accept(client: TestClient, proposal_id: str) -> Any:
    return client.post(f"/proposals/{proposal_id}/accept", params={"scope": P1}, json={})


def clause5(key: str) -> None:
    """An agent proposes the publication of a valid derived register into documents (P1)."""
    world = World()
    try:
        with world.backend(True) as uow:
            found = views.find_derived(uow.conn(), P1, key)
        command = PublishDerivedDocuments(
            actor=AGENT, source="mcp:triage", scope=P1, derived_id=found.id,
            expected_content_rev=max(found.content_rev, 1),
        )  # fmt: skip
        # ``propose`` records the proposal only: ``submit`` would first run the publication as the
        # agent, which holds no module role, and refuse it before any person decides
        with world.backend() as uow:
            view = proposals.propose(
                uow, tool="propose_import_documents", agent=AGENT, command=command,
                summary=f"Create the documents of {key}",
            )  # fmt: skip
        pid = view.proposal_id
        for who, what in (
            ("bob", "bob (a plain user) accepts the agent's publication"),
            ("alice", "alice (superuser on documents, a plain account) accepts it"),
        ):
            refused = accept(world.client(who), pid)
            text = refused.text[:120]
            check(refused.status_code == 403, f"{who}'s accept: {refused.status_code} {text}")
            check(refused.json().get("error") == "proposal_access", f"{who}'s accept: {text}")
            check(proposal_status(world.client(who), pid) == "pending", f"{who}: not pending")
            passed(5, f"{what}: 403 proposal_access, the proposal stays pending")
        done = accept(world.client("dora"), pid)
        check(done.status_code == 200, f"dora's accept: {done.status_code} {done.text[:160]}")
        check(done.json()["status"] == "accepted", f"dora's accept: {done.text[:200]}")
        passed(5, f"dora (document controller) accepts it and the publication of {key} runs")
    finally:
        world.close()


def clause6() -> None:
    world = World()
    try:
        alice_id = world.account_id("alice")
        stand_in = ModuleSpec(
            name="awp",
            record_types=frozenset({"awp.Cwp"}),
            projectors=list,
            command_words={"ReleaseCwp": "awp.cwp.release"},
            company_roles=True,
        )
        with use_modules([*load_modules(), stand_in]):
            check(command_index()["ReleaseCwp"] == ("awp", "controller"), "awp.cwp.release")
            with world.backend() as uow:
                granted = grant_module_role(
                    uow,
                    GrantModuleRole(
                        actor="user:ada", source="demo", scope="company", account_id=alice_id,
                        project="company", module="awp", role="user", reason="demo",
                    ),
                )  # fmt: skip
            check(granted.changed, "the company grant on awp was not written")
            passed(6, "a company grant for a stand-in module with company_roles is accepted")
            try:
                with world.backend() as uow:
                    grant_module_role(
                        uow,
                        GrantModuleRole(
                            actor="user:ada", source="demo", scope="company", account_id=alice_id,
                            project="company", module="documents", role="user", reason="demo",
                        ),
                    )  # fmt: skip
            except NoCompanyRolesError:
                passed(6, "a company grant on documents is refused no_company_roles")
            else:
                miss("a company grant on documents was accepted")
    finally:
        world.close()


def clause7() -> None:
    rows = record_type_rows()
    types = {row.record_type for row in rows}
    check(set(OFFLINE_CLASSES) == types and len(OFFLINE_CLASSES) == len(rows), "OFFLINE_CLASSES")
    passed(7, f"OFFLINE_CLASSES has one entry per record type ({len(rows)})")
    decision = capture_allowed("documents.Revision", "IssueRevision", node="device")
    check(decision.reason == "central_act", f"IssueRevision on device: {decision.reason}")
    decision = capture_allowed("documents.Revision", "CreateRevision", node="device")
    check(decision.reason == "draft", f"CreateRevision on device: {decision.reason}")
    decision = capture_allowed("cost.CostCode", "AddLink", node="device")
    check(decision.reason == "online_only", f"cost.CostCode on device: {decision.reason}")
    passed(
        7,
        "capture on device: IssueRevision central_act, CreateRevision draft, CostCode online_only",
    )
    for row in rows:
        for command in ("CreateRecord", "IssueRevision", "AddLink"):
            allowed = capture_allowed(row.record_type, command, node="authority").allowed
            check(allowed, f"{row.record_type} {command} on authority is refused")
    passed(7, "every record type and the checked commands are allowed on authority")


def clause8() -> None:
    world = World()
    try:
        rows = world.client("alice").get("/record-types").json()
        tag = next(row for row in rows if row["record_type"] == "engineering.Tag")
        check(tag["offline"] == "full", f"engineering.Tag is {tag['offline']}")
        passed(8, "GET /record-types lists engineering.Tag as full")
        client = EmbeddedClient(world.backend, actor="user:alice")
        record = {
            "id": "01P2W0TAG",
            "type": "engineering.Tag",
            "key": "47-FV-1001",
            "status": "Draft",
        }
        labels = Labels()
        technical = DisplayMode()
        technical.technical = True
        plain = DisplayMode()
        plain.technical = False
        lines = [r for r in details_for(client, P1, record, labels, technical)
                 if r.label == "Offline class"]  # fmt: skip
        check(len(lines) == 1 and lines[0].value == offline_words("full"), f"technical: {lines}")
        hidden = [r for r in details_for(client, P1, record, labels, plain)
                  if r.label == "Offline class"]  # fmt: skip
        check(hidden == [], "the plain record screen shows the Offline class line")
        passed(8, "the record screen shows the Offline class line in technical mode only")
    finally:
        world.close()


class SampleCheck:
    """A readiness check that answers n/a and writes nothing (the shape W0-B1 tests with)."""

    version = "1"
    watches = frozenset({"awp.IWP"})

    def __init__(self, name: str) -> None:
        self.name = name

    def evaluate(self, _conn: Any, _iwp: IwpFacts, _today: date) -> CheckResult:
        return CheckResult(name=self.name, version=self.version, state="n_a", detail="sample")


def clause9() -> None:
    check(load_checks() == {}, f"load_checks() is {load_checks()}")
    engine = create_engine("sqlite://", poolclass=StaticPool)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE thing (id INTEGER PRIMARY KEY)"))
    iwp = IwpFacts(record_id="r1", scope="P123", key="P123-IWP-PIP-0001", status="Draft")
    world_check = ContractWorld(engine.connect, iwp, TODAY, RECORD_TYPES, True)
    check_readiness_contract(SampleCheck("sample_check"), world_check)  # type: ignore[arg-type]
    passed(9, "load_checks() is empty and the contract passes on the sample check")
    world = World()
    try:
        alice = world.client("alice")
        for field, value in (("correlation_id", "rollup:x"), ("source", "job:x")):
            body = {"scope": P1, "number": "ISO-9009", "title": "Reserved", field: value}
            refused = alice.post("/commands/RegisterDocument", json=body)
            check(refused.status_code == 422, f"{field}={value}: {refused.status_code}")
            check(refused.json().get("error") == "reserved_identifier", refused.text[:120])
        passed(9, "a body with correlation_id rollup:x or source job:x is 422 reserved_identifier")
        with world.backend(True) as uow:
            lead = platform_settings.resolve(uow.conn(), "awp.iwp.ready_lead_weeks").value
        check(lead == 4, f"awp.iwp.ready_lead_weeks reads {lead!r}")
        passed(9, "awp.iwp.ready_lead_weeks reads 4")
    finally:
        world.close()


def doc_schema(path: str) -> None:
    """A derive schema file: a `doc-list` schema whose rows publish to the documents target."""
    body = {
        "code": "doc-list",
        "semver": "1.0.0",
        "title": "Document list",
        "description": "Document numbers and titles, published as controlled documents.",
        "json_schema": {
            "type": "object",
            "required": ["number", "title"],
            "properties": {"number": {"type": "string"}, "title": {"type": "string"}},
        },
        "key_column": "number",
        "target_kind": "documents",
        "mapping": {
            "target": "documents",
            "key_column": "number",
            "columns": [
                {"column": "number", "to": "number"},
                {"column": "title", "to": "title"},
            ],
        },
    }
    Path(path).write_text(yaml.safe_dump(body, sort_keys=False), encoding="utf-8")
    print(f"wrote the doc-list schema to {path}", flush=True)


def main(argv: list[str]) -> None:
    mode = argv[1] if len(argv) > 1 else ""
    args = argv[2:]
    if mode not in MODES:
        raise SystemExit(f"usage: p2_w0_demo.py {'|'.join(MODES)} [ARGS]")
    handlers: dict[str, Callable[..., None]] = {
        "clause3": clause3, "clause4": clause4, "clause5": clause5, "clause6": clause6,
        "clause7": clause7, "clause8": clause8, "clause9": clause9, "doc-schema": doc_schema,
    }  # fmt: skip
    expected = {"clause3": 1, "clause5": 1, "doc-schema": 1}.get(mode, 0)
    if len(args) != expected:
        raise SystemExit(f"{mode} takes {expected} argument(s)")
    handlers[mode](*args)


if __name__ == "__main__":
    main(sys.argv)
