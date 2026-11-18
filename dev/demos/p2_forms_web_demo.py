"""Driver for clause 9 of dev/demos/P2-FORMS.sh (V3-F3): a person fills forms in a browser.

Self-contained: it imports the `World` of ``p2_forms_demo`` (the ledger in TL_DB, the API at
TL_API_URL) and adds the checks the browser leg needs. The browser itself is driven by
``dev/tools/surveyjs_probe/page_probe.mjs`` (Playwright, Chromium, the web client's own CSP).
Each mode prints ``ok <what>`` lines; a miss prints ``FAIL <what>`` and exits 1.

* ``token USER``: a session token for USER (the browser's ``tl_session`` cookie).
* ``template-id KEY``: the id of the published template KEY.
* ``general-plan KEY DEST``: the plan (what to type, by question id) for the published template KEY.
* ``inspection-plan DEST``: picks a Scheduled inspection whose form hsato may fill, issues a scan
  code for it (as mokafor), writes the plan, prints ``<inspection key> <scan code>``.
* ``general-check SUBMISSION PLAN``: the API gives the submission, Submitted, by cbrooks, with the
  answers the plan typed, and its source is ``web``.
* ``inspection-check KEY PLAN``: the inspection is Done, recorded by hsato from the web, with the
  answers the plan typed, and its form is closed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import text
from tl_core import confidentiality as cf
from tl_core.auth import sessions
from tl_core.forms.types import FormBinding
from tl_mod_forms import bound
from tl_mod_qr import service
from tl_mod_qr.commands import IssueScanCode

sys.path.insert(0, str(Path(__file__).resolve().parent))
from p2_forms_demo import PASSWORD, PROJECT, World, check, miss, ok  # noqa: E402

FILL_DATE = "2026-11-12"


def plan_for(fields: list[dict[str, Any]], *, only_required: bool) -> list[dict[str, Any]]:
    """What a person types into each question the browser shows (a question shown only when
    another is answered, and a photo, are left out)."""
    steps: list[dict[str, Any]] = []
    for f in fields:
        if f["kind"] == "photo" or f.get("visible_when") is not None:
            continue
        if only_required and not f.get("required"):
            continue
        kind, value = f["kind"], f"Browser: {f['id']}"
        if kind == "number":
            low, high = f.get("min"), f.get("max")
            value = (low + high) / 2 if low is not None and high is not None else (low or high or 7)
        elif kind == "date":
            value = FILL_DATE
        elif kind == "yes_no_na":
            value = "yes"
        elif kind == "choice":
            value = f["choices"][0]
        elif kind == "multi":
            value = f["choices"][:2]
        steps.append({"id": f["id"], "kind": kind, "value": value})
    return steps


def token(user: str) -> None:
    world = World()
    _, got = sessions.sign_in(world.backend, username=user, password=PASSWORD)
    print(got)
    world.close()


def template_id(key: str) -> None:
    world = World()
    got = world.get("cbrooks", "/forms/templates", limit=500)
    check(got.status_code == 200, f"the template list answered {got.status_code}")
    found = [r["id"] for r in got.json()["rows"] if r["key"] == key and r["state"] == "Published"]
    check(len(found) == 1, f"template {key}: {len(found)} published versions")
    print(found[0])
    world.close()


def general_plan(key: str, dest: str) -> None:
    world = World()
    got = world.get("cbrooks", f"/forms/templates/{key}/versions/1")
    check(got.status_code == 200, f"template {key} answered {got.status_code}")
    steps = plan_for(got.json()["fields"], only_required=False)
    Path(dest).write_text(json.dumps(steps), encoding="utf-8")
    ok(f"{key}: {len(steps)} questions to type")
    world.close()


def inspection_plan(dest: str) -> None:
    world = World()
    rows = world.get("hsato", "/quality/inspections", project=PROJECT, state="Scheduled")
    check(rows.status_code == 200, f"the inspection list answered {rows.status_code}")
    for row in rows.json()["rows"]:
        offer = world.get("hsato", f"/forms/for/{row['key']}", project=PROJECT)
        if offer.status_code != 200 or not offer.json()["available"]:
            continue
        with world.backend(True) as uow:
            viewer = cf.viewer_for_actor(uow.conn(), "user:hsato")
            fields = bound.fields_of(uow.conn(), FormBinding.model_validate(offer.json()), viewer)
        steps = plan_for(fields, only_required=True)
        with world.backend(False) as uow:
            conn = uow.conn()
            target = str(
                conn.execute(
                    text("SELECT id FROM cur_core_record WHERE scope = :s AND key = :k"),
                    {"s": f"project:{PROJECT}", "k": row["key"]},
                ).scalar_one()
            )
            viewer = cf.viewer_for_actor(conn, "user:mokafor")
            cmd = IssueScanCode(
                actor="user:mokafor", source="demo", scope=f"project:{PROJECT}", target_id=target
            )
            with cf.use_viewer(viewer):
                issued = service.issue(uow, cmd)
        Path(dest).write_text(json.dumps(steps), encoding="utf-8")
        print(f"{row['key']} {issued.code}")
        world.close()
        return
    miss("no Scheduled inspection offers a form to hsato")


def same_value(kind: str, want: Any, got: Any) -> bool:
    if kind == "multi":
        return sorted(want) == sorted(got)
    if kind == "number":
        return float(want) == float(got)
    return bool(want == got)


def web_events(world: World, stream_key: str, *types: str) -> list[str]:
    marks = ",".join(f"'{t}'" for t in types)
    with world.backend(True) as uow:
        rows = uow.conn().execute(
            text(
                "SELECT e.source FROM events e JOIN cur_core_record r ON r.id = e.stream_id "
                f"WHERE r.key = :k AND e.event_type IN ({marks})"
            ),
            {"k": stream_key},
        )
        return [str(r.source) for r in rows]


def general_check(key: str, plan_file: str) -> None:
    world = World()
    plan = json.loads(Path(plan_file).read_text(encoding="utf-8"))
    got = world.get("cbrooks", f"/forms/submissions/{key}", project=PROJECT)
    check(got.status_code == 200, f"the submission {key} answered {got.status_code}")
    body = got.json()
    check(body["row"]["state"] == "Submitted", f"{key} is {body['row']['state']}, not Submitted")
    check(body["row"]["author"] == "user:cbrooks", "cbrooks is the author")
    stored = {a["q"]: a["value"] for a in body["answers"]}
    for step in plan:
        check(step["id"] in stored, f"no stored answer for {step['id']}")
        check(
            same_value(step["kind"], step["value"], stored[step["id"]]),
            f"{step['id']}: typed {step['value']!r}, stored {stored[step['id']]!r}",
        )
    sources = web_events(world, key, "Submission.Submitted")
    check(sources == ["web"], f"the Submitted event's source is {sources}, not ['web']")
    ok(f"{key}: Submitted by cbrooks from the web; {len(plan)} typed answers equal the stored ones")
    world.close()


def inspection_check(key: str, plan_file: str) -> None:
    world = World()
    plan = json.loads(Path(plan_file).read_text(encoding="utf-8"))
    got = world.get("mokafor", f"/quality/inspections/{key}", project=PROJECT)
    check(got.status_code == 200, f"the inspection {key} answered {got.status_code}")
    body = got.json()
    check(body["row"]["state"] == "Done", f"{key} is {body['row']['state']}, not Done")
    check(body["recorded_by"] == "user:hsato", "hsato recorded it")
    stored = {a["q"]: a["value"] for a in body["answers"]}
    for step in plan:
        check(step["id"] in stored, f"no stored answer for {step['id']}")
        check(
            same_value(step["kind"], step["value"], stored[step["id"]]),
            f"{step['id']}: typed {step['value']!r}, stored {stored[step['id']]!r}",
        )
    after = world.get("hsato", f"/forms/for/{key}", project=PROJECT)
    check(after.status_code == 200 and after.json()["reason"] == "already_recorded", "form closed")
    sources = web_events(world, key, "Inspection.ResultRecorded")
    check(bool(sources) and set(sources) == {"web"}, f"the result event's source is {sources}")
    ok(f"{key}: Done from the web by hsato; {len(plan)} typed answers stored; its form is closed")
    world.close()


MODES = {
    "token": token,
    "template-id": template_id,
    "general-plan": general_plan,
    "inspection-plan": inspection_plan,
    "general-check": general_check,
    "inspection-check": inspection_check,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in MODES:
        sys.exit(f"usage: p2_forms_web_demo.py {{{'|'.join(MODES)}}} ARGS")
    MODES[sys.argv[1]](*sys.argv[2:])
