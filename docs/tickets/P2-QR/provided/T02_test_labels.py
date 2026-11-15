"""The label renderer (P2-QR T02): pure functions, no database, no network, no required library."""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest
from tl_mod_qr import labels

CODE = "7KQ2M9XA4TTCP0HV"
BASE = "https://tl.example.com"


def test_format_code_groups_of_four() -> None:
    assert labels.format_code(CODE) == "7KQ2-M9XA-4TTC-P0HV"


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "7KQ2M9XA4TTCP0H",
        "7KQ2M9XA4TTCP0HVV",
        "7kq2m9xa4ttcp0hv",
        "7KQ2-M9XA-4TTC-P0H",
        "7KQ2M9XA4TTCP0H!",
    ],
)
def test_format_code_refuses_a_malformed_code(bad: str) -> None:
    with pytest.raises(labels.LabelError):
        labels.format_code(bad)


def test_label_url_is_base_web_q_code() -> None:
    assert labels.label_url(BASE, CODE) == "https://tl.example.com/web/q/7KQ2M9XA4TTCP0HV"
    assert labels.label_url("https://tl.example.com:8443", CODE).endswith(":8443/web/q/" + CODE)
    assert labels.label_url("http://localhost:8000", CODE) == "http://localhost:8000/web/q/" + CODE


@pytest.mark.parametrize(
    "base",
    [
        "",
        "http://tl.example.com",
        "https://tl.example.com/",
        "https://tl.example.com/x",
        "https://tl.example.com?a=1",
        "https://u@tl.example.com",
    ],
)
def test_label_url_refuses_a_base_the_setting_would_refuse(base: str) -> None:
    with pytest.raises(labels.LabelError):
        labels.label_url(base, CODE)


def test_label_url_refuses_a_malformed_code() -> None:
    with pytest.raises(labels.LabelError):
        labels.label_url(BASE, "short")


def test_sizes_tag_only_for_now() -> None:
    assert labels.LABEL_SIZES == {"tag": (50, 80)}
    for size in ("card", "sheet"):
        with pytest.raises(labels.LabelError, match="not available"):
            labels.render_label(code=CODE, text="x", size=size, svg="<svg/>")
    with pytest.raises(labels.LabelError):
        labels.render_label(code=CODE, text="x", size="poster", svg="<svg/>")


def test_render_contains_the_svg_the_grouped_code_and_the_page_size() -> None:
    html = labels.render_label(
        code=CODE, text="IWP P123-IWP-0042", size="tag", svg="<svg id='qr'></svg>"
    )
    assert "<svg id='qr'></svg>" in html
    assert "7KQ2-M9XA-4TTC-P0HV" in html
    assert "IWP P123-IWP-0042" in html
    assert "50mm" in html and "80mm" in html
    assert html.lstrip().lower().startswith("<!doctype html")


def test_render_never_prints_the_raw_code_run_together_or_the_url() -> None:
    html = labels.render_label(code=CODE, text=None, size="tag", svg="<svg/>")
    assert CODE not in html
    assert "/web/q/" not in html


def test_text_is_escaped_and_bounded() -> None:
    html = labels.render_label(
        code=CODE, text="<script>alert(1)</script>&", size="tag", svg="<svg/>"
    )
    assert "<script" not in html
    assert "&lt;script&gt;" in html and "&amp;" in html
    with pytest.raises(labels.LabelError):
        labels.render_label(code=CODE, text="x" * 41, size="tag", svg="<svg/>")
    labels.render_label(code=CODE, text="x" * 40, size="tag", svg="<svg/>")


def test_no_text_is_allowed_and_prints_no_text_line() -> None:
    html = labels.render_label(code=CODE, text=None, size="tag", svg="<svg/>")
    assert 'class="text"' not in html


def test_page_loads_nothing_from_outside_and_runs_no_script() -> None:
    html = labels.render_label(code=CODE, text="a", size="tag", svg="<svg/>").lower()
    for needle in (
        "<script",
        "src=",
        "href=",
        "@import",
        "url(",
        "http://",
        "https://",
        "<link",
        "<img",
    ):
        assert needle not in html


def test_without_a_qr_the_page_says_so_in_a_fixed_note() -> None:
    html = labels.render_label(code=CODE, text="a", size="tag", svg=None)
    assert labels.NO_QR_NOTE in html
    assert "<svg" not in html
    assert "7KQ2-M9XA-4TTC-P0HV" in html  # the typed code is still there


def test_label_never_prints_a_state_word() -> None:
    html = labels.render_label(code=CODE, text="Hot work", size="tag", svg="<svg/>").lower()
    for word in ("active", "green", "valid", "closed", "approved"):
        assert word not in html


# ---- make_svg: the optional library -----------------------------------------------------------


def test_make_svg_is_none_when_segno_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "segno", None)  # an import of it now raises ImportError
    assert labels.make_svg("https://tl.example.com/web/q/" + CODE) is None


def test_make_svg_uses_segno_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    class FakeQr:
        def svg_inline(self, **kw: Any) -> str:
            seen["svg_kw"] = kw
            return "<svg>fake</svg>"

    def make(content: str, **kw: Any) -> FakeQr:
        seen["content"] = content
        seen["make_kw"] = kw
        return FakeQr()

    fake = types.ModuleType("segno")
    fake.make = make  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "segno", fake)
    url = "https://tl.example.com/web/q/" + CODE
    assert labels.make_svg(url) == "<svg>fake</svg>"
    assert seen["content"] == url
    assert seen["make_kw"].get("error") == "q"
