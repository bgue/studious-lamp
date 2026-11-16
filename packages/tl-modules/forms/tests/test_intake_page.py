"""Plain page of a public intake form (P2-FORMS I02): escaped, script-free, no link, no state."""

from __future__ import annotations

import re
from typing import Any

from tl_mod_forms import intake_page as page


def fld(fid: str, kind: str = "text", **kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": fid,
        "text": f"Label {fid}",
        "kind": kind,
        "required": False,
        "unit": None,
        "min": None,
        "max": None,
        "choices": None,
        "fails_when": None,
        "section": None,
        "help": None,
        "visible_when": None,
    }
    base.update(kw)
    return base


FIELDS = [
    fld("what", required=True, help="Say what you need"),
    fld("how_many", "number", min=1, max=20, unit="pcs"),
    fld("where_", "choice", choices=["Level 1", "Level 2"]),
    fld("claim_name"),
]
KEY = "ab" * 16


def form(**kw: Any) -> str:
    args: dict[str, Any] = {
        "title": "Scaffold request",
        "heading": "Block C scaffold",
        "fields": FIELDS,
        "purpose": "request",
        "form_key": KEY,
    }
    args.update(kw)
    return page.render_form(**args)


def test_the_form_has_one_input_per_field_a_key_and_a_honeypot() -> None:
    html = form()
    assert html.startswith("<!doctype html>")
    assert '<form method="post" action="">' in html
    assert f'<input type="hidden" name="k" value="{KEY}">' in html
    assert 'name="f_what"' in html and 'name="f_how_many"' in html and 'name="f_claim_name"' in html
    assert '<select name="f_where_"' in html and "<option>Level 2</option>" in html
    assert re.search(r'<input type="number"[^>]*name="f_how_many"[^>]*min="1"[^>]*max="20"', html)
    assert re.search(r'name="f_what"[^>]*required', html)
    assert re.search(r'<input[^>]*name="website"[^>]*tabindex="-1"[^>]*autocomplete="off"', html)
    assert "Block C scaffold" in html and "Say what you need" in html and "pcs" in html


def test_nothing_in_the_page_can_run_or_leave() -> None:
    html = form()
    lowered = html.lower()
    assert "<script" not in lowered and "<iframe" not in lowered and "<a " not in lowered
    assert " style=" not in lowered and not re.search(r"\son[a-z]+=", lowered)
    assert 'content="noindex"' in lowered and 'content="no-referrer"' in lowered
    assert "javascript:" not in lowered
    urls = re.findall(r'(?:href|src|action)="([^"]*)"', html)
    assert [u for u in urls if u not in ("", "/web/static/intake.css")] == []
    assert html.count("<link ") == 1


def test_hostile_text_is_escaped_everywhere_it_lands() -> None:
    evil = '"><script>alert(1)</script><img src=x onerror=alert(1)>'
    fields = [
        fld("what", text=evil, help=evil),
        fld("pick", "choice", choices=[evil]),
        fld("amount", "number", min=0, max=9, unit=evil),
    ]
    html = form(title=evil, heading=evil, fields=fields, values={"what": evil})
    assert "<script" not in html.lower() and "<img" not in html.lower()
    assert "&lt;script&gt;" in html and "&quot;" in html
    assert "onerror=alert(1)>" not in html


def test_a_refilled_value_and_marked_fields_show_on_a_second_try() -> None:
    html = form(values={"what": "Two boards", "claim_name": "Sam"}, error_ids=["how_many"])
    assert 'value="Two boards"' in html and 'value="Sam"' in html
    assert re.search(r'name="f_how_many"[^>]*aria-invalid="true"', html)
    assert "aria-invalid" not in html.split('name="f_what"')[1].split(">")[0]


def test_the_purpose_line_differs_and_a_sign_on_says_it_is_not_a_sign_in() -> None:
    request, sign_on = form(), form(purpose="sign_on")
    assert request != sign_on
    assert "not a sign-in" in sign_on.lower() and "confirm" in sign_on.lower()
    assert "not a sign-in" not in request.lower()


def test_the_fixed_pages_are_constant_and_say_nothing_about_a_record() -> None:
    assert page.render_not_found() == page.render_not_found()
    for html in (page.render_not_found(), page.render_full(), page.render_busy()):
        assert "<script" not in html.lower() and html.startswith("<!doctype html>")
    assert len({page.render_not_found(), page.render_full(), page.render_busy()}) == 3
    thanks = page.render_thanks("KITE-42", "request")
    assert "KITE-42" in thanks and "KITE-42" not in page.render_thanks("OTHER-1", "request")
    assert page.render_thanks("<b>x</b>", "request").count("<b>") == 0
    assert "not a sign-in" in page.render_thanks("A-1", "sign_on").lower()
