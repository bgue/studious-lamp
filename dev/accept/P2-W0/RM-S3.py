"""Acceptance script for P2-W0 RM-S3: module roles on every admin surface.

Runs on SQLite with temp ledgers. Prints one ``PASS <check>`` line per check, plus the output of
the embedded client and the fake, of the CLI and of the module roles log (table and panel, 80 and
170 columns); exits 0 when every check passes, 1 on the first failure.

Nothing here decides who may do what: every expectation is computed from the role table
(``schema/settings/module-roles.yaml``) or stated as a fact of the spec.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

os.environ.setdefault("TL_ENV", "test")  # dev tokens (the agent principal) and the dev ledger rule

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages" / "tl-tui" / "tests"))  # the fake client and its helpers

import yaml  # noqa: E402
from fakes import SCOPE, FakeClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from helpers import screen_text, settle  # noqa: E402
from tl_adapters.backend import open_backend  # noqa: E402
from tl_adapters.db import create_schema  # noqa: E402
from tl_api.app import create_app  # noqa: E402
from tl_api.settings import ApiSettings  # noqa: E402
from tl_api.tokens import TokenStore, add_token  # noqa: E402
from tl_core.auth import accounts, sessions  # noqa: E402
from tl_core.auth.errors import ForbiddenError, NoSuchGrantError  # noqa: E402
from tl_core.auth.password import prepare_password  # noqa: E402
from tl_core.modules import load_modules  # noqa: E402
from tl_tui.app import TlApp  # noqa: E402
from tl_tui.embedded import EmbeddedClient  # noqa: E402
from tl_tui.widgets.admin_screen import AdminScreen  # noqa: E402
from tl_tui.widgets.module_roles_log import ModuleRolesLog  # noqa: E402
from typer.testing import CliRunner  # noqa: E402

PASSWORD = "correct horse battery"
P1 = "project:P1"
TABLE = yaml.safe_load(
    (ROOT / "schema" / "settings" / "module-roles.yaml").read_text(encoding="utf-8")
)
MODULES = [spec.name for spec in load_modules()]


def passed(check: str) -> None:
    print(f"PASS {check}")


def error_code(response: Any) -> str:
    return str(response.json()["error"])


# --- the API --------------------------------------------------------------------------------


class World:
    def __init__(self, work: Path) -> None:
        db = work / "api.db"
        create_schema(db)
        self.backend = open_backend(db)
        tokens = work / "tokens.json"
        settings = ApiSettings(db_path=db, tokens_path=tokens)
        self.app = create_app(self.backend, settings=settings, tokens=TokenStore(tokens))
        self.tokens_path = tokens
        self.clients: dict[str, TestClient] = {}
        self.ids: dict[str, str] = {}

    def _client(self, token: str) -> TestClient:
        client = TestClient(self.app, raise_server_exceptions=False)
        client.headers.update({"Authorization": f"Bearer {token}"})
        return client

    def person(self, name: str, roles: tuple[str, ...], kind: str = "person") -> None:
        password = None if kind == "agent" else prepare_password(PASSWORD, username=name)
        with self.backend() as uow:
            view = accounts.create_account(
                uow, username=name, display_name=name.title(), kind=kind,  # pyright: ignore
                roles=list(roles), password=password, by="svc:accept",
            )  # fmt: skip
        self.ids[name] = view.account_id
        if kind != "agent":
            _, token = sessions.sign_in(self.backend, username=name, password=PASSWORD)
            self.clients[name] = self._client(token)

    def agent_token(self, name: str) -> None:
        self.clients[f"agent:{name}"] = self._client(add_token(self.tokens_path, f"agent:{name}"))

    def body(self, role: str, module: str = "documents", project: str = P1) -> dict[str, str]:
        return {"project": project, "module": module, "role": role, "reason": "acceptance"}

    def grant_url(self, who: str) -> str:
        return f"/admin/accounts/{self.ids[who]}/module-roles"


def api_checks(work: Path) -> None:
    world = World(work)
    world.person("ada", ("admin",))
    world.person("uma", ("user",))
    world.person("dora", ("user", "document_controller"))
    world.person("triage", ("user",), kind="agent")
    world.agent_token("triage")
    ada, uma = world.clients["ada"], world.clients["uma"]
    url = world.grant_url("uma")

    first = ada.post(url, json=world.body("superuser"))
    assert first.status_code == 201 and first.json()["changed"] is True, first.text
    passed("admin: grant answers 201 with changed true")
    again = ada.post(url, json=world.body("superuser"))
    assert again.status_code == 201 and again.json()["changed"] is False, again.text
    passed("admin: the same grant again answers changed false (nothing written)")
    revoked = ada.post(f"{url}/revoke", json=world.body("superuser"))
    assert revoked.status_code == 200 and revoked.json()["changed"] is True, revoked.text
    passed("admin: revoke answers 200")
    gone = ada.post(f"{url}/revoke", json=world.body("superuser"))
    assert gone.status_code == 404 and error_code(gone) == "no_such_grant", gone.text
    passed("admin: revoke again is 404 no_such_grant")
    bad_role = ada.post(url, json=world.body("overlord"))
    assert bad_role.status_code == 422 and error_code(bad_role) == "unknown_role", bad_role.text
    bad_module = ada.post(url, json=world.body("user", module="nowhere"))
    assert error_code(bad_module) == "unknown_module" and bad_module.status_code == 422
    passed("admin: an unknown role and an unknown module are 422 unknown_role / unknown_module")
    assert not any(getattr(m, "company_roles", False) for m in load_modules())
    company = ada.post(url, json=world.body("user", project="company"))
    assert company.status_code == 422 and error_code(company) == "no_company_roles", company.text
    passed("admin: a company grant for a module without company_roles is 422 no_company_roles")
    agent = ada.post(world.grant_url("triage"), json=world.body("superuser"))
    assert agent.status_code == 422 and error_code(agent) == "invalid_account", agent.text
    passed("admin: an agent account cannot be granted superuser (422)")
    missing = ada.post("/admin/accounts/NOSUCH/module-roles", json=world.body("user"))
    assert missing.status_code == 404 and error_code(missing) == "account_not_found"
    passed("admin: an unknown account is 404 account_not_found")

    # a plain user: every admin route is refused
    probes = [
        ("post", url, world.body("user")),
        ("post", f"{url}/revoke", world.body("user")),
        ("get", "/admin/module-roles", None),
        ("get", f"/admin/accounts/{world.ids['uma']}/effective-roles?project={P1}", None),
    ]
    for client in ("uma", "dora", "agent:triage"):
        for method, path, body in probes:
            call = world.clients[client]
            response = call.post(path, json=body) if method == "post" else call.get(path)
            assert response.status_code == 403, (client, method, path, response.status_code)
    passed("a plain user, a document controller and an agent: all four admin routes answer 403")

    mine = uma.get("/auth/me/roles", params={"project": P1})
    assert mine.status_code == 200, mine.text
    derived = {row["module"]: (row["roles"], row["source"]) for row in mine.json()}
    assert derived == {m: (["user"], "derived") for m in MODULES}, derived
    passed(f"a plain user reads their own roles: user, derived, in all {len(MODULES)} modules")
    dora = world.clients["dora"].get("/auth/me/roles", params={"project": P1}).json()
    got = {row["module"]: row["roles"] for row in dora}
    want = {"documents", "correspondence", "schedule"}
    assert {m for m, r in got.items() if "superuser" in r} == want, got
    passed("a document controller reads superuser (derived) in documents, correspondence, schedule")
    agent_me = world.clients["agent:triage"].get("/auth/me/roles", params={"project": P1})
    assert agent_me.status_code == 200, agent_me.text
    passed("an agent may read its own roles (auth.me); the admin routes stay closed to it")
    assert uma.get("/auth/me/roles").status_code == 422  # project is required, nobody else's id
    passed("GET /auth/me/roles takes no account id: the project alone")

    # filters
    dora_id = world.ids["dora"]
    for who, project, module, role in (
        ("uma", P1, "documents", "viewer"),
        ("uma", "project:P2", "schedule", "superuser"),
        ("dora", P1, "documents", "user"),
    ):
        r = ada.post(world.grant_url(who), json=world.body(role, module=module, project=project))
        assert r.status_code == 201, r.text
    everything = ada.get("/admin/module-roles").json()
    assert len(everything) == 3, everything
    by_project = ada.get("/admin/module-roles", params={"project": P1}).json()
    by_module = ada.get("/admin/module-roles", params={"module": "schedule"}).json()
    by_account = ada.get("/admin/module-roles", params={"account_id": dora_id}).json()
    both = ada.get("/admin/module-roles", params={"project": P1, "module": "documents"}).json()
    assert [(g["username"], g["project"]) for g in by_project] == [("dora", P1), ("uma", P1)]
    assert [(g["username"], g["module"]) for g in by_module] == [("uma", "schedule")]
    assert [(g["username"], g["role"]) for g in by_account] == [("dora", "user")]
    assert len(both) == 2
    assert set(everything[0]) == {
        "account_id", "username", "project", "module", "role", "granted_by", "granted_at",
    }  # fmt: skip
    passed("GET /admin/module-roles: all 3; filtered by project (2), module (1), account (1)")

    rows = ada.get(f"/admin/accounts/{world.ids['uma']}/effective-roles", params={"project": P1})
    views = rows.json()
    assert [v["module"] for v in views] == MODULES and set(views[0]) == {
        "module",
        "roles",
        "source",
    }
    by_name = {v["module"]: v for v in views}
    assert by_name["documents"] == {"module": "documents", "roles": ["viewer"], "source": "granted"}
    assert by_name["cost"] == {"module": "cost", "roles": ["user"], "source": "derived"}
    passed(
        f"effective-roles: one entry per loaded module ({len(views)}) with the resolver's source"
    )
    other = ada.get(
        f"/admin/accounts/{world.ids['uma']}/effective-roles", params={"project": "project:P2"}
    )
    assert {v["module"]: v["source"] for v in other.json()}["schedule"] == "granted"
    admin_roles = ada.get(
        f"/admin/accounts/{world.ids['ada']}/effective-roles", params={"project": P1}
    )
    assert {v["source"] for v in admin_roles.json()} == {"admin"}
    assert all(v["roles"] == list(TABLE["roles"]) for v in admin_roles.json())
    passed("effective-roles: scoped to the project asked for; an admin holds every role (admin)")
    assert ada.get("/admin/module-roles", params={"project": "P1"}).status_code == 422
    passed("a project that is neither `company` nor `project:<id>` is a 422")

    # events
    admin_types = {e["event_type"] for e in ada.get("/events").json()["events"]}
    user_types = {e["event_type"] for e in uma.get("/events").json()["events"]}
    assert "Account.ModuleRoleGranted" in admin_types and "Account.ModuleRoleRevoked" in admin_types
    assert not {t for t in user_types if t.startswith("Account.")}, user_types
    passed("/events: an admin sees the grant and revoke events, a plain user sees no Account event")


# --- the embedded client and the fake -----------------------------------------------------------


def shown(call: Any) -> Any:
    try:
        value = call()
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"
    if isinstance(value, list):
        return [v.model_dump(exclude={"account_id", "granted_at", "granted_by"}) for v in value]
    return {"changed": value.changed}


def client_checks(work: Path) -> None:
    db = work / "embedded.db"
    create_schema(db)
    embedded = EmbeddedClient.for_sqlite(db, actor="user:boss")
    with embedded._uow(False) as uow:  # pyright: ignore[reportPrivateUsage]
        for name, roles in (("boss", ["admin"]), ("amy", ["user"])):
            accounts.create_account(
                uow, username=name, display_name=name.title(), kind="person", roles=roles,
                password=prepare_password(PASSWORD, username=name), by="svc:accept",
            )  # fmt: skip
        amy_e = accounts.create_account(  # a second 'amy' is refused: read the first back
            uow, username="cat", display_name="Cat", kind="person", roles=["user"],
            password=prepare_password(PASSWORD, username="cat"), by="svc:accept",
        )  # fmt: skip
    fake = FakeClient()
    fake.seed_account("boss", roles=["admin"])
    fake.seed_account("amy")
    amy_f = fake.seed_account("cat")
    fake.me_account_id = fake.list_accounts()[0].account_id
    both = {"embedded": (embedded, amy_e.account_id), "fake": (fake, amy_f.account_id)}
    script = (
        ("grant", lambda c, a: c.grant_module_role(a, P1, "documents", "superuser", "demo")),
        ("grant again", lambda c, a: c.grant_module_role(a, P1, "documents", "superuser", "demo")),
        ("list", lambda c, a: c.list_module_roles(P1)),
        ("list (other project)", lambda c, a: c.list_module_roles("project:P2")),
        ("effective", lambda c, a: c.effective_roles(a, P1)),
        ("my roles (the admin)", lambda c, a: c.my_roles(P1)),
        ("unknown role", lambda c, a: c.grant_module_role(a, P1, "documents", "boss", "demo")),
        ("unknown module", lambda c, a: c.grant_module_role(a, P1, "nowhere", "user", "demo")),
        ("company grant", lambda c, a: c.grant_module_role(a, "company", "documents", "user", "d")),
        ("revoke", lambda c, a: c.revoke_module_role(a, P1, "documents", "superuser", "demo")),
        ("revoke again", lambda c, a: c.revoke_module_role(a, P1, "documents", "superuser", "x")),
    )
    for label, call in script:
        answers = {
            name: shown(lambda c=c, a=a, call=call: call(c, a)) for name, (c, a) in both.items()
        }
        for name, answer in answers.items():
            text = str(answer)
            print(f"  {label:22s} {name:9s} {text[:110]}")
        assert answers["embedded"] == answers["fake"], (label, answers)
    passed("the embedded client and the fake answer the five calls alike (printed above)")

    # the gate: a plain account gets ForbiddenError on the admin four, and reads its own roles
    plain = EmbeddedClient.for_sqlite(db, actor="user:amy")
    for call in (
        lambda: plain.list_module_roles(P1),
        lambda: plain.effective_roles(amy_e.account_id, P1),
        lambda: plain.grant_module_role(amy_e.account_id, P1, "documents", "user", "x"),
        lambda: plain.revoke_module_role(amy_e.account_id, P1, "documents", "user", "x"),
    ):
        try:
            call()
        except ForbiddenError:
            continue
        raise AssertionError("expected ForbiddenError")
    mine = plain.my_roles(P1)
    assert [v.roles for v in mine] == [["user"]] * len(MODULES), mine
    passed("embedded: the admin four refuse a plain account (ForbiddenError); my_roles answers")
    try:
        embedded.revoke_module_role(amy_e.account_id, P1, "documents", "superuser", "x")
    except NoSuchGrantError:
        pass
    else:
        raise AssertionError("expected NoSuchGrantError")


# --- the CLI ---------------------------------------------------------------------------------


def cli_checks(work: Path) -> None:
    from tl_cli.main import app

    runner = CliRunner()
    env = {"TL_DB": str(work / "cli.db"), "TL_ENV": "dev", "TL_SESSION_FILE": str(work / "s.json")}

    def tl(*args: str, stdin: str | None = None) -> Any:
        result = runner.invoke(app, list(args), env=env, input=stdin)
        print(f"$ tl {' '.join(args)}\n{result.output.rstrip()}  [exit {result.exit_code}]")
        return result

    assert tl("init").exit_code == 0
    boot = ("admin", "bootstrap", "--username", "root", "--password-stdin")
    assert tl(*boot, stdin=PASSWORD).exit_code == 0
    assert tl("login", "root", "--password-stdin", stdin=PASSWORD).exit_code == 0
    assert tl("admin", "user", "add", "alice", "--password-stdin", stdin=PASSWORD).exit_code == 0
    roles = ("admin", "roles")
    grant = tl(*roles, "grant", "alice", "--project", "P1", "--module", "documents",
               "--role", "superuser", "--reason", "demo")  # fmt: skip
    assert grant.exit_code == 0 and "granted superuser on documents for project:P1" in grant.output
    again = tl(*roles, "grant", "alice", "--project", "P1", "--module", "documents",
               "--role", "superuser", "--reason", "demo")  # fmt: skip
    assert again.exit_code == 0 and "already held" in again.output
    listed = tl(*roles, "ls")
    assert (
        listed.exit_code == 0
        and "alice  project:P1  documents  superuser  by user:root" in listed.output
    )
    filtered = tl(*roles, "ls", "--project", "P2", "--user", "alice")
    assert filtered.exit_code == 0 and filtered.output.strip() == ""
    effective = tl(*roles, "effective", "alice", "--project", "P1")
    assert "documents  superuser  granted" in effective.output
    assert "cost  user  derived" in effective.output
    revoke = tl(*roles, "revoke", "alice", "--project", "P1", "--module", "documents",
                "--role", "superuser", "--reason", "demo over")  # fmt: skip
    assert (
        revoke.exit_code == 0 and "revoked superuser on documents for project:P1" in revoke.output
    )
    after = tl(*roles, "revoke", "alice", "--project", "P1", "--module", "documents",
               "--role", "superuser", "--reason", "twice")  # fmt: skip
    assert after.exit_code == 1 and "error:" in after.output
    unknown = tl(*roles, "grant", "alice", "--project", "company", "--module", "documents",
                 "--role", "user", "--reason", "x")  # fmt: skip
    assert unknown.exit_code == 1 and "no company-level roles" in unknown.output
    passed("CLI: grant, grant again, ls, ls filtered, effective, revoke, revoke again refused")
    # a plain user is refused by the command, not by the handler alone
    assert tl("admin", "user", "add", "bob", "--password-stdin", stdin=PASSWORD).exit_code == 0
    assert tl("logout").exit_code == 0
    assert tl("login", "bob", "--password-stdin", stdin=PASSWORD).exit_code == 0
    refused = tl(*roles, "ls")
    assert refused.exit_code == 1 and "forbidden" in refused.output
    passed("CLI: a signed-in plain user is refused `tl admin roles ls` (exit 1, forbidden)")


# --- the module roles log -----------------------------------------------------------------------


def seeded_fake() -> FakeClient:
    client = FakeClient()
    boss = client.seed_account("boss", roles=["admin", "user"], display_name="Boss B")
    amy = client.seed_account("amy", display_name="Amy A")
    bob = client.seed_account("bob", display_name="Bob B")
    client.me_account_id = boss.account_id
    client.seed_module_role(amy.account_id, SCOPE, "documents", "superuser")
    client.seed_module_role(amy.account_id, SCOPE, "schedule", "viewer")
    client.seed_module_role(bob.account_id, SCOPE, "*", "user")
    client.admin_calls.clear()
    return client


def run_tui(app: TlApp, scenario: Any, size: tuple[int, int]) -> None:
    async def main() -> None:
        async with app.run_test(size=size) as pilot:
            await settle(pilot)
            await scenario(pilot)

    asyncio.run(main())


def tui_checks() -> None:
    for size in ((80, 24), (170, 40)):
        client = seeded_fake()
        app = TlApp(client, scope=SCOPE, actor="user:boss", is_admin=True)
        seen: dict[str, str] = {}

        async def scenario(
            pilot: Any, app: TlApp = app, seen: dict[str, str] = seen, client: FakeClient = client
        ) -> None:
            await pilot.press("f10")
            await settle(pilot)
            assert isinstance(app.screen, AdminScreen)
            assert "m module roles" in AdminScreen.KEY_HINTS
            await pilot.press("m")
            await settle(pilot)
            assert isinstance(app.screen, ModuleRolesLog), type(app.screen).__name__
            log = app.screen
            assert len(log.rows) == 3
            seen["log"] = screen_text(app)
            await pilot.press("down")
            await settle(pilot)
            seen["second"] = screen_text(app)
            # the grant disappears behind the screen's back; the revoke is refused
            client._module_grants.clear()  # pyright: ignore[reportPrivateUsage]
            await pilot.press("r")
            await settle(pilot)
            seen["form"] = screen_text(app)
            for key in "gone":
                await pilot.press(key)
            await pilot.press("enter")
            await settle(pilot)
            seen["refused"] = "\n".join(
                line.strip()
                for line in screen_text(app).splitlines()
                if line.strip().startswith("!")
            )

        run_tui(app, scenario, size)
        print(f"\n--- module roles log at {size[0]} columns, 3 rows (table and panel) ---")
        print(seen["log"])
        print(f"--- second row highlighted at {size[0]} columns ---")
        print(seen["second"])
        print(f"--- revoke refusal at {size[0]} columns (status line) ---")
        print(seen["refused"])
        text = seen["log"]
        for needle in ("Amy A", "Documents", "Superuser", "Effective roles", "Granted"):
            assert needle in text, (size, needle)
        assert "01FAKE" not in text and "01FAKE" not in seen["second"], "an id in plain mode"
        assert "is not held by that account" in seen["refused"], seen["refused"]
        passed(f"module roles log at {size[0]} columns: 3 rows, panel, refusal in the status line")

    # a new grant through the form, then the unchanged repeat
    client = seeded_fake()
    app = TlApp(client, scope=SCOPE, actor="user:boss", is_admin=True)
    out: dict[str, Any] = {}

    async def grant_flow(pilot: Any) -> None:
        await pilot.press("f10", "m")
        await settle(pilot)
        await pilot.press("n")
        await settle(pilot)
        out["form"] = screen_text(app)
        await pilot.press("tab", "tab", "tab")  # account, module, role -> reason
        for key in "demo":
            await pilot.press(key)
        await pilot.press("enter")
        await settle(pilot)
        out["status"] = screen_text(app)

    run_tui(app, grant_flow, (120, 40))
    calls = [a for m, a in client.admin_calls if m == "grant_module_role"]
    assert len(calls) == 1 and calls[0]["project"] == SCOPE, calls
    passed("module roles log: key n opens the form and sends one grant for the current project")

    # key m is not there for a non-admin
    client = seeded_fake()
    plain = TlApp(client, scope=SCOPE, actor="user:amy", is_admin=False)

    async def plain_flow(pilot: Any) -> None:
        await pilot.press("f10")
        await settle(pilot)
        assert not isinstance(plain.screen, AdminScreen)
        await pilot.press("m")
        await settle(pilot)
        assert not isinstance(plain.screen, ModuleRolesLog | AdminScreen)

    run_tui(plain, plain_flow, (120, 40))
    module_calls = [
        c for c in client.admin_calls if "module_role" in c[0] or c[0] == "effective_roles"
    ]
    assert not module_calls, module_calls
    passed("key m opens nothing for a non-admin (F10 refuses; no module role call was made)")


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        api_checks(work)
        print("\n--- embedded client and fake ---")
        client_checks(work)
        print("\n--- CLI ---")
        cli_checks(work)
        print("\n--- TUI ---")
        tui_checks()
    print("\nALL PASS")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as exc:
        print(f"FAIL {exc!r}")
        raise SystemExit(1) from exc
