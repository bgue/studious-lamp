"""The data block of the fill page (V3-F3, D29): text from a template cannot end it or add markup.

A template whose title, question text, help and choices hold ``</script><script>alert(1)</script>``,
``<!--``, quotes, an ampersand and an ``<img onerror>`` renders a block that parses as JSON equal to
the model, that no HTML parser ends early, and a page with no other script and no markup from the
template.
"""

from __future__ import annotations

import json
from html.parser import HTMLParser
from types import ModuleType
from typing import Any

PROJECT = "P123"
EVIL = "</script><script>alert(1)</script>"


class Scripts(HTMLParser):
    """Counts scripts and elements the page should not have, as a browser's parser would."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.scripts = 0
        self.tags: list[str] = []
        self.data: list[str] = []
        self._in_script = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append(tag)
        if tag == "script":
            self.scripts += 1
            self._in_script = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._in_script = False

    def handle_data(self, data: str) -> None:
        if self._in_script:
            self.data.append(data)


def planted(fw: Any) -> Any:
    web = fw.world.web("bob")
    return web.client.get(f"/web/forms/t/{fw.ids['plant']}", params={"project": PROJECT})


def test_the_block_parses_as_the_model_and_no_parser_ends_it_early(
    forms_world_ro: Any, htmlkit: ModuleType
) -> None:
    got = planted(forms_world_ro)
    assert got.status_code == 200
    body = got.text
    assert "</script><script>alert(1)" not in body and "<!--" not in body
    assert "<img src=x" not in body
    doc = htmlkit.parse(body)
    block = doc.by_id("form-model")
    assert block is not None
    model = json.loads(block.text())
    elements = model["pages"][0]["elements"]
    assert elements[0]["title"].startswith(EVIL) and "<!--" in elements[0]["title"]
    assert elements[0]["description"].startswith(EVIL)
    assert elements[1]["choices"][0].startswith(EVIL) and elements[1]["choices"][1] == "b"
    assert '"q"' in elements[0]["title"] and "'s'" in elements[0]["title"]
    assert "&" in elements[0]["title"] and "<img src=x onerror=alert(2)>" in elements[0]["title"]


def test_the_page_has_the_three_vendored_scripts_forms_js_and_the_one_block(
    forms_world_ro: Any,
) -> None:
    probe = Scripts()
    probe.feed(planted(forms_world_ro).text)
    assert probe.scripts == 4  # core, renderer, forms.js and the data block
    assert probe.tags.count("img") == 0 and probe.tags.count("i") == 0
    assert len(probe.data) == 1  # one script body: the JSON block
    assert json.loads(probe.data[0])["pages"]


def test_the_title_of_the_page_is_escaped_text(forms_world_ro: Any, htmlkit: ModuleType) -> None:
    doc = htmlkit.parse(planted(forms_world_ro).text)
    heading = next(n for n in doc.all() if n.tag == "h1")
    assert heading.text().startswith(EVIL)
    assert [n for n in doc.all() if n.tag == "img"] == []
