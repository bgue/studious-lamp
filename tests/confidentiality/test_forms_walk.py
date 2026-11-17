"""V3-F1a walk: every forms read route and every `tl form` read, as five kinds of reader.

Readers: the author (``uma``), another user (``rob``), the document controller (``dora``: reads
restricted records), an administrator (``ada``), and an agent token (``bot``, refused before any
lookup). A submission of a privileged template and a draft are the author's alone, so for every
other reader each of them answers exactly as a key that never existed does: same status, same
headers, same body, byte for byte (the CLI echoes the caller's own reference and nothing else).
Lists and counts leave them out. A record the viewer may not read offers no form, as a missing
one does.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
from harness import Harness
from sqlalchemy import text
from tl_adapters.db import open_uow
from tl_cli import session as cli_session
from tl_cli.main import app as cli_app
from tl_core.auth import accounts, sessions
from typer.testing import CliRunner

_FORMS_TESTS = str(Path(__file__).resolve().parents[2] / "packages/tl-modules/forms/tests")
if _FORMS_TESTS not in sys.path:
    sys.path.insert(0, _FORMS_TESTS)

from forms_world import PASSWORD, World, two_fields  # noqa: E402

PROJECT = "P123"
FAKE_ULID = "01J000000000000000000000"
MISSING_KEY = "P123-FRM-9999"
READERS = ("uma", "rob", "dora", "ada")
OTHERS = ("rob", "dora", "ada")


class Rig:
    def __init__(self, h: Harness, world: World) -> None:
        self.h = h
        self.world = world
        self.tokens: dict[str, str] = {}
        self.ids: dict[str, str] = {}
        self.keys: dict[str, str] = {}

    def get(self, who: str | None, path: str, **params: Any) -> Any:
        client = self.h.client_for(None)
        if who is not None:
            client.headers.update({"Authorization": f"Bearer {self.tokens[who]}"})
        return client.get(path, params=params)


def _same(a: Any, b: Any) -> bool:
    """Status, content type and body are the same bytes."""
    return (
        a.status_code == b.status_code
        and a.content == b.content
        and a.headers.get("content-type") == b.headers.get("content-type")
    )


@pytest.fixture(scope="module")
def rig(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Rig]:
    h = Harness.build(tmp_path_factory.mktemp("forms-walk"))
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
            label="forms",
            expires_at=datetime.now(UTC) + timedelta(days=1),
            by="svc:test",
        )
    r.tokens = {n: sessions.sign_in(h.backend, username=n, password=PASSWORD)[1] for n in READERS}
    r.tokens["bot"] = token
    plain = world.template(fields=two_fields())
    secret = world.template(fields=two_fields(), answer_class="privileged")
    r.ids["plain_template"] = plain
    r.ids["secret_template"] = secret
    r.keys["open"] = str(world.submit("uma", plain).key)
    r.keys["secret"] = str(world.submit("uma", secret).key)
    r.ids["draft"] = str(world.save("uma", plain).stream_id)
    r.ids["hidden_record"] = world.hidden_record("restricted")
    r.keys["hidden_record"] = str(
        world.rows("SELECT key FROM cur_core_record WHERE id = :i", i=r.ids["hidden_record"])[0][
            "key"
        ]
    )
    yield r
    h.close()


def _keys_of(response: Any) -> set[str]:
    return {row["key"] for row in response.json()["rows"] if row["key"]}


# --- the routes -----------------------------------------------------------------------------


@pytest.mark.parametrize("who", OTHERS)
def test_a_hidden_submission_is_a_missing_one_on_the_detail_route(rig: Rig, who: str) -> None:
    missing = rig.get(who, f"/forms/submissions/{MISSING_KEY}", project=PROJECT)
    assert missing.status_code == 404
    hidden = rig.get(who, f"/forms/submissions/{rig.keys['secret']}", project=PROJECT)
    assert _same(hidden, missing)
    by_id = rig.get(who, f"/forms/submissions/{rig.ids['draft']}", project=PROJECT)
    gone = rig.get(who, f"/forms/submissions/{FAKE_ULID}", project=PROJECT)
    assert _same(by_id, gone)  # another person's draft
    assert rig.keys["secret"] not in hidden.text and rig.ids["draft"] not in by_id.text


def test_the_author_reads_the_submission_and_the_draft(rig: Rig) -> None:
    for ref in (rig.keys["secret"], rig.keys["open"], rig.ids["draft"]):
        got = rig.get("uma", f"/forms/submissions/{ref}", project=PROJECT)
        assert got.status_code == 200, got.text
        assert got.json()["answers"]


@pytest.mark.parametrize("who", OTHERS)
def test_lists_leave_out_the_hidden_and_the_drafts(rig: Rig, who: str) -> None:
    listed = rig.get(who, "/forms/submissions", project=PROJECT)
    assert listed.status_code == 200
    assert _keys_of(listed) == {rig.keys["open"]}
    assert listed.json()["total"] == 1
    drafts = rig.get(who, "/forms/submissions", project=PROJECT, state="Draft")
    assert drafts.json() == {"rows": [], "total": 0}
    secret = rig.get(
        who, "/forms/submissions", project=PROJECT, template=rig.ids["secret_template"]
    )
    assert secret.json() == {"rows": [], "total": 0}


def test_the_authors_list_has_everything_of_theirs(rig: Rig) -> None:
    listed = rig.get("uma", "/forms/submissions", project=PROJECT)
    assert _keys_of(listed) == {rig.keys["open"], rig.keys["secret"]}
    assert listed.json()["total"] == 3  # the draft has no key and is counted


@pytest.mark.parametrize("who", OTHERS)
def test_the_form_of_a_hidden_record_is_the_form_of_a_missing_one(rig: Rig, who: str) -> None:
    hidden = rig.get(who, f"/forms/for/{rig.keys['hidden_record']}", project=PROJECT)
    missing = rig.get(who, "/forms/for/P123-NOPE-0001", project=PROJECT)
    assert hidden.status_code == 404 and _same(hidden, missing)


def test_templates_read_and_project_as_json_schema_and_surveyjs(rig: Rig) -> None:
    template = rig.get("rob", "/forms/templates")
    assert template.status_code == 200 and template.json()["total"] == 2
    row = next(r for r in template.json()["rows"] if r["id"] == rig.ids["plain_template"])
    base = f"/forms/templates/{row['key']}/versions/{row['version']}"
    schema = rig.get("rob", base, **{"as": "jsonschema"})
    assert schema.status_code == 200 and schema.json()["type"] == "array"
    survey = rig.get("rob", base, **{"as": "surveyjs"})
    assert survey.status_code == 200 and survey.json()["model"]["pages"]
    tag = schema.headers["etag"]
    again = rig.h.client_for(None)
    again.headers.update({"Authorization": f"Bearer {rig.tokens['rob']}", "If-None-Match": tag})
    assert again.get(base, params={"as": "jsonschema"}).status_code == 304
    assert survey.headers["etag"] != tag
    miss = rig.get("rob", "/forms/templates/TPL-9999/versions/1")
    assert miss.status_code == 404
    assert rig.get("rob", f"{base[:-1]}9").status_code == 404


ROUTES = (
    ("/forms/templates", {}),
    ("/forms/templates/TPL-0001/versions/1", {}),
    ("/forms/for/PUN-1", {"project": PROJECT}),
    ("/forms/submissions", {"project": PROJECT}),
    ("/forms/submissions/P123-FRM-0001", {"project": PROJECT}),
)


@pytest.mark.parametrize(("path", "params"), ROUTES)
def test_an_agent_is_refused_and_a_stranger_is_signed_out(
    rig: Rig, path: str, params: dict[str, Any]
) -> None:
    refused = rig.get("bot", path, **params)
    assert refused.status_code == 403
    assert rig.get("bot", path.replace("0001", "9999"), **params).content == refused.content
    assert rig.get(None, path, **params).status_code == 401


# --- the CLI --------------------------------------------------------------------------------


def _cli(rig: Rig, who: str, tmp: Path, *args: str) -> tuple[int, str]:
    target = rig.world.db
    env = {"TL_DB": str(target), "TL_SESSION_FILE": str(tmp / f"{who}.json"), "TL_ENV": "test"}
    with mock.patch.dict(os.environ, env):
        cli_session.save(
            cli_session.StoredSession(
                target=cli_session.db_target(target),
                username=who,
                actor=f"user:{who}",
                expires_at="2099-01-01T00:00:00Z",
                token=rig.tokens[who],
            )
        )
        result = CliRunner().invoke(cli_app, list(args), env=env)
    return result.exit_code, result.output


@pytest.mark.parametrize("who", OTHERS)
def test_the_cli_answers_a_hidden_submission_as_a_missing_one(
    rig: Rig, who: str, tmp_path: Path
) -> None:
    for hidden, never in (
        (rig.keys["secret"], "P123-FRM-9998"),
        (rig.ids["draft"], FAKE_ULID),
    ):
        h_code, h_out = _cli(
            rig, who, tmp_path, "form", "show", hidden, "--submission", "--project", PROJECT
        )
        m_code, m_out = _cli(
            rig, who, tmp_path, "form", "show", never, "--submission", "--project", PROJECT
        )
        assert (h_code, h_out.replace(hidden, "<ref>")) == (m_code, m_out.replace(never, "<ref>"))
        assert h_code == 1 and "no submission" in h_out
        # reviewing one is the same miss
        r_code, r_out = _cli(
            rig, who, tmp_path, "form", "review", hidden, "accept", "--project", PROJECT
        )
        q_code, q_out = _cli(
            rig, who, tmp_path, "form", "review", never, "accept", "--project", PROJECT
        )
        assert (r_code, r_out.replace(hidden, "<ref>")) == (q_code, q_out.replace(never, "<ref>"))


@pytest.mark.parametrize("who", OTHERS)
def test_the_cli_lists_leave_out_the_hidden(rig: Rig, who: str, tmp_path: Path) -> None:
    code, out = _cli(rig, who, tmp_path, "form", "ls", "--submissions", "--project", PROJECT)
    assert code == 0 and out.splitlines()[0] == "form submissions: 1"
    assert rig.keys["open"] in out and rig.keys["secret"] not in out
    code, out = _cli(rig, who, tmp_path, "form", "drafts", "--project", PROJECT)
    assert code == 0 and out.splitlines() == ["form drafts: 0"]


def test_the_cli_author_sees_the_draft_and_the_secret(rig: Rig, tmp_path: Path) -> None:
    code, out = _cli(rig, "uma", tmp_path, "form", "drafts", "--project", PROJECT)
    assert code == 0 and rig.ids["draft"] in out
    code, out = _cli(
        rig,
        "uma",
        tmp_path,
        "form",
        "show",
        rig.keys["secret"],
        "--submission",
        "--project",
        PROJECT,
    )
    assert code == 0 and "topic" in out


def test_the_cli_templates_list_and_show(rig: Rig, tmp_path: Path) -> None:
    code, out = _cli(rig, "rob", tmp_path, "form", "ls")
    assert code == 0 and out.splitlines()[0] == "form templates: 2"
    code, out = _cli(rig, "rob", tmp_path, "form", "show", "TPL-0001", "--as", "jsonschema")
    assert code == 0 and json.loads(out)["type"] == "array"
    code, out = _cli(rig, "rob", tmp_path, "form", "show", "TPL-9999")
    assert code == 1 and "no template" in out


def test_the_fixture_rows_are_what_the_reader_counts(rig: Rig) -> None:
    with open_uow(rig.world.db, readonly=True) as uow:
        total = uow.conn().execute(text("SELECT count(*) FROM cur_forms_submission")).scalar_one()
    assert total == 3
