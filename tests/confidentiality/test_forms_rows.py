"""Forms confidentiality rows (P2-FORMS CR1): subjects, the answer class, the join budget, intake
rows, and the proposals and cards that could carry a submission's answers (ADR-0016, ADR-0031).

Records are made through the forms commands and the correspondence module's own confidentiality
command; the intake rows, which have no command yet, go through the ledger as events.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
from sqlalchemy import text
from tl_adapters.db import DbTarget, create_schema, open_uow
from tl_core import confidentiality as cf
from tl_core.auth import accounts, sessions
from tl_core.ledger import NewEvent
from tl_core.modules import confidential_sources, load_modules
from tl_core.services import link_queries, queries
from tl_core.services.errors import RecordNotFoundError
from tl_core.services.links import AddLink, handle_add_link
from tl_core.services.proposals import list_proposals, propose
from tl_core.util import new_ulid

_ROOT = Path(__file__).resolve().parents[2] / "packages"
for _tests in ("tl-modules/forms/tests", "tl-api/tests"):
    if str(_ROOT / _tests) not in sys.path:
        sys.path.insert(0, str(_ROOT / _tests))

from forms_world import MARKER, PASSWORD, SCOPE, World, answer  # noqa: E402
from harness import Harness  # noqa: E402
from tl_mod_forms.commands import SubmitForm  # noqa: E402
from tl_mod_forms.module import FORMS_COMMANDS  # noqa: E402
from tl_mod_forms.names import INTAKE_CODE, INTAKE_ITEM, SUBMISSION  # noqa: E402

LOW = cf.Viewer(actor="user:vera", level=0, account="user:vera")
AGENT = cf.Viewer(actor="agent:bot", level=0, account="")
NOBODY = cf.LOWEST
CLEARED = cf.Viewer(actor="user:dora", level=1, account="user:dora")
ADMIN = cf.Viewer(actor="user:ada", level=1, account="user:ada")
LOWS = {"user": LOW, "agent": AGENT, "nobody": NOBODY}


@pytest.fixture
def world(new_db: Callable[[], DbTarget]) -> World:
    target = new_db()
    create_schema(target)
    made = World(target)
    made.people()
    return made


def as_system(world: World, who: str, name: str, **fields: Any) -> Any:
    """A command run as ``who`` by its handler with nothing hidden: for the one record no person
    can finish through the filtered path (see the report: a class the author may not read)."""
    cmd = world.command(who, name, None, **fields)
    handler = next(c.handler for c in FORMS_COMMANDS if c.model.__name__ == name)
    with cf.system_view(), open_uow(world.db) as uow:
        return handler(uow, cmd)


def raise_punch(world: World, source: str) -> str:
    """A punch item raised by the controller from ``source``, by the quality module's command."""
    from tl_core.auth.module_roles import require_command_access
    from tl_mod_quality.commands import RaisePunchItem
    from tl_mod_quality.module import PUNCH_COMMANDS

    row = next(c for c in PUNCH_COMMANDS if c.model is RaisePunchItem)
    cmd = RaisePunchItem(
        actor="user:dora", source="test", scope=SCOPE, subject="Rail", from_record_id=source
    )
    with open_uow(world.db) as uow:
        require_command_access(uow.conn(), cmd)
        with cf.use_viewer(cf.viewer_for_actor(uow.conn(), cmd.actor)):
            return str(row.handler(uow, cmd).stream_id)


def run(env: dict[str, str], *args: str) -> Any:
    from tl_cli.main import app
    from typer.testing import CliRunner

    return CliRunner().invoke(app, list(args), env=env)


def new_ledger(tmp_path: Path) -> dict[str, str]:
    env = {"TL_DB": str(tmp_path / "tl.db"), "TL_ENV": "prod"}
    assert run(env, "init").exit_code == 0
    return env


def sign_in(env: dict[str, str], name: str) -> None:
    """Sign in as ``tl login`` does and store the session in the file ``env`` names."""
    from tl_cli import session

    db = Path(env["TL_DB"])
    with mock.patch.dict(os.environ, env):
        principal, token = sessions.sign_in(
            session.open_backend(db), username=name, password=PASSWORD
        )
        stored = session.StoredSession(
            target=session.db_target(db),
            username=name,
            actor=principal.actor,
            expires_at=session.expires_at_from(sessions.SESSION_TTL),
            token=token,
        )
        session.save(stored)


def hidden(world: World, record: str, viewer: cf.Viewer) -> bool:
    with open_uow(world.db, readonly=True) as uow:
        return cf.is_hidden(uow.conn(), record, viewer)


def filed(world: World, tpl: str, who: str = "dora", **more: Any) -> str:
    return str(world.submit(who, tpl, **more).stream_id)


def everything(world: World) -> list[dict[str, Any]]:
    return world.rows("SELECT event_id, stream_id, stream_type, payload FROM events")


# --- the rows -----------------------------------------------------------------------------------


def test_the_forms_rows_are_one_block_and_the_old_rows_are_unchanged() -> None:
    assert [row[0] for row in cf.SUBJECT_LINKS[:6]] == [
        "requisitions.LaborRequisition",
        "requisitions.MaterialRequisition",
        "requisitions.GeneralRequisition",
        "requisitions.ScaffoldRequest",
        "requisitions.WorkOrder",
        "quality.PunchItem",
    ]
    assert cf.SUBJECT_LINKS[6:] == (
        ("forms.Submission", "cur_forms_submission", "id", "subject_id"),
        ("forms.IntakeItem", "cur_forms_intake_item", "id", "code_id"),
        ("forms.IntakeCode", "cur_forms_intake_code", "id", "context_id"),
    )
    assert cf._HOPS == 2  # pyright: ignore[reportPrivateUsage]


def test_only_the_submission_is_an_own_class_type() -> None:
    assert cf.OWN_CLASS_TYPES == {SUBMISSION}
    declared = {t for c in confidential_sources() for t in c.record_types}
    assert cf.OWN_CLASS_TYPES <= declared


# --- a submission with a subject --------------------------------------------------------------


def test_a_submission_with_a_restricted_subject_is_missing_for_low_viewers(world: World) -> None:
    secret = world.hidden_record()
    open_record = world.record("awp.IWP", "OPEN-1")
    tpl = world.template()
    sub = filed(world, tpl, subject_id=secret, answers=[answer("topic", MARKER)])
    with cf.system_view(), open_uow(world.db) as uow:
        handle_add_link(
            uow,
            AddLink(actor="user:dora", source="test", scope=SCOPE, from_id=open_record, to_id=sub),
            by_module=True,
        )
    ghost = new_ulid()
    rows = everything(world)
    own = {r["event_id"] for r in rows if r["stream_id"] == sub}
    assert own
    for name, viewer in LOWS.items():
        assert hidden(world, sub, viewer), name
        with open_uow(world.db, readonly=True) as uow, cf.use_viewer(viewer):
            assert queries.record_history(uow, sub) == queries.record_history(uow, ghost)
            assert queries.get_record_by_id(uow, sub) is None
            with pytest.raises(RecordNotFoundError) as caught:
                cf.require_visible(uow.conn(), sub)
            assert str(caught.value) == f"no record {sub!r}"
            links = link_queries.links_of(uow, open_record)
            assert sub not in [v.other_id for v in links], name
            assert cf.hidden_row_ids(uow.conn(), rows) & own == own, name
            link_ids = [r["stream_id"] for r in rows if r["event_id"] in own]
            assert set(link_ids) <= cf.hidden_event_streams(
                uow.conn(), [(s, SUBMISSION) for s in link_ids]
            ), name
    assert not hidden(world, sub, CLEARED) and not hidden(world, sub, ADMIN)
    with open_uow(world.db, readonly=True) as uow, cf.use_viewer(CLEARED):
        assert sub in [v.other_id for v in link_queries.links_of(uow, open_record)]
        assert cf.hidden_row_ids(uow.conn(), rows) & own == set()


def test_a_submission_follows_a_punch_item_to_its_own_subject(world: World) -> None:
    """The second hop: a submission about a punch item whose source is a restricted record."""
    secret = world.hidden_record()
    punch = raise_punch(world, secret)
    sub = as_system(world, "dora", "SubmitForm", template_id=world.template(), subject_id=punch,
                    answers=[answer("topic", "x")]).stream_id  # fmt: skip
    assert hidden(world, str(sub), LOW) and not hidden(world, str(sub), CLEARED)
    assert hidden(world, punch, LOW)


# --- the answer class --------------------------------------------------------------------------


def test_an_internal_subject_and_a_restricted_answer_class_hide_from_the_lowest(
    world: World,
) -> None:
    subject = world.record("awp.IWP", "OPEN-2")
    tpl = world.template(answer_class="restricted")
    sub = filed(world, tpl, subject_id=subject)
    for name, viewer in LOWS.items():
        assert not hidden(world, subject, viewer), name  # the subject itself is readable
        assert hidden(world, sub, viewer), name
    assert not hidden(world, sub, CLEARED) and not hidden(world, sub, ADMIN)
    plain = filed(world, world.template(), subject_id=subject)
    assert not hidden(world, plain, LOW) and not hidden(world, plain, AGENT)


def test_a_privileged_answer_class_with_no_subject_is_its_own_subject(world: World) -> None:
    tpl = world.template(answer_class="privileged")
    sub = str(as_system(world, "dora", "SubmitForm", template_id=tpl,
                        answers=[answer("topic", "x")]).stream_id)  # fmt: skip
    for viewer in (*LOWS.values(), ADMIN):  # no clearance table: nobody is named
        assert hidden(world, sub, viewer)
    assert not hidden(world, sub, CLEARED)  # but its author (dora) reads what she wrote
    with cf.system_view(), open_uow(world.db, readonly=True) as uow:
        assert queries.get_record_by_id(uow, sub) is not None


def test_a_restricted_answer_class_with_no_subject_is_read_by_a_controller(world: World) -> None:
    sub = filed(world, world.template(answer_class="restricted"))
    for viewer in LOWS.values():
        assert hidden(world, sub, viewer)
    assert not hidden(world, sub, CLEARED) and not hidden(world, sub, ADMIN)


# --- intake rows -------------------------------------------------------------------------------

HASH = "ab" * 32


def _stream(world: World, record_type: str, key: str, event: str, payload: dict[str, Any]) -> str:
    """A record of ``record_type`` made through the ledger: ``Record.Created`` and one event."""
    stream = new_ulid()
    events = [
        NewEvent(
            event_type="Record.Created",
            payload={
                "record_type": record_type,
                "key": key,
                "title": key,
                "description": None,
                "psets": {},
            },
        ),
        NewEvent(
            event_type=event,
            payload={"record_id": stream, "feed_policy": "none", **payload},
        ),
    ]
    with open_uow(world.db) as uow:
        uow.append(
            stream_id=stream,
            stream_type=record_type,
            scope=SCOPE,
            expected_version=0,
            events=events,
            actor="user:uma",
            source="test",
            correlation_id=new_ulid(),
        )
    return stream


def _code(world: World, key: str, context: str | None) -> str:
    return _stream(
        world,
        INTAKE_CODE,
        key,
        "IntakeCode.Issued",
        {
            "code_hash": new_ulid().lower() + HASH[:38],
            "template_id": new_ulid(),
            "template_version": 1,
            "template_hash": HASH,
            "context_id": context,
            "context_type": None if context is None else "core.Record",
            "heading": "Scaffold",
            "controller_role": "controller",
            "expires_on": "2027-01-31",
        },
    )


def _item(world: World, key: str, code: str) -> str:
    return _stream(
        world,
        INTAKE_ITEM,
        key,
        "IntakeItem.Received",
        {
            "item_id": new_ulid(),
            "code_id": code,
            "template_id": new_ulid(),
            "template_version": 1,
            "template_hash": HASH,
            "body_mac": HASH,
            "body_bytes": 10,
            "received_at": "2026-12-01T09:00:00Z",
        },
    )


def test_an_intake_item_is_hidden_when_its_codes_context_is(world: World) -> None:
    secret = world.hidden_record()
    open_record = world.record("awp.IWP", "OPEN-3")
    code_secret, code_open, code_none = (
        _code(world, "IC-1", secret),
        _code(world, "IC-2", open_record),
        _code(world, "IC-3", None),
    )
    items = {
        name: _item(world, name, code)
        for name, code in (("i-secret", code_secret), ("i-open", code_open), ("i-none", code_none))
    }
    for name, viewer in LOWS.items():
        assert hidden(world, code_secret, viewer) and hidden(world, items["i-secret"], viewer), name
        for visible in (code_open, code_none, items["i-open"], items["i-none"]):
            assert not hidden(world, visible, viewer), name  # null context: no source classes it
    assert not hidden(world, code_secret, CLEARED)
    assert not hidden(world, items["i-secret"], CLEARED)


# --- the join budget ---------------------------------------------------------------------------

AUTHOR = cf.Viewer(actor="user:uma", level=0, account="user:uma")


def test_the_hidden_sql_of_every_installed_module_is_under_the_join_limit_on_both_adapters(
    world: World,
) -> None:
    installed = {spec.name for spec in load_modules()}
    assert {"forms", "quality", "requisitions", "correspondence"} <= installed
    for viewer in (NOBODY, AGENT, LOW, CLEARED, AUTHOR):
        sql = cf.hidden_sql(viewer)
        assert sql is not None
        parts = sql.split(" UNION ALL ")
        # SQLite joins at most 64 tables in one SELECT; every part is its own SELECT
        assert max(part.count("JOIN") for part in parts) < 64, viewer
        statement = f"SELECT x.id FROM cur_core_record x WHERE x.id IN ({sql})"
        with open_uow(world.db, readonly=True) as uow:  # it parses and plans: no overflow
            conn = uow.conn()
            conn.execute(text(f"EXPLAIN {statement}"), cf.params_for(sql, viewer)).all()
            conn.execute(text(statement), cf.params_for(sql, viewer)).all()


# --- a proposal carries answers (F-S3a) --------------------------------------------------------

CLASSES = ("internal", "restricted", "privileged")
#: the classes of the proposals each reader may read; nobody is named on a form class
MAY = {
    "uma": {"internal"},
    "vera": {"internal"},
    "dora": {"internal", "restricted"},
    "ada": {"internal", "restricted"},
    "bot": {"internal"},
}
READERS = {"uma": AUTHOR, "vera": LOW, "dora": CLEARED, "ada": ADMIN, "bot": AGENT}


def _proposals(world: World, subject: str | None = None) -> dict[str, str]:
    """One pending proposal per answer class, each with the marker in its answers."""
    made: dict[str, str] = {}
    for cls in CLASSES:
        tpl = world.template(answer_class=cls)
        command = SubmitForm(
            actor="agent:forms-bot",
            source="mcp:forms-bot",
            scope=SCOPE,
            template_id=tpl,
            subject_id=subject,
            answers=[answer("topic", f"{MARKER}-{cls}")],
        )
        # system view: ``propose`` reads the proposal back, and an agent may not read a class
        with cf.system_view(), open_uow(world.db) as uow:
            made[cls] = propose(
                uow,
                tool="propose_form_submission",
                agent="agent:forms-bot",
                command=command,
                summary="File the talk",
            ).proposal_id
    return made


def test_a_proposal_for_a_class_the_viewer_may_not_read_is_absent_on_every_reader(
    world: World,
) -> None:
    made = _proposals(world)
    by_id = {v: k for k, v in made.items()}
    for name, viewer in READERS.items():
        with open_uow(world.db, readonly=True) as uow, cf.use_viewer(viewer):
            listed = list_proposals(uow.conn(), SCOPE, status=None)
        assert {by_id[v.proposal_id] for v in listed} == MAY[name], name
        for cls in CLASSES:
            assert (f"{MARKER}-{cls}" in str(listed)) == (cls in MAY[name]), (name, cls)


def test_a_hidden_proposal_answers_like_one_that_never_existed(world: World) -> None:
    from tl_core.services.errors import ProposalNotFoundError
    from tl_core.services.proposals import get_proposal

    made = _proposals(world)
    ghost = new_ulid()
    for name, viewer in READERS.items():
        for cls, pid in made.items():
            with open_uow(world.db, readonly=True) as uow, cf.use_viewer(viewer):
                if cls in MAY[name]:
                    assert get_proposal(uow.conn(), pid).proposal_id == pid
                    continue
                with pytest.raises(ProposalNotFoundError) as caught:
                    get_proposal(uow.conn(), pid)
                with pytest.raises(ProposalNotFoundError) as missing:
                    get_proposal(uow.conn(), ghost)
            assert str(caught.value).replace(pid, "<id>") == str(missing.value).replace(
                ghost, "<id>"
            ), (name, cls)


def test_the_created_event_of_a_proposal_is_filtered_by_the_class_of_its_template(
    world: World,
) -> None:
    made = _proposals(world)
    by_id = {v: k for k, v in made.items()}
    with open_uow(world.db, readonly=True) as uow:
        events = uow.ledger.read_after(0, scope=SCOPE, limit=1000)
        rows = everything(world)
        for name, viewer in READERS.items():
            with cf.use_viewer(viewer):
                shown = cf.filter_events(uow.conn(), events)
            seen = {by_id[e.stream_id] for e in shown if e.event_type == "Proposal.Created"}
            assert seen == MAY[name], name
            for cls in CLASSES:
                assert (f"{MARKER}-{cls}" in str([e.payload for e in shown])) == (
                    cls in MAY[name]
                ), (name, cls)
            for cls in CLASSES:
                held = {str(r["event_id"]) for r in rows if r["stream_id"] == made[cls]}
                assert (cf.hidden_row_ids(uow.conn(), rows, viewer) & held == set()) == (
                    cls in MAY[name]
                ), (name, cls)
        with cf.system_view():
            assert len(cf.filter_events(uow.conn(), events)) == len(events)


def _sessions(h: Harness, world: World) -> dict[str, str]:
    with h.backend(False) as uow:
        bot = accounts.create_account(
            uow, username="bot", display_name="Bot", kind="agent", roles=["user"],
            password=None, by="svc:test",
        )  # fmt: skip
        _, agent_token = accounts.issue_agent_token(
            uow,
            account_id=bot.account_id,
            label="walk",
            expires_at=datetime.now(UTC) + timedelta(days=1),
            by="svc:test",
        )
    tokens = {
        name: sessions.sign_in(h.backend, username=name, password=PASSWORD)[1]
        for name in ("uma", "vera", "dora", "ada")
    }
    tokens["bot"] = agent_token
    return tokens


def test_the_api_lists_and_gets_a_proposal_only_for_a_class_the_reader_may_read(
    tmp_path: Path,
) -> None:
    h = Harness.build(tmp_path, files=False)
    try:
        world = World(h.db)
        # the harness ledger is a file of the same schema: the people go in as in any test
        world.people()
        made = _proposals(world)
        tokens = _sessions(h, world)
        by_id = {v: k for k, v in made.items()}
        ghost = new_ulid()
        for name, token in tokens.items():
            client = h.client_for(None)
            client.headers.update({"Authorization": f"Bearer {token}"})
            listed = client.get("/proposals", params={"scope": SCOPE, "all": "true"})
            assert listed.status_code == 200, name
            assert {by_id[r["proposal_id"]] for r in listed.json()} == MAY[name], name
            for cls, pid in made.items():
                got = client.get(f"/proposals/{pid}", params={"scope": SCOPE})
                if cls in MAY[name]:
                    assert got.status_code == 200, (name, cls)
                    continue
                missing = client.get(f"/proposals/{ghost}", params={"scope": SCOPE})
                assert got.status_code == missing.status_code == 404, (name, cls)
                assert got.content.replace(pid.encode(), b"<id>") == missing.content.replace(
                    ghost.encode(), b"<id>"
                ), (name, cls)
                assert MARKER not in got.text
    finally:
        h.close()


@pytest.fixture
def cli_env(tmp_path: Path) -> Iterator[dict[str, str]]:
    env = new_ledger(tmp_path)
    yield env


def test_the_cli_lists_and_shows_a_proposal_only_for_a_class_the_reader_may_read(
    cli_env: dict[str, str], tmp_path: Path
) -> None:
    world = World(Path(cli_env["TL_DB"]))
    world.people()
    made = _proposals(world)
    by_id = {v: k for k, v in made.items()}
    readers = {"vera": "vera", "uma": "uma", "dora": "dora", "ada": "ada"}
    for name in readers:
        env = cli_env | {"TL_SESSION_FILE": str(tmp_path / f"session-{name}.json")}
        sign_in(env, name)
        listed = run(env, "proposal", "ls", "--project", "P123", "--status", "all")
        assert listed.exit_code == 0, listed.output
        seen = {by_id[pid] for pid in made.values() if pid in listed.output}
        assert seen == MAY[name], name
        assert MARKER not in listed.output
        for cls, pid in made.items():
            shown = run(env, "proposal", "show", pid)
            if cls in MAY[name]:
                assert shown.exit_code == 0, (name, cls, shown.output)
            else:
                assert shown.exit_code == 1 and MARKER not in shown.output, (name, cls)
                assert pid not in shown.output.replace(f"no proposal {pid!r}", "")
    nobody = run(cli_env | {"TL_SESSION_FILE": str(tmp_path / "none.json")}, "proposal", "ls",
                 "--project", "P123", "--status", "all")  # fmt: skip
    assert nobody.exit_code == 0 and MARKER not in nobody.output
    assert {by_id[pid] for pid in made.values() if pid in nobody.output} == {"internal"}


def test_the_record_activity_of_a_subject_leaves_out_a_proposal_of_a_class_not_read(
    world: World,
) -> None:
    from tl_core.insights.activity import record_activity

    subject = world.record("awp.IWP", "OPEN-9")
    made = _proposals(world, subject)
    for name, viewer in READERS.items():
        with open_uow(world.db, readonly=True) as uow, cf.use_viewer(viewer):
            page = record_activity(uow, subject)
        dump = str([r.event.payload for r in page.rows])
        created = [r for r in page.rows if r.event.event_type == "Proposal.Created"]
        assert {r.event.stream_id for r in created} == {made[c] for c in MAY[name]}, name
        for cls in CLASSES:
            assert (f"{MARKER}-{cls}" in dump) == (cls in MAY[name]), (name, cls)


def test_the_api_record_activity_of_a_subject_leaves_out_a_proposal_of_a_class_not_read(
    tmp_path: Path,
) -> None:
    h = Harness.build(tmp_path, files=False)
    try:
        world = World(h.db)
        world.people()
        subject = world.record("awp.IWP", "OPEN-9")
        made = _proposals(world, subject)
        tokens = _sessions(h, world)
        for name, token in tokens.items():
            client = h.client_for(None)
            client.headers.update({"Authorization": f"Bearer {token}"})
            got = client.get(f"/records/{subject}/activity")
            if name == "bot":  # activity.read is not open to agents
                assert got.status_code == 403 and MARKER not in got.text
                continue
            assert got.status_code == 200, (name, got.text)
            for cls in CLASSES:
                assert (f"{MARKER}-{cls}" in got.text) == (cls in MAY[name]), (name, cls)
                assert (made[cls] in got.text) == (cls in MAY[name]), (name, cls)
    finally:
        h.close()


def test_a_subject_reclassified_after_the_filing_is_missing_for_the_author_too(
    world: World,
) -> None:
    from tl_core.services.commands import Command
    from tl_mod_correspondence.handlers.confidentiality import (
        SetCorrespondenceConfidentiality,
        handle_set_confidentiality,
    )
    from tl_mod_correspondence.handlers.create import create_item
    from tl_mod_correspondence.handlers.models import Recipient
    from tl_mod_correspondence.testing import frozen_today

    cmd = Command(actor="user:dora", source="test", scope=SCOPE)
    with cf.system_view(), frozen_today("2026-10-19"), open_uow(world.db) as uow:
        item = str(
            create_item(
                uow, cmd, subject="Plain", direction="in", medium="letter",
                received_via="manual", to=[Recipient(name="Someone")], body="Body",
                received_on="2026-10-19", received=True,
            ).stream_id
        )  # fmt: skip
    sub = str(
        world.submit("uma", world.template(), subject_id=item).stream_id
    )  # a plain user files
    assert not hidden(world, sub, AUTHOR) and not hidden(world, sub, LOW)
    with cf.system_view(), frozen_today("2026-10-19"), open_uow(world.db) as uow:
        handle_set_confidentiality(
            uow,
            SetCorrespondenceConfidentiality(
                actor="user:dora", source="test", scope=SCOPE, stream_id=item,
                to_class="restricted", reason="test",
            ),
        )  # fmt: skip
    ghost = new_ulid()
    for viewer in (AUTHOR, LOW, AGENT, NOBODY):
        assert hidden(world, sub, viewer)
        with open_uow(world.db, readonly=True) as uow, cf.use_viewer(viewer):
            assert queries.get_record_by_id(uow, sub) is None
            assert queries.record_history(uow, sub) == queries.record_history(uow, ghost)
    assert not hidden(world, sub, CLEARED)
