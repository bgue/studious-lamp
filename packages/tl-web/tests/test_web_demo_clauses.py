"""The demo clauses of the spec (``docs/build-spec/specs/web-client-i1.md`` section 12), in process.

One function per clause, end to end through the app: sign-in, the RFI log, actions with CSRF, the
document log with the viewer and the bytes, and the technical mode. SQLite only (see
``conftest.py``).
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from tl_adapters.db import open_uow
from tl_cli.rfi import _line  # pyright: ignore[reportPrivateUsage]
from tl_core.confidentiality import use_viewer, viewer_for
from tl_mod_correspondence import reports_technical
from tl_web import present

P = "/web/p/P123"


def tl_rfi_ls(w: Any, name: str) -> list[str]:
    """The lines of ``tl rfi ls`` for the project, as the CLI's own text function writes them, for
    the viewer ``name`` would be (the CLI itself reads as the lowest clearance)."""
    principal = w.principal(name)
    with use_viewer(viewer_for(principal)), open_uow(w.target, readonly=True) as uow:
        log = reports_technical.rfi_log(uow.conn(), "project:P123")
    return [_line(line) for line in log.lines]


def test_clause_1_sign_in_is_a_303_with_a_strict_cookie_and_the_json_api_ignores_it(
    fresh_world: Any, k: Any
) -> None:
    w = fresh_world
    response = w.client().post("/web/sign-in", data={"username": "bob", "password": k.PASSWORD})
    assert response.status_code == 303
    attrs = k.cookie_attrs(response.headers["set-cookie"])
    assert "HttpOnly" in attrs and "SameSite=Strict" in attrs
    token = response.headers["set-cookie"].split(";")[0].partition("=")[2]
    jar = w.client(token)
    assert jar.post("/commands/AnswerTechnical", json={}).status_code == 401  # cookie ignored


def test_clause_2_the_rfi_log_has_seven_regions_and_the_rows_of_tl_rfi_ls(
    fresh_world: Any, htmlkit: Any
) -> None:
    w = fresh_world
    bob, ctl = w.web("bob").client, w.web("ctl").client
    plain = htmlkit.parse(bob.get(f"{P}/rfis").text)
    controller = htmlkit.parse(ctl.get(f"{P}/rfis").text)
    assert plain.regions() == list(htmlkit.LOG_REGIONS) == controller.regions()
    for name, doc in (("bob", plain), ("ctl", controller)):
        cli = tl_rfi_ls(w, name)
        rows = doc.log_rows()
        assert len(rows) == len(cli) >= 4, name
        for line, row in zip(cli, rows, strict=True):  # the same RFIs in the same order
            number = row.get("data-number")
            cells = doc.cells(row)
            assert line.startswith(f"{number} "), (name, line, number)
            assert line.endswith(cells[1]), (name, line, cells)  # the subject
    numbers = {"bob": [r.get("data-number") for r in plain.log_rows()],
               "ctl": [r.get("data-number") for r in controller.log_rows()]}  # fmt: skip
    restricted = w.numbers["restricted_rfi"]
    assert restricted not in numbers["bob"] and restricted in numbers["ctl"]
    hidden = bob.get(f"{P}/rfis/panel/{restricted}")
    assert hidden.status_code == 404
    assert hidden.content == bob.get("/web/nowhere").content  # the generic 404 page
    assert "RESTSECRET" not in hidden.text and restricted not in hidden.text


def test_clause_3_the_panel_offers_only_what_is_offered_and_an_action_needs_the_csrf_token(
    fresh_world: Any, htmlkit: Any
) -> None:
    w = fresh_world
    web = w.web("bob")
    number, rid = w.numbers["waiting"], w.ids["waiting"]
    offered = [a["command"] for a in w.api("bob").get(f"/records/{rid}/actions").json()["actions"]]
    panel = htmlkit.parse(web.client.get(f"{P}/rfis/panel/{number}").text)
    assert panel.commands() == [c for c in offered if c in present.ACTION_UI]
    assert "AnswerTechnical" in panel.commands()
    url = f"{P}/records/{rid}/do/AnswerTechnical"
    form = {"answer": "Reroute it.", "cost_impact": "yes", "schedule_impact": "no"}
    before = w.events()
    bare = web.client.post(url, data=form, headers={"Origin": "http://127.0.0.1"})
    assert bare.status_code == 403 and bare.json()["error"] == "csrf_refused"
    assert w.events() == before
    done = web.client.post(url, data=form, headers=web.headers())
    assert done.status_code == 200
    after = htmlkit.parse(web.client.get(f"{P}/rfis/panel/{number}").text)
    assert after.pre() != panel.pre()  # the panel shows the new state
    assert "Answered" in after.pre()
    assert "AnswerTechnical" not in after.commands()


def test_clause_4_the_document_log_shows_page_1_the_viewer_has_the_csp_and_the_bytes_hash_matches(
    fresh_world: Any, htmlkit: Any, k: Any
) -> None:
    w = fresh_world
    bob = w.web("bob").client
    log = htmlkit.parse(bob.get(f"{P}/documents").text)
    pictures = [i.get("src") for i in log.images("log-panel")]
    assert len(pictures) == 1  # the selected row is the PDF revision ISO-9002
    found = re.fullmatch(r"/web/files/([0-9A-Z]+)/page1\.png\?scope=project%3AP123", pictures[0])
    assert found is not None
    file_id = found.group(1)
    viewer = bob.get(f"{P}/files/{file_id}/view")
    assert viewer.status_code == 200
    assert viewer.headers["content-security-policy"] == k.CSP
    info = w.api("bob").get(f"/files/{file_id}?scope=project:P123").json()
    body = bob.get(f"/web/files/{file_id}/content?scope=project%3AP123")
    assert body.status_code == 200
    assert hashlib.sha256(body.content).hexdigest() == info["sha256"]


def test_clause_5_technical_mode_shows_ids_to_an_admin_and_the_notice_to_a_plain_user(
    fresh_world: Any, htmlkit: Any
) -> None:
    w = fresh_world
    number, rid = w.numbers["open"], w.ids["open"]
    boss = htmlkit.parse(
        w.web("boss")
        .client.get(f"{P}/correspondence/panel/{number}", params={"mode": "technical"})
        .text
    )
    assert rid in boss.pre()
    bob = htmlkit.parse(
        w.web("bob").client.get(f"{P}/correspondence", params={"mode": "technical"}).text
    )
    assert "for admins" in bob.status()
    assert rid not in bob.visible_text()
