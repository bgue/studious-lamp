"""V3-F1s walk: the form of an inspection and of a permit, as five kinds of reader.

The sources (``tl_mod_quality.form_source``, ``tl_mod_permits.form_source``) answer a binding for a
record the reader can see. A hidden record answers exactly as a key that never existed does on
``GET /forms/for/{key}`` and on ``tl form for`` (same status, same bytes; the CLI echoes the
caller's own reference and nothing else). Readers: ``uma`` and ``rob`` (users), ``vera`` (a user
with a viewer grant), ``ada`` (an administrator) and ``dora`` (the document controller, who reads
restricted records and is the positive control). Then the fills: an inspection's result and a
permit's ticks are recorded through the module's own typed command, in one unit of work; the
command's own access word decides and its refusal is its own; a failing answer set writes nothing.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
from harness import Harness
from sqlalchemy import text
from tl_adapters.db import open_uow
from tl_cli import session as cli_session
from tl_cli.main import app as cli_app
from tl_core import confidentiality as cf
from tl_core.auth import sessions
from tl_core.auth.module_grants import GrantModuleRole, grant_module_role
from tl_core.auth.module_roles import require_command_access
from tl_core.auth.queries import find_account
from tl_core.forms import rules
from tl_core.modules import module_commands
from tl_core.services.commands import Command
from tl_mod_correspondence.handlers.confidentiality import (
    SetCorrespondenceConfidentiality,
    handle_set_confidentiality,
)
from tl_mod_correspondence.handlers.create import create_item
from tl_mod_correspondence.handlers.models import Recipient
from tl_mod_correspondence.testing import frozen_today
from typer.testing import CliRunner

_FORMS_TESTS = str(Path(__file__).resolve().parents[2] / "packages/tl-modules/forms/tests")
if _FORMS_TESTS not in sys.path:
    sys.path.insert(0, _FORMS_TESTS)

from forms_world import PASSWORD, SCOPE, World  # noqa: E402

PROJECT = "P123"
MISSING = "P123-NOPE-0001"
READERS = ("uma", "rob", "vera", "ada", "dora")
HIDDEN_FROM = ("uma", "rob", "vera", "ada")  # dora reads restricted records
QUESTIONS: list[dict[str, Any]] = [
    {
        "id": "q1",
        "text": "Gauge fitted?",
        "kind": "yes_no_na",
        "required": True,
        "unit": None,
        "min": None,
        "max": None,
        "choices": None,
        "fails_when": "no",
    },
    {
        "id": "q2",
        "text": "Test pressure",
        "kind": "number",
        "required": False,
        "unit": "bar",
        "min": 1,
        "max": 10,
        "choices": None,
        "fails_when": "out_of_range",
    },
]
FORBIDDEN_RECORD = (
    "error: forbidden: RecordInspectionResult needs the user access word for quality "
    "on project:P123"
)


class Rig:
    def __init__(self, h: Harness, world: World) -> None:
        self.h = h
        self.world = world
        self.tokens: dict[str, str] = {}
        self.keys: dict[str, str] = {}
        self.ids: dict[str, str] = {}

    def get(self, who: str | None, path: str, **params: Any) -> Any:
        client = self.h.client_for(None)
        if who is not None:
            client.headers.update({"Authorization": f"Bearer {self.tokens[who]}"})
        return client.get(path, params=params)

    def call(self, who: str, name: str, **fields: Any) -> Any:
        """A module command as ``who`` (access word, then the handler as that person's viewer)."""
        row = next(c for c in module_commands() if c.name == name)
        cmd = row.model(actor=f"user:{who}", source="test", scope=SCOPE, **fields)
        with open_uow(self.world.db) as uow:
            conn = uow.conn()
            require_command_access(conn, cmd)
            with cf.use_viewer(cf.viewer_for_actor(conn, cmd.actor)):
                return row.handler(uow, cmd)

    def key_of(self, record_id: str) -> str:
        return str(
            self.world.rows("SELECT key FROM cur_core_record WHERE id = :i", i=record_id)[0]["key"]
        )

    def scalar(self, sql: str, **params: Any) -> Any:
        with open_uow(self.world.db, readonly=True) as uow:
            return uow.conn().execute(text(sql), params).scalar_one()

    def events(self) -> int:
        return int(self.scalar("SELECT count(*) FROM events"))

    def state(self, record_id: str, initial: str) -> str:
        with open_uow(self.world.db, readonly=True) as uow:
            found = (
                uow.conn()
                .execute(
                    text("SELECT state FROM cur_workflow_state WHERE record_id = :i"),
                    {"i": record_id},
                )
                .scalar_one_or_none()
            )
        return initial if found is None else str(found)


def _privileged_record(world: World) -> str:
    """A correspondence item only ``dora`` and ``eve`` may read (privileged: not even the
    administrator)."""
    cmd = Command(actor="user:dora", source="test", scope=SCOPE)
    with cf.system_view(), frozen_today("2026-10-19"), open_uow(world.db) as uow:
        made = create_item(
            uow,
            cmd,
            subject="Secret",
            direction="in",
            medium="letter",
            received_via="manual",
            to=[Recipient(name="Someone")],
            body="Body",
            received_on="2026-10-19",
            received=True,
        )
    with cf.system_view(), frozen_today("2026-10-19"), open_uow(world.db) as uow:
        handle_set_confidentiality(
            uow,
            SetCorrespondenceConfidentiality(
                actor="user:dora",
                source="test",
                scope=SCOPE,
                stream_id=made.stream_id,
                to_class="privileged",
                grant=["user:dora", "user:eve"],
                reason="test",
            ),
        )
    return str(made.stream_id)


def _grant(rig: Rig, name: str, module: str, role: str) -> None:
    with open_uow(rig.world.db) as uow:
        found = find_account(uow.conn(), username=name)
        assert found is not None
        grant_module_role(
            uow,
            GrantModuleRole(
                actor="user:ada",
                source="test",
                account_id=found.account_id,
                project=SCOPE,
                module=module,
                role=role,
                reason="test",
            ),
        )


@pytest.fixture(scope="module")
def rig(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Rig]:
    h = Harness.build(tmp_path_factory.mktemp("forms-sources"))
    world = World(h.target or h.db)
    world.people()
    world.person("vic", ("user",))  # holds no quality or permits word below a viewer grant
    world.person("eve", ("user", "document_controller"))
    r = Rig(h, world)
    for module in ("quality", "permits"):
        _grant(r, "vic", module, "viewer")
        _grant(r, "vera", module, "viewer")
        _grant(r, "eve", module, "superuser")
    r.tokens = {
        n: sessions.sign_in(h.backend, username=n, password=PASSWORD)[1]
        for n in (*READERS, "vic", "eve")
    }
    checklist = str(
        r.call("uma", "CreateChecklist", title="Pre-check", questions=QUESTIONS).stream_id
    )
    r.call("ada", "PublishChecklist", checklist=checklist)
    r.ids["checklist"] = checklist
    secret = _privileged_record(world)
    iwp = world.record("awp.IWP", "IWP-1")

    def scheduled(subject: str, who: str, name: str) -> str:
        item = str(
            r.call(who, "PlanInspection", subject_id=subject, title=name, point="hold").stream_id
        )
        r.call(
            who,
            "ScheduleInspection",
            inspection=item,
            checklist=checklist,
            scheduled_for="2026-12-01",
            inspector="M. Okafor",
        )
        return item

    for name in ("open", "fail", "short", "vic", "done"):
        r.ids[f"insp_{name}"] = scheduled(iwp, "uma", f"Inspection {name}")
    r.ids["insp_hidden"] = scheduled(secret, "dora", "Inspection hidden")
    r.ids["insp_planned"] = str(
        r.call(
            "uma", "PlanInspection", subject_id=iwp, title="Not scheduled", point="hold"
        ).stream_id
    )

    def permit(name: str, who: str = "rob", approver: str = "ada", **more: Any) -> str:
        made = r.call(
            who,
            "RequestPermit",
            permit_type="general",
            area="A1",
            location_text="Pump room",
            work_description=f"Work {name}",
            holder="Rob",
            needed_from="2026-11-01",
            needed_until="2026-12-31",
            **more,
        )
        r.call(approver, "ApprovePermit", permit=str(made.stream_id))
        return str(made.stream_id)

    for name in ("open", "unticked", "refused"):
        r.ids[f"permit_{name}"] = permit(name)
    r.ids["permit_hidden"] = permit("hidden", who="dora", approver="eve", for_record_id=secret)
    r.ids["permit_requested"] = str(
        r.call(
            "rob",
            "RequestPermit",
            permit_type="general",
            area="A1",
            location_text="Pump room",
            work_description="Not approved",
            holder="Rob",
            needed_from="2026-11-01",
            needed_until="2026-12-31",
        ).stream_id
    )
    for k, v in list(r.ids.items()):
        if k.startswith(("insp_", "permit_")):
            r.keys[k] = r.key_of(v)
    yield r
    h.close()


def _same(a: Any, b: Any) -> bool:
    return (
        a.status_code == b.status_code
        and a.content == b.content
        and a.headers.get("content-type") == b.headers.get("content-type")
    )


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


# --- the binding, on the route ----------------------------------------------------------------


@pytest.mark.parametrize("who", READERS)
def test_an_inspection_and_a_permit_offer_their_form(rig: Rig, who: str) -> None:
    got = rig.get(who, f"/forms/for/{rig.keys['insp_open']}", project=PROJECT)
    assert got.status_code == 200, got.text
    body = got.json()
    assert body["available"] is True and body["command"] == "RecordInspectionResult"
    assert body["answers_arg"] == "answers" and body["fixed_args"] == {
        "inspection": rig.ids["insp_open"]
    }
    ref = body["template"]
    assert ref["source_type"] == "quality.Checklist" and ref["source_id"] == rig.ids["checklist"]
    assert ref["content_hash"] == rules.content_hash(QUESTIONS, fmt=1) and ref["fmt"] == 1
    assert isinstance(body["expected_version"], int)
    got = rig.get(who, f"/forms/for/{rig.keys['permit_open']}", project=PROJECT)
    assert got.status_code == 200, got.text
    body = got.json()
    assert body["command"] == "IssuePermit" and body["answers_arg"] == "precautions"
    assert body["template"]["source_type"] == "permits.PermitType"
    assert body["template"]["source_id"] == "general"


def test_a_record_that_takes_no_form_now_says_so_with_a_fixed_word(rig: Rig) -> None:
    for key, reason in (
        (rig.keys["insp_planned"], "no_checklist"),
        (rig.keys["permit_requested"], "not_approved"),
    ):
        got = rig.get("uma", f"/forms/for/{key}", project=PROJECT)
        assert got.status_code == 200
        assert got.json()["available"] is False and got.json()["reason"] == reason
        assert got.json()["template"] is None


@pytest.mark.parametrize("who", HIDDEN_FROM)
@pytest.mark.parametrize("record", ["insp_hidden", "permit_hidden"])
def test_a_hidden_record_offers_the_form_of_a_missing_one(rig: Rig, who: str, record: str) -> None:
    missing = rig.get(who, f"/forms/for/{MISSING}", project=PROJECT)
    hidden = rig.get(who, f"/forms/for/{rig.keys[record]}", project=PROJECT)
    assert missing.status_code == 404
    assert _same(hidden, missing)
    assert rig.keys[record] not in hidden.text


@pytest.mark.parametrize("record", ["insp_hidden", "permit_hidden"])
def test_the_cleared_reader_reads_the_form_of_what_the_others_cannot(rig: Rig, record: str) -> None:
    got = rig.get("dora", f"/forms/for/{rig.keys[record]}", project=PROJECT)
    assert got.status_code == 200 and got.json()["available"] is True


@pytest.mark.parametrize("who", HIDDEN_FROM)
@pytest.mark.parametrize("record", ["insp_hidden", "permit_hidden"])
def test_the_cli_answers_a_hidden_record_as_a_missing_one(
    rig: Rig, who: str, record: str, tmp_path: Path
) -> None:
    key = rig.keys[record]
    h_code, h_out = _cli(rig, who, tmp_path, "form", "for", key, "--project", PROJECT)
    m_code, m_out = _cli(rig, who, tmp_path, "form", "for", MISSING, "--project", PROJECT)
    assert (h_code, h_out.replace(key, "<ref>")) == (m_code, m_out.replace(MISSING, "<ref>"))
    assert h_code == 1 and "no form for" in h_out
    # sending a filled form to it is the same miss, and writes nothing
    before = rig.events()
    args = (
        "form",
        "record",
        "{}",
        "--project",
        PROJECT,
        "--answer",
        "q1=yes",
        "--answer",
        "jha_attached=yes",
    )
    r_code, r_out = _cli(rig, who, tmp_path, *[key if a == "{}" else a for a in args])
    n_code, n_out = _cli(rig, who, tmp_path, *[MISSING if a == "{}" else a for a in args])
    assert (r_code, r_out.replace(key, "<ref>")) == (n_code, n_out.replace(MISSING, "<ref>"))
    assert r_code == 1 and rig.events() == before


def test_the_cli_shows_the_form_of_a_visible_record(rig: Rig, tmp_path: Path) -> None:
    code, out = _cli(
        rig, "uma", tmp_path, "form", "for", rig.keys["insp_open"], "--project", PROJECT
    )
    assert code == 0, out
    assert "command RecordInspectionResult  answers go in answers" in out
    assert "q1  yes_no_na  required  Gauge fitted?" in out
    code, out = _cli(
        rig, "uma", tmp_path, "form", "for", rig.keys["permit_open"], "--project", PROJECT
    )
    assert code == 0 and "command IssuePermit  answers go in precautions" in out
    assert "jha_attached  yes_no_na  required" in out


# --- the fills --------------------------------------------------------------------------------


def _record(rig: Rig, who: str, tmp: Path, key: str, *answers: str) -> tuple[int, str]:
    args = ["form", "record", key, "--project", PROJECT]
    for item in answers:
        args += ["--answer", item]
    return _cli(rig, who, tmp, *args)


def test_an_inspection_result_is_recorded_through_its_form(rig: Rig, tmp_path: Path) -> None:
    item = rig.ids["insp_open"]
    before = rig.events()
    code, out = _record(rig, "uma", tmp_path, rig.keys["insp_open"], "q1=yes", "q2=5")
    assert (
        code == 0 and out.strip() == f"recorded RecordInspectionResult on {rig.keys['insp_open']}"
    )
    assert rig.state(item, "Planned") == "Done"
    row = rig.world.rows("SELECT * FROM cur_quality_inspection WHERE id = :i", i=item)[0]
    assert row["result"] == "accept" and row["recorded_by"] == "user:uma"
    kinds = rig.world.rows(
        "SELECT event_type FROM events ORDER BY seq DESC LIMIT :n", n=rig.events() - before
    )
    assert "Inspection.ResultRecorded" in {k["event_type"] for k in kinds}
    assert not any(k["event_type"].startswith("Submission.") for k in kinds)  # forms adds none
    assert rig.scalar("SELECT count(*) FROM cur_forms_submission") == 0
    # the record takes no second form
    code, out = _record(rig, "uma", tmp_path, rig.keys["insp_open"], "q1=yes")
    assert code == 1 and "that record takes no form now (already_recorded)" in out


def test_a_failed_answer_raises_its_punch_item_in_the_same_unit_of_work(
    rig: Rig, tmp_path: Path
) -> None:
    item = rig.ids["insp_fail"]
    code, out = _record(rig, "uma", tmp_path, rig.keys["insp_fail"], "q1=no", "q2=5")
    assert code == 0, out
    row = rig.world.rows("SELECT * FROM cur_quality_inspection WHERE id = :i", i=item)[0]
    assert row["result"] == "reject"
    raised = rig.world.rows(
        "SELECT count(*) AS n FROM cur_links WHERE to_id = :i AND relation = 'raised_against'",
        i=item,
    )
    assert raised[0]["n"] == 1


@pytest.mark.parametrize(
    ("answers", "problem"),
    [
        ((), "q1: answer required"),
        (("q1=maybe",), "q1:"),
        (("q1=yes", "q2=abc"), "q2:"),
        (("q1=yes", "q9=1"), "an answer: no such question"),
    ],
)
def test_a_failing_answer_set_is_refused_before_any_event(
    rig: Rig, tmp_path: Path, answers: tuple[str, ...], problem: str
) -> None:
    before = rig.events()
    code, out = _record(rig, "uma", tmp_path, rig.keys["insp_short"], *answers)
    assert code == 1 and "error: the answers have problems: " in out and problem in out
    assert rig.events() == before
    assert rig.state(rig.ids["insp_short"], "Planned") == "Scheduled"


def test_a_reader_without_the_word_gets_the_typed_commands_refusal(
    rig: Rig, tmp_path: Path
) -> None:
    before = rig.events()
    code, out = _record(rig, "vic", tmp_path, rig.keys["insp_vic"], "q1=yes")
    assert code == 1 and out.strip() == FORBIDDEN_RECORD
    assert rig.events() == before and rig.state(rig.ids["insp_vic"], "Planned") == "Scheduled"
    # the module's own CLI says the same for the same person and record
    own_code, own_out = _cli(
        rig, "vic", tmp_path, "insp", "record", rig.keys["insp_vic"], "--project", PROJECT,
        "--answer", "q1=yes",
    )  # fmt: skip
    assert own_code == 1 and own_out.strip() == FORBIDDEN_RECORD
    # and the refusal comes before the answers are looked at
    code, out = _record(rig, "vic", tmp_path, rig.keys["insp_vic"], "q1=maybe")
    assert out.strip() == FORBIDDEN_RECORD


def test_a_permits_ticks_are_recorded_through_its_form(rig: Rig, tmp_path: Path) -> None:
    permit = rig.ids["permit_open"]
    code, out = _record(rig, "ada", tmp_path, rig.keys["permit_open"], "jha_attached=yes")
    assert code == 0, out
    assert out.strip() == f"recorded IssuePermit on {rig.keys['permit_open']}"
    assert rig.state(permit, "Requested") == "Active"
    ticked = rig.scalar("SELECT precautions_json FROM cur_permits_permit WHERE id = :i", i=permit)
    assert "jha_attached" in ticked


def test_an_unticked_precaution_is_the_permit_commands_own_refusal(
    rig: Rig, tmp_path: Path
) -> None:
    before = rig.events()
    code, out = _record(rig, "ada", tmp_path, rig.keys["permit_unticked"], "jha_attached=no")
    assert code == 1 and out.startswith("error: "), out
    assert rig.events() == before
    assert rig.state(rig.ids["permit_unticked"], "Requested") == "Approved"


def test_a_permit_filled_without_the_issue_word_is_refused_by_the_permit_command(
    rig: Rig, tmp_path: Path
) -> None:
    before = rig.events()
    code, out = _record(rig, "uma", tmp_path, rig.keys["permit_refused"], "jha_attached=yes")
    expected = (
        "error: forbidden: IssuePermit needs the controller access word for permits on project:P123"
    )
    assert code == 1 and out.strip() == expected
    own_code, own_out = _cli(
        rig, "uma", tmp_path, "permit", "issue", rig.keys["permit_refused"], "--project", PROJECT,
        "--tick", "jha_attached",
    )  # fmt: skip
    assert own_code == 1 and own_out.strip() == expected
    assert rig.events() == before
    assert rig.state(rig.ids["permit_refused"], "Requested") == "Approved"


# --- hardening after the security review ------------------------------------------------------


@pytest.mark.parametrize("record", ["insp_open", "permit_open"])
def test_a_reader_without_the_module_view_word_gets_the_miss(rig: Rig, record: str) -> None:
    """A person always derives the view word from an account role, so the reader is an account
    that holds nothing (an actor with no account; a `user:` one would get the dev-ledger rule): ``views.form_for`` answers None as for a missing record."""
    from datetime import UTC, datetime

    from tl_mod_forms import views

    now = datetime.now(UTC)
    ghost = cf.Viewer(actor="agent:ghost", level=1, account="agent:ghost")
    with open_uow(rig.world.db, readonly=True) as uow:
        conn = uow.conn()
        mine = cf.viewer_for_actor(conn, "user:uma")
        assert views.form_for(conn, rig.ids[record], now=now, viewer=mine) is not None
        assert views.form_for(conn, rig.ids[record], now=now, viewer=ghost) is None
        assert views.form_for(conn, "01J000000000000000000000", now=now, viewer=ghost) is None


def test_the_typed_refusal_comes_before_the_state_of_the_record(rig: Rig, tmp_path: Path) -> None:
    code, _ = _record(rig, "uma", tmp_path, rig.keys["insp_done"], "q1=yes")
    assert code == 0
    before = rig.events()
    code, out = _record(rig, "vic", tmp_path, rig.keys["insp_done"], "q1=yes")
    assert code == 1 and out.strip() == FORBIDDEN_RECORD  # not "takes no form now"
    assert rig.events() == before


def test_record_refuses_a_record_of_another_scope_as_a_missing_one(rig: Rig) -> None:
    from datetime import UTC, datetime

    from tl_core.services.errors import RecordNotFoundError
    from tl_mod_forms import bound

    with open_uow(rig.world.db) as uow:
        viewer = cf.viewer_for_actor(uow.conn(), "user:uma")
        with pytest.raises(RecordNotFoundError, match="no record with that id"):
            bound.record(
                uow,
                record_id=rig.ids["insp_short"],
                answers=[],
                actor="user:uma",
                scope="project:P999",
                source="test",
                now=datetime.now(UTC),
                viewer=viewer,
            )
