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
* ``clause5 KEY OWN``: KEY is Accepted by the controller; OWN is Accepted by a second controller.
* ``clause7 KEY``: KEY is a submission only its author may read: every other reader gets, on the
  detail route, the bytes a missing key gets, and no list holds it.
* ``clause8 DRAFT AUTHOR``: the draft DRAFT is invisible to every reader but AUTHOR.
* ``clause6-pick``: prints the key of a Scheduled inspection whose form hsato may fill (the API
  offers it, available), and ``clause6-answers KEY DEST``: writes an answers file for it that
  answers every question the way that passes (clause 6 fills it through ``tl form record``).
* ``clause6 KEY``: the inspection KEY is Done with the result accept, recorded by hsato, and its
  form is closed (``already_recorded``); the forms module holds no submission for it.
* ``budget``: every forms list read is under one second (median of five) as treyes and mokafor.
"""

from __future__ import annotations

import json
import os
import shutil
import statistics
import sys
import time
from pathlib import Path
from typing import Any, NoReturn

import httpx2
import yaml
from tl_adapters.backend import open_backend
from tl_adapters.db import as_target
from tl_core import confidentiality as cf
from tl_core.auth import sessions
from tl_core.forms import runner
from tl_core.forms.jsonschema import to_json_schema
from tl_core.forms.surveyjs import surveyjs_unsupported, to_surveyjs
from tl_core.forms.types import FormBinding
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
        "clause5": clause5,
        "clause6-pick": clause6_pick,
        "clause6-answers": clause6_answers,
        "clause6": clause6,
        "clause7": clause7,
        "clause8": clause8,
        "budget": budget,
    }
    if mode not in table:
        raise SystemExit(f"unknown mode {mode!r}")
    table[mode](*args)


if __name__ == "__main__":
    main()
