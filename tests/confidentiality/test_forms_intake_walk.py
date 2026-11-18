"""V3-F4 walk: every intake route, every `tl intake` read and the terminal's Intake log, as five
kinds of reader and an agent.

Readers: the document controller (``dora``, given the forms superuser role on the project: reads
everything), an administrator (``ada``: reads restricted, not privileged, items) and three plain
users (``uma``, ``rob``, ``vera``: they hold no intake word). An item whose code is about a record
the reader may not read answers exactly as an id that never existed does: same status, same
headers, same body, byte for byte; lists and counts leave it out. An agent is refused the same way
on every id before any lookup, and a stranger is signed out. Whatever is read, no code hash, salt,
stored body, mac or raw code appears; the sender's answers appear only in the detail of a Pending
item.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
from harness import Harness
from tl_cli import session as cli_session
from tl_cli.main import app as cli_app
from tl_core.auth import accounts, sessions
from tl_core.auth.errors import ForbiddenError
from tl_core.auth.module_grants import GrantModuleRole, grant_module_role
from tl_core.auth.queries import find_account
from tl_core.services.errors import RecordNotFoundError
from tl_tui.app import TlApp
from tl_tui.embedded import EmbeddedClient
from tl_tui.widgets.intake_log import IntakeLogScreen
from typer.testing import CliRunner

_ROOT = Path(__file__).resolve().parents[2] / "packages"
for _tests in (_ROOT / "tl-modules/forms/tests", _ROOT / "tl-tui/tests"):
    if str(_tests) not in sys.path:
        sys.path.insert(0, str(_tests))

from forms_world import PASSWORD, SCOPE, World, intake_body  # noqa: E402
from helpers import settle, static_of  # noqa: E402

PROJECT = "P123"
FAKE_ULID = "01J000000000000000000000"
READERS = ("dora", "ada", "uma", "rob", "vera")
HOLDERS = ("dora", "ada")
USERS = ("uma", "rob", "vera")
ANSWER = "Zq-ladders-for-level-3"
PHONE = "555-0142"
SALT = "0f" * 16
MAC = "cd" * 32
SIZE = (170, 44)
BODY = intake_body(topic=ANSWER, phone=PHONE)


class Rig:
    def __init__(self, h: Harness, world: World) -> None:
        self.h = h
        self.world = world
        self.tokens: dict[str, str] = {}
        self.items: dict[str, str] = {}
        self.codes: dict[str, str] = {}
        self.hashes: list[str] = []
        self.template = ""
        self.contexts: dict[str, str | None] = {}
        self.seen: list[str] = []  # every text a read returned, for the secret scan

    def get(self, who: str | None, path: str, **params: Any) -> Any:
        client = self.h.client_for(None)
        if who is not None:
            client.headers.update({"Authorization": f"Bearer {self.tokens[who]}"})
        got = client.get(path, params=params)
        self.seen.append(got.text)
        return got


def _same(a: Any, b: Any) -> bool:
    return (
        a.status_code == b.status_code
        and a.content == b.content
        and a.headers.get("content-type") == b.headers.get("content-type")
    )


@pytest.fixture(scope="module")
def rig(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Rig]:
    h = Harness.build(tmp_path_factory.mktemp("forms-intake-walk"))
    world = World(h.target or h.db)
    world.people()
    r = Rig(h, world)
    with h.backend(False) as uow:
        bot = accounts.create_account(
            uow,
            username="bot",
            display_name="Bot",
            kind="agent",
            roles=["user"],
            password=None,
            by="svc:test",
        )
        _, token = accounts.issue_agent_token(
            uow,
            account_id=bot.account_id,
            label="intake",
            expires_at=datetime.now(UTC) + timedelta(days=1),
            by="svc:test",
        )
    with h.backend(False) as uow:
        dora = find_account(uow.conn(), username="dora")
        assert dora is not None
        grant_module_role(
            uow,
            GrantModuleRole(
                actor="user:ada",
                source="test",
                account_id=dora.account_id,
                project=SCOPE,
                module="forms",
                role="superuser",
                reason="test",
            ),
        )
    r.tokens = {n: sessions.sign_in(h.backend, username=n, password=PASSWORD)[1] for n in READERS}
    r.tokens["bot"] = token
    template = world.intake_template()
    contexts = {
        "restricted": world.hidden_record("restricted"),
        "privileged": world.hidden_record("privileged"),
        "open": world.record("awp.IWP", "IWP-2"),
        "none": None,
    }
    r.template = template
    r.contexts = contexts
    r.codes = {n: world.stage_code(template, context_id=c) for n, c in contexts.items()}
    r.items = {n: world.stage_item(c, BODY) for n, c in r.codes.items()}
    r.items["rejected"] = world.stage_item(r.codes["none"], BODY)
    world.call("dora", "RejectIntakeItem", item_id=r.items["rejected"], reason="spam")
    r.hashes = [
        str(x["code_hash"]) for x in world.rows("SELECT code_hash FROM cur_forms_intake_code")
    ]
    yield r
    h.close()


def _ids(response: Any) -> set[str]:
    return {row["id"] for row in response.json()["rows"]}


def _visible(*names: str) -> set[str]:
    return set(names)


# --- the routes -----------------------------------------------------------------------------


def test_a_controller_reads_every_item_and_the_answers_of_a_pending_one(rig: Rig) -> None:
    listed = rig.get("dora", "/forms/intake/items", project=PROJECT)
    assert listed.status_code == 200 and listed.json()["total"] == 5
    assert _ids(listed) == set(rig.items.values())
    one = rig.get("dora", f"/forms/intake/items/{rig.items['open']}", project=PROJECT)
    assert one.status_code == 200
    assert one.json()["row"]["state"] == "Pending"
    assert {a["q"] for a in one.json()["answers"]} >= {"topic"}
    gone = rig.get("dora", f"/forms/intake/items/{rig.items['rejected']}", project=PROJECT)
    assert gone.json()["row"]["state"] == "Rejected" and gone.json()["answers"] is None


def test_an_administrator_does_not_read_a_privileged_item_and_reads_the_rest(rig: Rig) -> None:
    listed = rig.get("ada", "/forms/intake/items", project=PROJECT)
    shown = _ids(listed)
    assert rig.items["privileged"] not in shown and listed.json()["total"] == 4
    assert shown == set(rig.items.values()) - {rig.items["privileged"]}
    assert (
        rig.get(
            "ada", f"/forms/intake/items/{rig.items['restricted']}", project=PROJECT
        ).status_code
        == 200
    )
    codes = rig.get("ada", "/forms/intake/codes", project=PROJECT)
    assert {c["id"] for c in codes.json()["rows"]} == set(rig.codes.values()) - {
        rig.codes["privileged"]
    }
    assert codes.json()["total"] == 3
    pending = {c["id"]: c["pending"] for c in codes.json()["rows"]}
    assert pending[rig.codes["none"]] == 1  # the rejected one is not Pending


def test_a_hidden_item_is_a_missing_one_on_the_detail_route(rig: Rig) -> None:
    missing = rig.get("ada", f"/forms/intake/items/{FAKE_ULID}", project=PROJECT)
    assert missing.status_code == 404
    hidden = rig.get("ada", f"/forms/intake/items/{rig.items['privileged']}", project=PROJECT)
    assert _same(hidden, missing)
    assert rig.items["privileged"] not in hidden.text
    other = rig.get("ada", f"/forms/intake/items/{rig.items['open']}", project="P999")
    assert other.status_code in (403, 404)
    foreign = rig.get("dora", f"/forms/intake/items/{rig.items['open']}", project="P999")
    never = rig.get("dora", f"/forms/intake/items/{FAKE_ULID}", project="P999")
    assert _same(foreign, never)  # another project's item is a missing one


@pytest.mark.parametrize("who", USERS)
def test_a_plain_user_holds_no_intake_word_and_learns_nothing_about_an_id(
    rig: Rig, who: str
) -> None:
    refused = rig.get(who, f"/forms/intake/items/{FAKE_ULID}", project=PROJECT)
    assert refused.status_code == 403
    for key in ("open", "privileged", "rejected"):
        got = rig.get(who, f"/forms/intake/items/{rig.items[key]}", project=PROJECT)
        assert _same(got, refused)
    for path in ("/forms/intake/items", "/forms/intake/codes"):
        assert rig.get(who, path, project=PROJECT).status_code == 403


def test_an_agent_is_refused_on_every_route_before_any_lookup(rig: Rig) -> None:
    routes = (
        "/forms/intake/items",
        "/forms/intake/codes",
        f"/forms/intake/items/{rig.items['open']}",
        f"/forms/intake/items/{FAKE_ULID}",
    )
    seen = {rig.get("bot", p, project=PROJECT).content for p in routes[2:]}
    assert len(seen) == 1
    for path in routes:
        assert rig.get("bot", path, project=PROJECT).status_code == 403
        assert rig.get(None, path, project=PROJECT).status_code == 401


def test_lists_filter_before_the_limit_and_by_state(rig: Rig) -> None:
    page = rig.get("ada", "/forms/intake/items", project=PROJECT, limit=2)
    assert len(page.json()["rows"]) == 2 and page.json()["total"] == 4
    pending = rig.get("ada", "/forms/intake/items", project=PROJECT, state="Pending")
    assert pending.json()["total"] == 3
    by_code = rig.get("dora", "/forms/intake/items", project=PROJECT, code=rig.codes["none"])
    assert _ids(by_code) == {rig.items["none"], rig.items["rejected"]}


def test_no_route_is_public_and_no_agent_tool_names_intake() -> None:
    from tl_mod_forms import tools as forms_tools

    names = re.findall(r"intake", Path(forms_tools.__file__).read_text(encoding="utf-8"), re.I)
    assert names == []  # the module's MCP tools say nothing of intake


# --- the CLI --------------------------------------------------------------------------------


def _cli(rig: Rig, who: str, tmp: Path, *args: str) -> tuple[int, str]:
    target = rig.world.db
    env = {"TL_DB": str(target), "TL_SESSION_FILE": str(tmp / f"{who}.json"), "TL_ENV": "test"}
    actor = "agent:bot" if who == "bot" else f"user:{who}"
    with mock.patch.dict(os.environ, env):
        cli_session.save(
            cli_session.StoredSession(
                target=cli_session.db_target(target),
                username=who,
                actor=actor,
                expires_at="2099-01-01T00:00:00Z",
                token=rig.tokens[who],
            )
        )
        result = CliRunner().invoke(cli_app, list(args), env=env)
    rig.seen.append(result.output)
    return result.exit_code, result.output


def test_the_cli_answers_a_hidden_item_as_a_missing_one(rig: Rig, tmp_path: Path) -> None:
    for verb, extra in (
        ("show", ()),
        ("reject", ("--reason", "spam")),
        ("accept", ("--as", "SubmitForm", "--args-file", str(tmp_path / "a.json"))),
    ):
        (tmp_path / "a.json").write_text("{}", encoding="utf-8")
        h_code, h_out = _cli(
            rig,
            "ada",
            tmp_path,
            "intake",
            verb,
            rig.items["privileged"],
            "--project",
            PROJECT,
            *extra,
        )
        m_code, m_out = _cli(
            rig, "ada", tmp_path, "intake", verb, FAKE_ULID, "--project", PROJECT, *extra
        )
        assert (h_code, h_out) == (m_code, m_out), verb
        assert h_code == 1 and rig.items["privileged"] not in h_out
    still = rig.world.rows(
        "SELECT status FROM cur_core_record WHERE id = :i", i=rig.items["privileged"]
    )[0]["status"]
    assert still in (None, "Pending")


def test_the_cli_lists_leave_out_the_hidden(rig: Rig, tmp_path: Path) -> None:
    code, out = _cli(rig, "ada", tmp_path, "intake", "ls", "--project", PROJECT)
    assert code == 0 and out.splitlines()[0] == "intake items: 4"
    assert rig.items["privileged"] not in out and rig.items["open"] in out
    assert ANSWER not in out and PHONE not in out  # a list holds no answer
    code, out = _cli(rig, "dora", tmp_path, "intake", "ls", "--project", PROJECT)
    assert out.splitlines()[0] == "intake items: 5"
    code, out = _cli(rig, "ada", tmp_path, "intake", "code", "ls", "--project", PROJECT)
    assert code == 0 and out.splitlines()[0] == "intake codes: 3"
    assert rig.codes["privileged"] not in out


def test_the_cli_shows_a_pending_items_answers_and_no_other_verb_does(
    rig: Rig, tmp_path: Path
) -> None:
    code, out = _cli(
        rig, "dora", tmp_path, "intake", "show", rig.items["open"], "--project", PROJECT
    )
    assert code == 0 and ANSWER in out and "Pending" in out
    code, out = _cli(
        rig, "dora", tmp_path, "intake", "show", rig.items["rejected"], "--project", PROJECT
    )
    assert code == 0 and "rejected spam" in out and ANSWER not in out


@pytest.mark.parametrize("who", (*USERS, "bot"))
def test_the_cli_refuses_a_user_and_an_agent_the_same_way_for_every_id(
    rig: Rig, tmp_path: Path, who: str
) -> None:
    outs = {
        _cli(rig, who, tmp_path, "intake", "show", i, "--project", PROJECT)
        for i in (rig.items["open"], rig.items["privileged"], FAKE_ULID)
    }
    assert len(outs) == 1 and next(iter(outs))[0] == 1
    for args in (("ls",), ("code", "ls"), ("purge",)):
        code, out = _cli(rig, who, tmp_path, "intake", *args, "--project", PROJECT)
        assert code == 1 and "forbidden" in out


def test_a_hidden_context_is_an_absent_context_on_issue(rig: Rig, tmp_path: Path) -> None:
    def key_of(record: str | None) -> str:
        return str(
            rig.world.rows("SELECT key FROM cur_core_record WHERE id = :i", i=record)[0]["key"]
        )

    template = str(
        rig.world.rows("SELECT key FROM cur_core_record WHERE id = :i", i=rig.template)[0]["key"]
    )
    args = (
        "intake", "code", "issue", "--project", PROJECT, "--template", template, "--heading", "H",
        "--controller-role", "controller", "--expires-on", rig.world.days_from_now(5),
    )  # fmt: skip
    hidden = _cli(rig, "ada", tmp_path, *args, "--context", key_of(rig.contexts["privileged"]))
    absent = _cli(rig, "ada", tmp_path, *args, "--context", "NO-SUCH-0001")
    assert hidden == absent and hidden[0] == 1 and "code " not in hidden[1]
    visible = _cli(rig, "ada", tmp_path, *args, "--context", key_of(rig.contexts["open"]))
    assert visible[0] == 0 and visible[1].splitlines()[1].startswith("code ")
    printed = visible[1].splitlines()[1].removeprefix("code ")
    rig.seen.pop()  # the one place a raw code is meant to be printed: it is checked below
    rest = (
        "\n".join(rig.seen)
        + rig.world.rows("SELECT group_concat(payload) AS p FROM events")[0]["p"]
    )
    assert printed not in rest and printed.replace("-", "") not in rest
    for user in USERS:
        refused = _cli(rig, user, tmp_path, *args)
        assert refused[0] == 1 and "code " not in refused[1] and printed not in refused[1]


# --- the terminal ---------------------------------------------------------------------------


def _client(rig: Rig, who: str) -> EmbeddedClient:
    actor = "agent:bot" if who == "bot" else f"user:{who}"
    return EmbeddedClient(rig.h.backend, actor=actor)


def test_the_embedded_client_reads_the_queue_as_the_viewer(rig: Rig) -> None:
    dora = _client(rig, "dora")
    assert dora.list_intake_items(PROJECT).total == 5
    detail = dora.get_intake_item(PROJECT, rig.items["open"])
    assert detail.answers and ANSWER in json.dumps(detail.answers)
    ada = _client(rig, "ada")
    assert ada.list_intake_items(PROJECT).total == 4
    with pytest.raises(RecordNotFoundError) as hidden:
        ada.get_intake_item(PROJECT, rig.items["privileged"])
    with pytest.raises(RecordNotFoundError) as missing:
        ada.get_intake_item(PROJECT, FAKE_ULID)
    assert str(hidden.value) == str(missing.value)
    with pytest.raises(ValueError, match="agent_must_propose"):
        _client(rig, "bot")  # an agent is not a terminal reader
    for who in USERS:
        client = _client(rig, who)
        with pytest.raises(ForbiddenError):
            client.list_intake_items(PROJECT)
        with pytest.raises(ForbiddenError):
            client.get_intake_item(PROJECT, rig.items["open"])


def _observe(rig: Rig, who: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    app = TlApp(_client(rig, who), scope=SCOPE, actor=f"user:{who}")

    async def go() -> None:
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot)
            app.action_intake()
            await settle(pilot)
            log = app.screen
            assert isinstance(log, IntakeLogScreen)
            out["rows"] = {r.id for r in log.shown}
            out["status"] = static_of(log, "#log-status")
            out["panel"] = " ".join(str(log.panel_text(r)) for r in log.shown)
            out["rendered"] = str(app.screen_stack)

    asyncio.run(go())
    rig.seen.append(out["panel"] + out["status"])
    return out


def test_the_intake_log_lists_what_the_viewer_may_read_and_a_user_sees_a_refusal(rig: Rig) -> None:
    dora = _observe(rig, "dora")
    assert dora["rows"] == set(rig.items.values())
    ada = _observe(rig, "ada")
    assert ada["rows"] == set(rig.items.values()) - {rig.items["privileged"]}
    assert rig.items["privileged"][-8:] not in ada["panel"]
    vera = _observe(rig, "vera")
    assert vera["rows"] == set()


# --- no secret ------------------------------------------------------------------------------


def test_no_read_carries_a_code_hash_a_salt_a_mac_or_the_stored_body(rig: Rig) -> None:
    assert rig.hashes and len(rig.seen) > 20
    blob = "\n".join(rig.seen)
    for secret in (*rig.hashes, SALT, MAC, BODY):
        assert secret not in blob
    for word in ("code_hash", "body_mac", "salt"):
        assert word not in blob
    # the answers are in the detail of a Pending item and in no list
    assert ANSWER in blob and PHONE in blob
    lists = "\n".join(
        rig.get(who, path, project=PROJECT).text
        for who in HOLDERS
        for path in ("/forms/intake/items", "/forms/intake/codes")
    )
    assert ANSWER not in lists and PHONE not in lists
