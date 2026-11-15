"""Driver for dev/demos/P2-I4.sh clauses 5 and 6 (P2-I4B-T10a): the scaffold lifecycle, the
scaffold_tagged readiness check, the inspections-due job and the dismantle check.

It opens the ledger named by TL_DB (a SQLite file or a postgresql:// URL, read with `as_target`),
runs the API in process with the test client (the scaffold commands go over ``POST
/commands/{Name}`` with the person's session, as dev/demos/p2_i4_demo.py does), and reads the
readiness of the IWP over ``GET /projects/P123/awp/iwps/{number}/readiness``. Each mode prints one
``PASS clause N: <what was checked>`` line per check; a miss prints ``FAIL <what>`` and exits 1.
The people are the ones the shell script seeded (documented dev passwords). Token files go to
``P2_I4_WORKDIR``.

Modes (first argument):

* ``scaffold REQ_KEY IWP``: clause 5 (the scaffold registered from the approved request REQ_KEY,
  designed, erected, tagged green, released; a failed inspection gives a red tag and Modify, and
  scaffold_tagged is blocked) and the first part of clause 6 (the inspections-due job flags the
  scaffold once; the IWP is moved to Issued; a dismantle is refused, naming the IWP).
* ``scaffold-after``: after the script cancels the IWP, a dismantle is allowed; the scaffold is
  in state Dismantle.
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, NoReturn

from fastapi.testclient import TestClient
from sqlalchemy import text
from tl_adapters.backend import open_backend
from tl_adapters.db import as_target, make_uow_factory
from tl_adapters.queue import job_queue_for
from tl_api.app import create_app
from tl_api.client import ApiClient
from tl_api.settings import ApiSettings
from tl_api.tokens import TokenStore
from tl_core.auth import sessions
from tl_core.jobs import JobRunner
from tl_core.services.workflow import TransitionWorkflow, handle_transition_workflow
from tl_mod_awp.readiness.engine import request as request_readiness
from tl_mod_awp.worker import build_worker
from tl_mod_scaffold.inspections_due import InspectionsDueKind
from tl_mod_scaffold.inspections_due import request as request_inspections
from tl_mod_scaffold.names import SCAFFOLD_TABLE

PASSWORDS = {  # the documented dev passwords the script seeds the people with
    "uma": "a long passphrase for uma",
    "sue": "a long passphrase for sue",
}
PROJECT = "P123"
P123 = f"project:{PROJECT}"
IWP = "P123-IWP-PIP-0001"
SCAFFOLD_KEY = "P123-SCF-0001"  # the first scaffold of the demo ledger
#: The transitions from Draft to Issued (a copy of IWP_PATH["Issued"] in the scaffold test world).
ISSUED_PATH = ["develop", "check_constraints", "ready", "issue"]
SCAFFOLD_CHECK = "scaffold_tagged"


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
        self.target = target
        self.backend = open_backend(target)
        self.open_uow = make_uow_factory(target)
        workdir = Path(os.environ["P2_I4_WORKDIR"])
        self.workdir = workdir
        settings = ApiSettings(db_path=target, tokens_path=workdir / "tokens.json")
        self.app = create_app(
            self.backend, settings=settings, tokens=TokenStore(workdir / "tokens.json")
        )
        self.clients: dict[str, TestClient] = {}
        self.tokens: dict[str, str] = {}

    def token(self, name: str) -> str:
        if name not in self.tokens:
            _principal, token = sessions.sign_in(
                self.backend, username=name, password=PASSWORDS[name]
            )
            self.tokens[name] = token
            client = TestClient(self.app, raise_server_exceptions=False)
            client.headers.update({"Authorization": f"Bearer {token}"})
            self.clients[name] = client
        return self.tokens[name]

    def client(self, name: str) -> TestClient:
        self.token(name)
        return self.clients[name]

    def api(self, name: str) -> ApiClient:
        return ApiClient("http://testserver", self.token(name), http=self.client(name))

    def close(self) -> None:
        self.backend.close()

    def scalar(self, sql: str, **params: Any) -> Any:
        with self.open_uow(readonly=True) as uow:
            return uow.conn().execute(text(sql), params).scalar_one_or_none()

    def id_of(self, key: str) -> str:
        found = self.scalar("SELECT id FROM cur_core_record WHERE key = :k", k=key)
        check(found is not None, f"no record {key} on the ledger")
        return str(found)

    def state_of(self, record_id: str) -> str:
        """The state of a record; a scaffold with no state row yet is Requested (as in S1)."""
        found = self.scalar("SELECT status FROM cur_core_record WHERE id = :i", i=record_id)
        return "Requested" if found is None else str(found)

    def version_of(self, record_id: str) -> int:
        return int(self.scalar("SELECT version FROM cur_core_record WHERE id = :i", i=record_id))

    def scaffold_row(self, scaffold_id: str) -> dict[str, Any]:
        with self.open_uow(readonly=True) as uow:
            rows = uow.conn().execute(
                text(f"SELECT * FROM {SCAFFOLD_TABLE} WHERE id = :i"), {"i": scaffold_id}
            )
            return dict(rows.mappings().one())

    def event_count(self) -> int:
        return int(self.scalar("SELECT count(*) FROM events") or 0)


def post(world: World, who: str, name: str, **fields: Any) -> Any:
    """``POST /commands/{name}`` as ``who``, in the scope of the project."""
    return world.client(who).post(f"/commands/{name}", json={"scope": P123, **fields})


def done(resp: Any, what: str) -> None:
    check(resp.status_code == 200, f"{what}: {resp.status_code} {resp.text[:200]}")


def refused(resp: Any, status: int, code: str, words: str | None = None) -> None:
    """The door answers ``status`` with the error ``code``; the message names ``words``."""
    body = resp.json()
    message = str(body.get("message", ""))
    named = words is None or words in message
    check(
        resp.status_code == status and body.get("error") == code and named,
        f"expected {status} {code}; got {resp.status_code} {resp.text[:200]}",
    )


def readiness_state(world: World, iwp_id: str) -> str:
    """Evaluate the IWP's readiness with the awp readiness job in process, then read the
    scaffold_tagged check over the API."""
    with world.open_uow() as uow:
        request_readiness(uow, [iwp_id], reason="demo: clause 5")
    with build_worker(world.target) as worker:
        worker.runner.run_until_idle()
    resp = world.client("uma").get(f"/projects/{PROJECT}/awp/iwps/{IWP}/readiness")
    check(resp.status_code == 200, f"readiness: {resp.status_code} {resp.text[:200]}")
    checks = {c["name"]: c for c in resp.json()["checks"]}
    check(SCAFFOLD_CHECK in checks, f"the readiness has no {SCAFFOLD_CHECK} check")
    return str(checks[SCAFFOLD_CHECK]["state"])


def run_inspections_due(world: World, today: datetime) -> int:
    """Queue the inspections-due run of P123 for ``today`` and run the job; the events it wrote."""
    before = world.event_count()
    with world.open_uow() as uow:
        request_inspections(uow, PROJECT, today.date())
    with world.open_uow() as uow:
        queue = job_queue_for(uow.conn())
    JobRunner(world.open_uow, queue, [InspectionsDueKind()], worker_id="demo").run_until_idle()
    return world.event_count() - before


def transition_to_issued(world: World, iwp_id: str) -> None:
    for transition in ISSUED_PATH:
        version = world.version_of(iwp_id)  # read before the write unit of work opens
        with world.open_uow() as uow:
            handle_transition_workflow(
                uow,
                TransitionWorkflow(
                    actor="user:uma",
                    source="demo",
                    scope=P123,
                    stream_id=iwp_id,
                    expected_version=version,
                    transition=transition,
                ),
                by_module=True,
            )
    check(world.state_of(iwp_id) == "Issued", f"{IWP} is {world.state_of(iwp_id)}, not Issued")


def clause5_and_6(req_key: str, iwp: str) -> None:
    """Clause 5 in full; clause 6 up to the refused dismantle."""
    check(iwp == IWP, f"this demo's IWP is {IWP}, not {iwp}")
    world = World()
    try:
        req_id = world.api("uma").get_requisition(PROJECT, req_key).row.id
        iwp_id = world.id_of(IWP)

        resp = post(
            world, "uma", "RegisterScaffold", request_id=req_id, title="Scaffold level 1 east"
        )
        done(resp, "RegisterScaffold")
        sid = world.id_of(SCAFFOLD_KEY)
        check(world.state_of(sid) == "Requested", "a new scaffold is not Requested")
        passed(5, f"register gives {SCAFFOLD_KEY} from {req_key}, state Requested")

        done(post(world, "uma", "DesignScaffold", scaffold=sid), "DesignScaffold")
        done(post(world, "uma", "ErectScaffold", scaffold=sid), "ErectScaffold")
        check(world.state_of(sid) == "Erecting", "design then erect is not Erecting")
        passed(5, "design then erect: state Erecting")

        done(post(world, "sue", "TagScaffoldGreen", scaffold=sid), "TagScaffoldGreen")
        row = world.scaffold_row(sid)
        check(world.state_of(sid) == "Inspected" and row["tag"] == "green", "not Inspected, green")
        passed(5, "green tag: state Inspected, tag green (sue, scaffold superuser)")

        done(
            post(
                world,
                "uma",
                "AddLink",
                from_id=iwp_id,
                to_id=sid,
                relation="requires",
            ),
            "AddLink requires",
        )
        state = readiness_state(world, iwp_id)
        check(state == "ok", f"{SCAFFOLD_CHECK} is {state} with a green scaffold")
        passed(5, f"{SCAFFOLD_CHECK} on {IWP} is ok (the requires link from the IWP)")

        done(post(world, "uma", "ReleaseScaffold", scaffold=sid), "ReleaseScaffold")
        check(world.state_of(sid) == "In Use", "release did not give In Use")
        done(
            post(world, "uma", "InspectScaffold", scaffold=sid, result="fail"),
            "InspectScaffold fail",
        )
        row = world.scaffold_row(sid)
        check(world.state_of(sid) == "Modify" and row["tag"] == "red", "fail is not Modify, red")
        state = readiness_state(world, iwp_id)
        check(state == "blocked", f"{SCAFFOLD_CHECK} is {state} with a red scaffold")
        passed(5, f"a failed inspection: tag red, state Modify, {SCAFFOLD_CHECK} blocked")

        refused(post(world, "uma", "ReleaseScaffold", scaffold=sid), 409, "scaffold_state")
        done(post(world, "sue", "TagScaffoldGreen", scaffold=sid), "TagScaffoldGreen again")
        done(post(world, "uma", "ReleaseScaffold", scaffold=sid), "ReleaseScaffold again")
        check(world.state_of(sid) == "In Use", "release after green is not In Use")
        passed(5, "release from Modify is refused (409 scaffold_state); green again, then In Use")
        # the blocked evaluation raised a blocking constraint on the IWP; a passing one clears it
        state = readiness_state(world, iwp_id)
        check(state == "ok", f"{SCAFFOLD_CHECK} is {state} with the scaffold green again")
        passed(
            5, f"{SCAFFOLD_CHECK} is ok again after the re-tag (the blocked constraint is cleared)"
        )

        today = datetime.now(UTC)
        flagged = run_inspections_due(world, today + timedelta(days=8))
        check(flagged == 1, f"the inspections-due run wrote {flagged} events, not 1")
        row = world.scaffold_row(sid)
        check(
            row["flagged_due_on"] == row["next_due_on"] and world.state_of(sid) == "In Use",
            "the scaffold is not flagged for its next due day, or its state moved",
        )
        again = run_inspections_due(world, today + timedelta(days=8))
        check(again == 0, f"a second run on the same day wrote {again} events")
        passed(6, f"inspections-due flags {SCAFFOLD_KEY} once; a second run writes nothing")

        transition_to_issued(world, iwp_id)
        refused(
            post(world, "uma", "DismantleScaffold", scaffold=sid, reason="demo: pipe rack"),
            409,
            "scaffold_dismantle_refused",
            IWP,
        )
        check(world.state_of(sid) == "In Use", "a refused dismantle moved the scaffold")
        passed(6, f"dismantle is refused while {IWP} is Issued and requires the scaffold")
    finally:
        world.close()


def after_cancel() -> None:
    """After the script cancelled the IWP: the dismantle is allowed."""
    world = World()
    try:
        sid = world.id_of(SCAFFOLD_KEY)
        iwp_id = world.id_of(IWP)
        check(world.state_of(iwp_id) == "Cancelled", f"{IWP} is {world.state_of(iwp_id)}")
        done(
            post(
                world, "uma", "DismantleScaffold", scaffold=sid, reason="demo: work package closed"
            ),
            "DismantleScaffold",
        )
        check(world.state_of(sid) == "Dismantle", "the dismantle did not give Dismantle")
        passed(6, f"{IWP} is Cancelled, so the dismantle is allowed: {SCAFFOLD_KEY} Dismantle")
    finally:
        world.close()


MODES = {"scaffold": (2, clause5_and_6), "scaffold-after": (0, after_cancel)}


def main(argv: list[str]) -> None:
    mode = argv[1] if len(argv) > 1 else ""
    args = argv[2:]
    if mode not in MODES:
        raise SystemExit(f"usage: p2_i4b_demo.py {'|'.join(MODES)} [ARGS]")
    expected, run = MODES[mode]
    if len(args) != expected:
        raise SystemExit(f"{mode} takes {expected} argument(s)")
    run(*args)


if __name__ == "__main__":
    main(sys.argv)
