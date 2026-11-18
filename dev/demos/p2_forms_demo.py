"""Driver for dev/demos/P2-FORMS.sh: the clauses that are not a `tl form` command.

The ledger is the whole demo project P200 (the generator's `forms` section included); TL_DB names
it (a SQLite file or a postgresql:// URL). The API is the running `tl serve` at TL_API_URL, read as
a person (a session token from `sessions.sign_in`). Each mode prints ``ok <what>`` lines, and a
miss prints ``FAIL <what>`` and exits 1; the shell prints ``PASS clause N`` after the mode returns.

Modes (first argument):

* ``ledger DEST``: copy the cached full demo ledger (tests/perf, built once) to DEST (SQLite).
* ``template-file DEST``: write the template file clause 1 publishes (a copy of the toolbox talk
  with its own title).
* ``clause1 KEY``: the API gives template KEY version 1 as JSON Schema and as SurveyJS; both equal
  the projection of the file's fields computed here, the ETag answers 304, and a miss is a 404.
* ``clause2 KEY DRAFT``: the submission KEY has a new, latest number, is Submitted, and the
  draft DRAFT it came from never had one.
* ``clause3 TEMPLATE``: fill TEMPLATE through the runner model (``tl_core.forms.runner``), one
  field at a time, and submit the confirmed answers over the API as pnair; the stored answers are
  the ones the runner confirmed. Prints the new key.
* ``clause4 KEY DRAFT``: KEY is the Submitted form that DRAFT (saved twice, the second time by
  ``tl form fill --resume``) became: it has a number only now, and its answers hold the ones of the
  first save and of the resume.
* ``clause5 KEY OWN``: KEY is Accepted by the controller; OWN is Accepted by a second controller.
* ``clause7 KEY``: KEY is a submission only its author may read: every other reader gets, on the
  detail route, the bytes a missing key gets, and no list holds it.
* ``clause7-mcp KEY``: the MCP tools (in-process server, no model) as an agent and as three people:
  ``get_form_submission`` for KEY (a hidden submission), for a draft id and for a missing key
  answer with the same bytes; ``list_form_submissions`` leaves KEY out.
* ``clause8 DRAFT AUTHOR``: the draft DRAFT is invisible to every reader but AUTHOR.
* ``clause11 TEMPLATE``: the terminal app (headless Textual pilot, as ``p2_i4b_demo`` drives the
  toolcrib screen): open the forms log of the project as pnair, show the templates, fill TEMPLATE
  through the runner screen one question at a time, review, send; the new number is in the log and
  the stored answers are the ones the screen collected. Prints the wall time and ``submitted KEY``.
* ``clause6-pick``: prints the key of a Scheduled inspection whose form hsato may fill (the API
  offers it, available), and ``clause6-answers KEY DEST``: writes an answers file for it that
  answers every question the way that passes (clause 6 fills it through ``tl form record``).
* ``clause6 KEY``: the inspection KEY is Done with the result accept, recorded by hsato, and its
  form is closed (``already_recorded``); the forms module holds no submission for it.
* ``clause10-stage CODE_ID``: a dev-only helper standing in for the public intake route (S6, owner
  gate Q9; there is none): it writes two received items of the code, as ``svc:intake`` would (a
  ``Received`` event and a body row), the second received 45 days ago. Prints their ids.
* ``clause10-args TEMPLATE_KEY DEST``: write the arguments file the controller accepts item A with
  (the command ``SubmitForm`` for that template, with every answer).
* ``clause10 CODE ITEM_A ITEM_B TEMPLATE_KEY OUTFILE``: the signed-in reads give A as Accepted (as
  SubmitForm) and B as Rejected and purged; the submission A proposed is read back with its
  answers; a user without the intake word and a stranger are refused; the code (plain and grouped),
  its hash, the salt and the stored body are in no read, in OUTFILE (the CLI outputs the shell
  collected); the code (never its hash, which the event holds) is in no ledger row of the code and
  the items.
* ``budget``: every forms list read is under one second (median of five) as treyes and mokafor.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import statistics
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, NoReturn

import httpx2
import yaml
from mcp.server.mcpserver.exceptions import ToolError
from sqlalchemy import Connection, text
from tl_adapters.backend import open_backend
from tl_adapters.db import as_target, open_uow
from tl_core import confidentiality as cf
from tl_core.auth import sessions
from tl_core.forms import runner
from tl_core.forms.jsonschema import to_json_schema
from tl_core.forms.surveyjs import surveyjs_unsupported, to_surveyjs
from tl_core.forms.types import FormBinding
from tl_core.ledger import NewEvent
from tl_core.qr.codes import code_hash, grouped, normalise_code
from tl_core.util import new_ulid
from tl_mcp.server import build_server
from tl_mod_forms import bound

ROOT = Path(__file__).resolve().parents[2]
PASSWORD = "p200-demo-pass"  # demo data only (dev/seed/demo_project/core.py)
PROJECT = "P200"
READERS = ("mokafor", "ipetrov", "treyes", "cbrooks", "pnair")
MISSING_KEY = "P200-FRM-9999"
MISSING_ID = "01J000000000000000000000"
BUDGET_SECONDS = 1.0
FIXTURE = ROOT / "schema" / "fixtures" / "forms" / "templates" / "toolbox-talk.yaml"
TITLE = "Site induction check"


def ok(text: str) -> None:
    print(f"ok {text}", flush=True)


def miss(what: str) -> NoReturn:
    print(f"FAIL {what}", flush=True)
    raise SystemExit(1)


def check(condition: bool, what: str) -> None:
    if not condition:
        miss(what)


class World:
    """The ledger in TL_DB and the API at TL_API_URL, read as a named person."""

    def __init__(self) -> None:
        self.backend = open_backend(as_target(os.environ["TL_DB"]))
        self.url = os.environ["TL_API_URL"]
        self._tokens: dict[str, str] = {}

    def http(self, who: str) -> httpx2.Client:
        if who not in self._tokens:
            _, token = sessions.sign_in(self.backend, username=who, password=PASSWORD)
            self._tokens[who] = token
        return httpx2.Client(
            base_url=self.url, headers={"Authorization": f"Bearer {self._tokens[who]}"}
        )

    def get(self, who: str, path: str, **params: Any) -> httpx2.Response:
        with self.http(who) as client:
            return client.get(path, params=params)

    def post(self, who: str, name: str, body: dict[str, Any]) -> httpx2.Response:
        with self.http(who) as client:
            return client.post(f"/commands/{name}", json=body)

    def close(self) -> None:
        self.backend.close()


def same(a: httpx2.Response, b: httpx2.Response) -> bool:
    """The same status, content type and body bytes."""
    return (
        a.status_code == b.status_code
        and a.content == b.content
        and a.headers.get("content-type") == b.headers.get("content-type")
    )


def fixture_body() -> dict[str, Any]:
    body = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))
    body["title"] = TITLE
    return body


def ledger(dest: str) -> None:
    sys.path.insert(0, str(ROOT / "tests" / "perf"))
    import test_budget  # pyright: ignore[reportMissingImports]

    began = time.monotonic()
    cached = test_budget.build_cached_ledger(ROOT / ".gate" / "demo-full", test_budget.ledger_key())
    shutil.copyfile(cached, dest)
    ok(f"the full demo ledger {cached.name} copied in {time.monotonic() - began:.1f} s")


def template_file(dest: str) -> None:
    Path(dest).write_text(yaml.safe_dump(fixture_body(), sort_keys=False), encoding="utf-8")
    ok(f"template file {TITLE}")


def clause1(key: str) -> None:
    world = World()
    body = fixture_body()
    fields, fmt = body["fields"], body["format_version"]
    base = f"/forms/templates/{key}/versions/1"
    schema = world.get("cbrooks", base, **{"as": "jsonschema"})
    check(schema.status_code == 200, f"jsonschema answered {schema.status_code}")
    check(schema.json() == to_json_schema(fields, fmt), "the JSON Schema is the projection")
    ok(f"{key} as JSON Schema equals the projection of its {len(fields)} fields")
    survey = world.get("cbrooks", base, **{"as": "surveyjs"})
    check(survey.status_code == 200, f"surveyjs answered {survey.status_code}")
    want = {"model": to_surveyjs(fields, fmt), "unsupported": surveyjs_unsupported(fields)}
    check(survey.json() == want, "the SurveyJS model is the projection")
    ok(f"{key} as SurveyJS equals the projection")
    tag = schema.headers.get("etag")
    check(bool(tag), "the ETag is set")
    check(survey.headers.get("etag") != tag, "the two projections have two ETags")
    with world.http("cbrooks") as client:
        again = client.get(base, params={"as": "jsonschema"}, headers={"If-None-Match": str(tag)})
    check(again.status_code == 304 and not again.content, "If-None-Match answers 304")
    ok("the ETag answers 304 with no body")
    gone = world.get("cbrooks", "/forms/templates/TPL-9999/versions/1")
    check(gone.status_code == 404, "an unknown template is a 404")
    world.close()


def keys_of(world: World, who: str, **params: Any) -> list[dict[str, Any]]:
    got = world.get(who, "/forms/submissions", project=PROJECT, limit=500, **params)
    check(got.status_code == 200, f"{who} list answered {got.status_code}")
    return list(got.json()["rows"])


def clause2(key: str, draft: str) -> None:
    world = World()
    rows = keys_of(world, "cbrooks")
    numbers = sorted(int(r["key"].rsplit("-", 1)[1]) for r in rows if r["key"])
    check(key in {r["key"] for r in rows}, f"{key} is in the list")
    check(int(key.rsplit("-", 1)[1]) == numbers[-1], f"{key} has the latest number")
    others = [n for n in numbers if n != int(key.rsplit("-", 1)[1])]
    check(len(numbers) == len(set(numbers)), "the numbers are unique")
    ok(f"{key} took a number after the {len(others)} the reader sees (the last is {max(others)})")
    got = world.get("cbrooks", f"/forms/submissions/{key}", project=PROJECT).json()
    check(got["row"]["state"] == "Submitted", "the submission is Submitted")
    first = world.get("cbrooks", f"/forms/submissions/{got['row']['id']}", project=PROJECT).json()
    check(first["row"]["id"] == got["row"]["id"] and first["row"]["key"] == key, "same record")
    check(got["row"]["id"] == draft, "the submission is the draft that was saved")
    ok("the draft had no number and became the submission")
    world.close()


def value_for(step: runner.Step) -> Any:
    if step.kind == "number":
        low = step.min if step.min is not None else 0
        return int(max(low, 1))
    if step.kind == "yes_no_na":
        return "yes"
    if step.kind == "date":
        return "2026-11-05"
    if step.kind == "choice":
        return step.choices[0]
    if step.kind == "multi":
        return list(step.choices[:2])
    return f"{step.id} done"


def clause3(template: str) -> None:
    world = World()
    detail = world.get("pnair", f"/forms/templates/{template}/versions/1")
    check(detail.status_code == 200, f"template read answered {detail.status_code}")
    body = detail.json()
    fields: list[dict[str, Any]] = body["fields"]
    fmt = int(body["row"]["format_version"] or 2)
    state = runner.start(fields, fmt=fmt)
    walked: list[str] = []
    for _ in range(2 * len(fields)):
        current = runner.step(state, fields)
        if current is None:
            break
        if not current.required:
            state, problems = runner.skip(state, fields)
        else:
            state, problems = runner.answer(state, fields, value_for(current))
        check(not problems, f"the runner refused {current.id}: {problems}")
        walked.append(current.id)
    seen = runner.review(state, fields)
    check(not seen.missing, f"the review misses {seen.missing}")
    answers = runner.confirm(state, fields)
    ok(f"the runner walked {len(walked)} fields one at a time ({len(answers)} answered)")
    before = {r["key"] for r in keys_of(world, "pnair") if r["key"]}
    sent = world.post(
        "pnair",
        "SubmitForm",
        {
            "source": "demo",
            "scope": f"project:{PROJECT}",
            "template_id": body["row"]["id"],
            "answers": answers,
        },
    )
    check(sent.status_code in (200, 201), f"SubmitForm answered {sent.status_code} {sent.text}")
    key = str(sent.json()["key"])
    check(key not in before and key.startswith("P200-FRM-"), "a new number was taken")
    stored = world.get("pnair", f"/forms/submissions/{key}", project=PROJECT).json()
    got = {a["q"]: a["value"] for a in stored["answers"]}
    check(got == {a["q"]: a["value"] for a in answers}, "the stored answers are the confirmed ones")
    ok(f"{key} holds the answers the runner confirmed")
    print(f"submitted {key}")
    world.close()


def line_for(step: runner.Step) -> str:
    """What a person types on the runner's line for ``step``; empty skips an optional question."""
    if not step.required:
        return ""
    if step.kind == "choice":
        return "1"
    if step.kind == "multi":
        return "1,2"
    return str(value_for(step))


def clause11(template: str) -> None:
    """The forms log and the runner screen of the terminal app, on the full demo ledger."""
    import asyncio

    from textual.widgets import Input, Static
    from tl_tui.app import TlApp
    from tl_tui.embedded import EmbeddedClient
    from tl_tui.form_runner_text import parse_answer
    from tl_tui.widgets.forms_log import FormRunnerScreen, FormsLogScreen

    began = time.monotonic()
    world = World()
    actor = "user:pnair"
    client = EmbeddedClient(world.backend, actor=actor)
    before = {r.key for r in client.list_form_submissions(PROJECT, limit=500).rows if r.key}
    found: dict[str, Any] = {}

    async def settle(pilot: Any) -> None:
        await pilot.pause()
        await pilot.app.workers.wait_for_complete()
        await pilot.pause()
        await pilot.pause()

    async def scenario() -> None:
        app = TlApp(client, scope=f"project:{PROJECT}", actor=actor)
        async with app.run_test(size=(170, 44)) as pilot:
            await settle(pilot)
            app.push_screen(FormsLogScreen(client, PROJECT))  # the palette's `forms` opens this
            await settle(pilot)
            log = app.screen
            check(isinstance(log, FormsLogScreen), "the forms log did not open")
            assert isinstance(log, FormsLogScreen)
            found["opened"] = len(log.shown)
            await pilot.press("2")
            await settle(pilot)
            row = next((r for r in log.shown if getattr(r, "key", None) == template), None)
            check(row is not None, f"{template} is not in the templates view")
            log.open_row(row)  # type: ignore[arg-type]
            await settle(pilot)
            screen = app.screen
            check(isinstance(screen, FormRunnerScreen), "the runner screen did not open")
            assert isinstance(screen, FormRunnerScreen)
            check(screen.ready and screen.state is not None, "the runner did not load the template")
            typed: dict[str, Any] = {}
            for _ in range(2 * len(screen.fields)):
                assert screen.state is not None
                step = runner.step(screen.state, screen.fields)
                if step is None:
                    break
                line = line_for(step)
                if line:
                    typed[step.id] = parse_answer(step, line)
                screen.query_one("#fr-input", Input).value = line
                await pilot.press("enter")
                await settle(pilot)
                status = str(screen.query_one("#fr-status", Static).content)
                check(not status.startswith("!"), f"the runner refused {step.id}: {status}")
            assert screen.state is not None
            check(screen.state.phase == "review", "the runner did not reach the review page")
            found["typed"] = typed
            found["walked"] = len(typed)
            await pilot.press("enter")  # the review page: send
            await settle(pilot)
            check(app.screen is log, "the runner did not close after the send")
            found["numbers"] = {getattr(r, "key", None) for r in log.shown}
            found["status"] = str(log.query_one("#log-status", Static).content)

    asyncio.run(scenario())
    new = sorted(k for k in found["numbers"] if k and k not in before)
    check(len(new) == 1, f"the log shows {len(new)} new numbers, want 1")
    key = str(new[0])
    check(key.startswith(f"{PROJECT}-FRM-"), f"{key} is not a form number")
    check(found["status"].startswith(f"Submitted {key}"), f"status line: {found['status']!r}")
    ok(f"the log of {found['opened']} submissions opened; {template} walked in the runner screen")
    stored = client.get_form_submission(PROJECT, key)
    got = {str(a["q"]): a["value"] for a in stored.answers}
    check(stored.row.state == "Submitted", f"{key} is {stored.row.state}")
    check(got == found["typed"], f"stored answers {got} differ from the typed {found['typed']}")
    ok(f"{key} is Submitted by {stored.row.author} with the {found['walked']} answers typed")
    again = client.list_form_submissions(PROJECT, limit=500)
    check(key in {r.key for r in again.rows}, f"{key} is not in the log read again")
    ok(f"{key} is in the log read again")
    print(f"submitted {key}")
    print(f"clause 11 wall {time.monotonic() - began:.1f} s")
    world.close()


def state_of(world: World, who: str, key: str) -> str:
    got = world.get(who, f"/forms/submissions/{key}", project=PROJECT)
    check(got.status_code == 200, f"{who} could not read {key}")
    return str(got.json()["row"]["state"])


def clause5(key: str, own: str) -> None:
    world = World()
    check(state_of(world, "cbrooks", key) == "Accepted", f"{key} is Accepted")
    detail = world.get("cbrooks", f"/forms/submissions/{key}", project=PROJECT).json()
    check(detail["row"]["reviewed_by"] == "user:ipetrov", "the reviewer is the controller")
    check(detail["row"]["author"] != detail["row"]["reviewed_by"], "the reviewer is not the author")
    ok(f"{key} was accepted by {detail['row']['reviewed_by']}, who is not its author")
    check(state_of(world, "ipetrov", own) == "Accepted", f"{own} is Accepted")
    mine = world.get("ipetrov", f"/forms/submissions/{own}", project=PROJECT).json()
    check(mine["row"]["reviewed_by"] == "user:mokafor", "a second controller accepted the own form")
    ok(f"{own}, filled by a controller, was accepted by another")
    world.close()


def clause7(key: str) -> None:
    world = World()
    missing = world.get("mokafor", f"/forms/submissions/{MISSING_KEY}", project=PROJECT)
    check(missing.status_code == 404, "a missing key is a 404")
    for who in READERS:
        mine = world.get(who, f"/forms/submissions/{MISSING_KEY}", project=PROJECT)
        hidden = world.get(who, f"/forms/submissions/{key}", project=PROJECT)
        check(same(hidden, mine), f"{who}: the hidden submission differs from a missing one")
        check(key not in hidden.text, f"{who}: the answer echoes the key")
        listed = {r["key"] for r in keys_of(world, who)}
        check(key not in listed, f"{who}: the list shows the hidden submission")
        ok(f"{who}: {hidden.status_code}, {len(hidden.content)} bytes, same as a missing key")
    author = world.get("hsato", f"/forms/submissions/{key}", project=PROJECT)
    check(author.status_code == 200, "the author reads it")
    check(key in {r["key"] for r in keys_of(world, "hsato")}, "the author lists it")
    ok("its author reads and lists it")
    world.close()


def clause4(key: str, draft: str) -> None:
    world = World()
    got = world.get("cbrooks", f"/forms/submissions/{key}", project=PROJECT).json()
    check(
        got["row"]["id"] == draft and got["row"]["state"] == "Submitted", "the draft was submitted"
    )
    check(
        (got["row"]["draft_saves"] or 0) >= 2, "the draft was saved twice before it was submitted"
    )
    answers = {a["q"]: a["value"] for a in got["answers"]}
    check(answers.get("topic") == "Resumed talk", "the answer of the first save is kept")
    check(answers.get("led_by") == "Callum", "the answer added on resume is kept")
    ok(f"{draft}: saved, resumed, submitted as {key}; the number came at submit")
    world.close()


def call_tool(server: Any, tool: str, **arguments: Any) -> tuple[bool, str]:
    """``(ok, bytes)`` of one in-process MCP tool call: the structured result or the refusal."""
    try:
        result = asyncio.run(server.call_tool(tool, arguments))
    except ToolError as exc:
        return False, str(exc)
    return True, json.dumps(result.structured_content, sort_keys=True)


def clause7_mcp(key: str) -> None:
    world = World()
    check(
        call_tool(build_server(world.backend, actor="agent:demo"), "list_form_templates")[0],
        "the agent lists the templates",
    )
    for actor in ("agent:demo", "user:cbrooks", "user:ipetrov", "user:treyes"):
        server = build_server(world.backend, actor=actor)
        gone = call_tool(server, "get_form_submission", project=PROJECT, key=MISSING_KEY)
        check(gone[0] is False, f"{actor}: a missing key is refused")
        for ref in (key, MISSING_ID):
            seen = call_tool(server, "get_form_submission", project=PROJECT, key=ref)
            check(seen == gone, f"{actor}: {ref} differs from a missing key")
        check(key not in gone[1], f"{actor}: the refusal echoes the key")
        listed = call_tool(server, "list_form_submissions", project=PROJECT, limit=200)
        check(listed[0] and key not in listed[1], f"{actor}: the list shows the hidden submission")
        ok(f"{actor}: get_form_submission gives {len(gone[1])} equal bytes for {key} and a miss")
    world.close()


def clause8(draft: str, author: str) -> None:
    world = World()
    for who in READERS:
        if who == author:
            continue
        mine = world.get(who, f"/forms/submissions/{MISSING_ID}", project=PROJECT)
        seen = world.get(who, f"/forms/submissions/{draft}", project=PROJECT)
        check(same(seen, mine), f"{who}: the draft differs from a missing id")
        drafts = keys_of(world, who, state="Draft")
        check(draft not in {r["id"] for r in drafts}, f"{who}: the drafts list shows it")
        ok(f"{who}: the draft is a missing id ({seen.status_code}), and not in a list")
    mine = world.get(author, f"/forms/submissions/{draft}", project=PROJECT)
    check(mine.status_code == 200 and mine.json()["row"]["state"] == "Draft", "the author reads it")
    check(draft in {r["id"] for r in keys_of(world, author, state="Draft")}, "the author lists it")
    ok(f"{author} reads and lists the draft")
    world.close()


def clause6_pick() -> None:
    world = World()
    rows = world.get("hsato", "/quality/inspections", project=PROJECT, state="Scheduled")
    check(rows.status_code == 200, f"the inspection list answered {rows.status_code}")
    for row in rows.json()["rows"]:
        offer = world.get("hsato", f"/forms/for/{row['key']}", project=PROJECT)
        if offer.status_code == 200 and offer.json()["available"]:
            world.close()
            print(row["key"])
            return
    miss("no Scheduled inspection offers a form to hsato")


def passing_answer(field: dict[str, Any]) -> Any:
    if field["kind"] == "number":
        low, high = field.get("min"), field.get("max")
        return (low + high) / 2 if low is not None and high is not None else (low or high or 1)
    if field["kind"] == "yes_no_na":
        return "yes"
    if field["kind"] == "choice":
        return field["choices"][0]
    return f"{field['id']} checked"


def clause6_answers(key: str, dest: str) -> None:
    world = World()
    offer = world.get("hsato", f"/forms/for/{key}", project=PROJECT)
    check(offer.status_code == 200, f"/forms/for/{key} answered {offer.status_code}")
    body = offer.json()
    check(body["available"] and body["command"] == "RecordInspectionResult", "the form is open")
    check(body["answers_arg"] == "answers", "the answers go in `answers`")
    with world.backend(True) as uow:
        viewer = cf.viewer_for_actor(uow.conn(), "user:hsato")
        fields = bound.fields_of(uow.conn(), FormBinding.model_validate(body), viewer)
    check(bool(fields), "the checklist has questions")
    answers = {f["id"]: passing_answer(f) for f in fields if f.get("required")}
    Path(dest).write_text(json.dumps(answers), encoding="utf-8")
    ok(f"{key}: {len(answers)} of {len(fields)} questions answered (the required ones)")
    world.close()


def clause6(key: str) -> None:
    world = World()
    got = world.get("mokafor", f"/quality/inspections/{key}", project=PROJECT)
    check(got.status_code == 200, f"the inspection read answered {got.status_code}")
    row = got.json()
    check(row["row"]["state"] == "Done", f"the inspection is {row['row']['state']}, not Done")
    check(row["row"]["result"] == "accept", "the recorded result is accept")
    check(row["recorded_by"] == "user:hsato", "hsato recorded it")
    check(len(row["answers"]) > 0, "the answers are on the inspection")
    ok(f"{key} is Done: result accept, {len(row['answers'])} answers, recorded by hsato")
    after = world.get("hsato", f"/forms/for/{key}", project=PROJECT)
    check(after.status_code == 200 and after.json()["reason"] == "already_recorded", "form closed")
    subs = keys_of(world, "mokafor", subject=row["row"]["id"])
    check(not subs, "the forms module holds no submission for it")
    ok("its form is closed and forms holds no submission: the typed command made the record")
    world.close()


SALT = "0f" * 16  # the staged rows' salt, as the item's body row holds it


def clause10_stage(code_id: str) -> None:
    """Write two received items of ``code_id`` (see the module docstring); print their ids."""
    scope = f"project:{PROJECT}"
    made: list[str] = []
    with open_uow(as_target(os.environ["TL_DB"])) as uow:
        conn = uow.conn()
        code = (
            conn.execute(
                text(
                    "SELECT template_id, template_version, template_hash "
                    "FROM cur_forms_intake_code WHERE id = :i"
                ),
                {"i": code_id},
            )
            .mappings()
            .one()
        )
        for topic, name, company, age in (
            ("Scaffold for the gate 3 canopy", "Sam Smith", "Acme Scaffolding", 0),
            ("Please call me about hire rates", "Pat Lee", "Lee Hire", 45),
        ):
            item = new_ulid()
            stamp = (datetime.now(UTC) - timedelta(days=age)).strftime("%Y-%m-%dT%H:%M:%SZ")
            body = json.dumps(
                {
                    "answers": [
                        {"q": "claim_name", "value": name, "note": None},
                        {"q": "claim_company", "value": company, "note": None},
                        {"q": "location", "value": topic, "note": None},
                        {"q": "scaffold_type", "value": "Tube and fitting", "note": None},
                        {"q": "height_m", "value": 6, "note": None},
                    ]
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            uow.append(
                stream_id=item,
                stream_type="forms.IntakeItem",
                scope=scope,
                expected_version=0,
                events=[
                    NewEvent(
                        event_type="Record.Created",
                        payload={
                            "record_type": "forms.IntakeItem",
                            "key": None,
                            "title": "Intake item",
                            "description": None,
                            "psets": {},
                        },
                    ),
                    NewEvent(
                        event_type="IntakeItem.Received",
                        payload={
                            "item_id": item,
                            "code_id": code_id,
                            "template_id": code["template_id"],
                            "template_version": code["template_version"],
                            "template_hash": code["template_hash"],
                            "body_mac": "cd" * 32,
                            "body_bytes": len(body.encode()),
                            "received_at": stamp,
                            "feed_policy": "none",
                        },
                    ),
                ],
                actor="svc:intake",
                source=f"intake:{code_id}",
                correlation_id=new_ulid(),
            )
            conn.execute(
                text(
                    "INSERT INTO forms_intake_body (item_id, code_id, salt, body, received_at) "
                    "VALUES (:i, :c, :s, :b, :r)"
                ),
                {"i": item, "c": code_id, "s": SALT, "b": body, "r": stamp},
            )
            made.append(item)
    print(" ".join(made))


def clause10_args(template_key: str, dest: str) -> None:
    world = World()
    answers = {
        "topic": "Gate 3 canopy scaffold",
        "talk_date": "2026-11-05",
        "led_by": "Marta",
        "hazards_covered": ["Falls"],
        "ppe_checked": "yes",
        "attendees": 6,
    }
    args = {
        "template_id": _template_id(world, template_key),
        "answers": [{"q": q, "value": v, "note": None} for q, v in answers.items()],
    }
    Path(dest).write_text(json.dumps(args), encoding="utf-8")
    ok(f"arguments of SubmitForm for {template_key}")
    world.close()


def clause10(code: str, item_a: str, item_b: str, template_key: str, outfile: str) -> None:
    plain = normalise_code(code)
    check(plain is not None, "the printed code is a code")
    assert plain is not None
    secrets = [plain, grouped(plain), code_hash(plain), SALT, "cd" * 32]
    world = World()
    seen: list[str] = []

    def read(who: str | None, path: str, **params: Any) -> httpx2.Response:
        if who is None:
            with httpx2.Client(base_url=world.url) as bare:
                got = bare.get(path, params=params)
        else:
            got = world.get(who, path, **params)
        seen.append(got.text)
        return got

    items = read("mokafor", "/forms/intake/items", project=PROJECT, limit=500)
    check(items.status_code == 200, f"the items answered {items.status_code}")
    rows = {r["id"]: r for r in items.json()["rows"]}
    a, b = rows.get(item_a), rows.get(item_b)
    check(a is not None and b is not None, "both items are in the queue")
    assert a is not None and b is not None
    check(
        a["state"] == "Accepted" and a["accepted_as"] == "SubmitForm", "A is Accepted as SubmitForm"
    )
    check(a["claim_name"] == "Sam Smith" and a["claim_company"] == "Acme Scaffolding", "A's claim")
    check(a["purged_at"] is not None, "A's text was removed when it was accepted")
    check(b["state"] == "Rejected" and b["rejected_reason"] == "spam", "B is Rejected as spam")
    check(b["purged_at"] is not None, "B's text was purged")
    ok("A reads Accepted as SubmitForm and B Rejected (spam) and purged; neither holds its text")
    for item in (item_a, item_b):
        gone = read("mokafor", f"/forms/intake/items/{item}", project=PROJECT)
        check(
            gone.status_code == 200 and gone.json()["answers"] is None, f"{item}: no answers left"
        )
    codes = read("mokafor", "/forms/intake/codes", project=PROJECT, limit=500).json()["rows"]
    mine = [c for c in codes if c["heading"] == "Poster at gate 3"]
    check(len(mine) == 1 and mine[0]["state"] == "Active", "the code is listed Active")
    check(mine[0]["pending"] == 0, "no item of the code is Pending")
    subs = keys_of(world, "mokafor", template=_template_id(world, template_key))
    made = [s for s in subs if s["author"] == "user:mokafor" and s["state"] == "Submitted"]
    check(bool(made), "the record item A proposed exists")
    key = max((s["key"] for s in made), key=lambda k: int(k.rsplit("-", 1)[1]))
    detail = read("mokafor", f"/forms/submissions/{key}", project=PROJECT).json()
    got = {a["q"]: a["value"] for a in detail["answers"]}
    check(
        got.get("topic") == "Gate 3 canopy scaffold",
        "the submission holds the controller's answers",
    )
    ok(f"{key} read back: accepted from the item, answers as the controller completed them")
    for who in ("cbrooks", "pnair"):
        for path in ("/forms/intake/items", "/forms/intake/codes", f"/forms/intake/items/{item_a}"):
            check(read(who, path, project=PROJECT).status_code == 403, f"{who} {path} is refused")
    check(read(None, "/forms/intake/items", project=PROJECT).status_code == 401, "signed out: 401")
    ok("a user without the intake word is refused (403) and a stranger is signed out (401)")
    cli = Path(outfile).read_text(encoding="utf-8")
    with open_uow(as_target(os.environ["TL_DB"]), readonly=True) as uow:
        code_id = (
            uow.conn()
            .execute(
                text("SELECT id FROM cur_forms_intake_code WHERE heading = :h"),
                {"h": "Poster at gate 3"},
            )
            .scalar_one()
        )
        stored = [
            *_payloads(uow.conn(), item_a),
            *_payloads(uow.conn(), item_b),
            *_payloads(uow.conn(), str(code_id)),
        ]
    shown_once = cli.replace(f"code {code}", "", 1)  # the one line that prints the code
    for name, blob in (("a read", "\n".join(seen)), ("the CLI output", shown_once)):
        for secret in secrets:
            check(secret not in blob, f"{name} holds a secret ({secret[:4]}...)")
    for secret in secrets[:2]:  # the code, plain and grouped: never stored (its hash is, by design)
        check(secret not in "\n".join(stored), f"the ledger rows hold a secret ({secret[:4]}...)")
    ok(
        "code, hash, salt and stored body are in no read or CLI output; the code is in no ledger row"
    )
    world.close()


def _payloads(conn: Connection, stream: str) -> list[str]:
    found = conn.execute(
        text("SELECT CAST(payload AS TEXT) FROM events WHERE stream_id = :s"), {"s": stream}
    )
    return [str(p) for p in found.scalars()]


def _template_id(world: World, key: str) -> str:
    got = world.get("mokafor", "/forms/templates", limit=500).json()["rows"]
    return next(r["id"] for r in got if r["key"] == key)


def budget() -> None:
    world = World()
    slowest = 0.0
    for who in ("treyes", "mokafor"):
        for name, path, params in (
            ("templates", "/forms/templates", {}),
            ("submissions", "/forms/submissions", {"project": PROJECT, "limit": 500}),
        ):
            took: list[float] = []
            with world.http(who) as client:
                for _ in range(5):
                    began = time.perf_counter()
                    got = client.get(path, params=params)
                    took.append(time.perf_counter() - began)
                    check(got.status_code == 200, f"{who} {name} answered {got.status_code}")
            median = statistics.median(took)
            slowest = max(slowest, median)
            check(median < BUDGET_SECONDS, f"{who}: {name} list took {median:.2f} s")
    ok(f"every forms list read is under {BUDGET_SECONDS:.0f} s (slowest median {slowest:.3f} s)")
    world.close()


def main() -> None:
    mode, args = (sys.argv[1] if len(sys.argv) > 1 else ""), sys.argv[2:]
    table: dict[str, Any] = {
        "ledger": ledger,
        "template-file": template_file,
        "clause1": clause1,
        "clause2": clause2,
        "clause3": clause3,
        "clause4": clause4,
        "clause5": clause5,
        "clause6-pick": clause6_pick,
        "clause6-answers": clause6_answers,
        "clause6": clause6,
        "clause7": clause7,
        "clause7-mcp": clause7_mcp,
        "clause8": clause8,
        "clause10-stage": clause10_stage,
        "clause10-args": clause10_args,
        "clause10": clause10,
        "clause11": clause11,
        "budget": budget,
    }
    if mode not in table:
        raise SystemExit(f"unknown mode {mode!r}")
    table[mode](*args)


if __name__ == "__main__":
    main()
