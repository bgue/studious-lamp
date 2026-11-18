"""The fill page in a real browser (V3-F3, W2 probe clause): ``surveyjs_probe/page_probe.mjs``.

The test app is served on an ephemeral loopback port, a person is signed in with a test session,
and Chromium (Playwright) loads the real page under the web client's own CSP: the survey renders,
answers are typed through the DOM, a draft is saved and resumed, the form is sent, and no CSP
violation, console error or foreign request happens. Text from a template shows as text (a title
that is ``<img onerror>`` makes no element). Skipped when node, playwright or Chromium is missing.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from sqlalchemy import text

PROBE = Path(__file__).resolve().parents[3] / "dev" / "tools" / "surveyjs_probe" / "page_probe.mjs"
PROJECT = "P123"


def _browser_ready() -> bool:
    node = shutil.which("node")
    if node is None:
        return False
    found = subprocess.run(
        [
            node,
            "-e",
            "const {chromium}=require('playwright');"
            "process.exit(require('fs').existsSync(chromium.executablePath())?0:1)",
        ],
        capture_output=True,
        check=False,
    )
    return found.returncode == 0


pytestmark = pytest.mark.skipif(not _browser_ready(), reason="node, playwright or Chromium missing")


class Live:
    def __init__(self, app: Any) -> None:
        config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error")
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def __enter__(self) -> str:
        self.thread.start()
        while not self.server.started:
            self.thread.join(0.05)
        port = self.server.servers[0].sockets[0].getsockname()[1]
        return f"http://127.0.0.1:{port}"

    def __exit__(self, *_: object) -> None:
        self.server.should_exit = True
        self.thread.join(10)


@pytest.fixture
def live(forms_world: Any) -> Iterator[tuple[str, Any]]:
    with Live(forms_world.world.app) as origin:
        yield origin, forms_world


def browse(
    origin: str, fw: Any, who: str, path: str, plan: list[dict[str, Any]], **env: str
) -> subprocess.CompletedProcess[str]:
    token = fw.world.token(who)
    import os

    return subprocess.run(
        ["node", str(PROBE), origin, token, path, json.dumps(plan)],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, **env},
        timeout=90,
    )


def answers_of(fw: Any, key: str) -> dict[str, Any]:
    with fw.world.backend(True) as uow:
        raw = (
            uow.conn()
            .execute(
                text(
                    "SELECT answers_json FROM cur_forms_submission s "
                    "JOIN cur_core_record r ON r.id = s.id WHERE r.key = :k"
                ),
                {"k": key},
            )
            .scalar_one()
        )
    return {a["q"]: a["value"] for a in json.loads(raw)}


def test_a_person_fills_and_sends_a_general_form_in_the_browser(live: Any) -> None:
    origin, fw = live
    plan = [
        {"id": "topic", "kind": "text", "value": "Ladders"},
        {"id": "count", "kind": "number", "value": 5},
    ]
    done = browse(origin, fw, "bob", f"/web/forms/t/{fw.ids['talk']}?project={PROJECT}", plan)
    assert done.returncode == 0, done.stdout + done.stderr[-500:]
    assert "ok no CSP violation" in done.stdout and "ok submitted" in done.stdout
    assert "Received P123-FRM-0001" in done.stdout
    assert answers_of(fw, "P123-FRM-0001") == {"topic": "Ladders", "count": 5}


def test_a_draft_saved_in_the_browser_is_resumed_and_sent(live: Any) -> None:
    origin, fw = live
    path = f"/web/forms/t/{fw.ids['talk']}?project={PROJECT}"
    saved = browse(
        origin, fw, "bob", path, [{"id": "topic", "kind": "text", "value": "Draft topic"}],
        PAGE_PROBE_DRAFT="1", PAGE_PROBE_NO_SUBMIT="1",
    )  # fmt: skip
    assert saved.returncode == 0, saved.stdout + saved.stderr[-500:]
    draft = next(line.split()[1] for line in saved.stdout.splitlines() if line.startswith("draft "))
    resumed = browse(
        origin, fw, "bob", f"{path}&draft={draft}", [{"id": "count", "kind": "number", "value": 3}],
        PAGE_PROBE_VALUES=json.dumps({"topic": "Draft topic"}),
    )  # fmt: skip
    assert resumed.returncode == 0, resumed.stdout + resumed.stderr[-500:]
    assert "ok topic holds its saved value" in resumed.stdout
    assert answers_of(fw, "P123-FRM-0001") == {"topic": "Draft topic", "count": 3}


def test_a_template_that_is_markup_shows_as_text_and_makes_no_element(live: Any) -> None:
    origin, fw = live
    evil = "<img src=x onerror=alert(2)>"
    shown = browse(
        origin, fw, "bob", f"/web/forms/t/{fw.ids['plant']}?project={PROJECT}", [],
        PAGE_PROBE_TEXT=json.dumps([evil]), PAGE_PROBE_NO=json.dumps(["img", "i", "script"]),
        PAGE_PROBE_NO_SUBMIT="1",
    )  # fmt: skip
    assert shown.returncode == 0, shown.stdout + shown.stderr[-500:]
    assert f"ok shows as text: {evil[:30]}" in shown.stdout


def test_an_inspection_is_filled_from_its_page_and_recorded_by_the_typed_command(live: Any) -> None:
    origin, fw = live
    key = fw.keys["insp_open"]
    plan = [{"id": "q1", "kind": "yes_no_na", "value": "yes"}]
    done = browse(origin, fw, "bob", f"/web/forms/for/{key}?project={PROJECT}", plan)
    assert done.returncode == 0, done.stdout + done.stderr[-500:]
    assert f"/web/p/{PROJECT}/records/{fw.ids['insp_open']}" in done.stdout
    with fw.world.backend(True) as uow:
        sources = (
            uow.conn()
            .execute(
                text(
                    "SELECT source FROM events WHERE stream_id = :i "
                    "AND event_type = 'Inspection.ResultRecorded'"
                ),
                {"i": fw.ids["insp_open"]},
            )
            .scalars()
            .all()
        )
    assert list(sources) == ["web"]
