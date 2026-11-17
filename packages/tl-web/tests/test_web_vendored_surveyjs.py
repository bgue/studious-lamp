"""The vendored SurveyJS renderer (P2-FORMS-W1): pinned, unedited, MIT, nothing else beside it."""

from __future__ import annotations

import hashlib
import importlib.util
import tomllib
from pathlib import Path
from typing import Any

import pytest

WEB_SRC = Path(__file__).resolve().parents[1] / "src" / "tl_web"
VENDOR = WEB_SRC / "static" / "vendor"
DIR = VENDOR / "surveyjs"
ROOT = Path(__file__).resolve().parents[3]

CORE = "https://registry.npmjs.org/survey-core/-/survey-core-3.2.5.tgz"
UI = "https://registry.npmjs.org/survey-js-ui/-/survey-js-ui-3.2.5.tgz"
LICENCE_URL = "https://raw.githubusercontent.com/surveyjs/survey-library/v3.2.5/LICENSE"
ROWS = {
    "survey-core": (
        "surveyjs/survey.core.min.js",
        CORE,
        "46f07eca3a1f07fbafff2864bfc31cb9ab766e8a25dfc2375dcc02df2dbcd253",
    ),
    "survey-core-css": (
        "surveyjs/survey-core.min.css",
        CORE,
        "68fa8ad13a6e09935fbb93baee388c4054576a6524419e3e477a3ae671ad8f41",
    ),
    "survey-js-ui": (
        "surveyjs/survey-js-ui.min.js",
        UI,
        "66587c72ecee48222d9fd2ffc02f603dfe0890631e85204c625a50a582df42f5",
    ),
    "surveyjs-licence": (
        "surveyjs/LICENSE",
        LICENCE_URL,
        "ef2cef07ff83d3ab514f530d85b8b86eb5979f2897eabb875cb69c2bbd8ee611",
    ),
}
CORE_JS = DIR / "survey.core.min.js"
UI_JS = DIR / "survey-js-ui.min.js"
CSS = DIR / "survey-core.min.css"


def rows() -> dict[str, dict[str, Any]]:
    data = tomllib.loads((VENDOR / "VENDORED.toml").read_text(encoding="utf-8"))["file"]
    return {e["name"]: e for e in data if e["path"].startswith("surveyjs/")}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_the_four_rows_are_fixed_and_each_file_hashes_to_its_row() -> None:
    found = rows()
    assert set(found) == set(ROWS)
    for name, (path, url, digest) in ROWS.items():
        row = found[name]
        assert row["path"] == path and row["url"] == url, name
        assert row["version"] == "3.2.5" and row["licence"] == "MIT", name
        assert row["sha256"] == digest, name
        assert sha(VENDOR / path) == digest, name


def test_the_licence_is_the_upstream_text() -> None:
    text = (DIR / "LICENSE").read_text(encoding="utf-8")
    assert text.startswith("MIT License")
    assert "Devsoft Baltic" in text


def test_the_directory_holds_only_the_four_files() -> None:
    assert {p.name for p in DIR.rglob("*")} == {
        "survey.core.min.js",
        "survey-core.min.css",
        "survey-js-ui.min.js",
        "LICENSE",
    }


@pytest.mark.parametrize("path", [CORE_JS, UI_JS])
def test_the_scripts_have_no_eval_and_say_mit(path: Path) -> None:
    data = path.read_bytes()
    assert b"eval(" not in data and b"new Function" not in data
    assert b"License: MIT" in data[:400]


def test_the_stylesheet_loads_nothing() -> None:
    css = CSS.read_bytes().lower()
    for word in (b"url(", b"@import", b"@font-face"):
        assert word not in css, word


def test_just_checks_licence_step_accepts_the_manifest() -> None:
    spec = importlib.util.spec_from_file_location(
        "check_licences_w1", ROOT / "dev" / "tools" / "check_licences.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.vendored_problems(VENDOR / "VENDORED.toml") == []


@pytest.mark.parametrize(
    ("path", "kind"),
    [
        ("survey.core.min.js", "javascript"),
        ("survey-js-ui.min.js", "javascript"),
        ("survey-core.min.css", "css"),
    ],
)
def test_the_files_are_served_with_the_standard_headers(
    light_world: Any, k: Any, path: str, kind: str
) -> None:
    served = light_world.client().get(f"/web/static/vendor/surveyjs/{path}")  # no session
    assert served.status_code == 200
    assert kind in served.headers["content-type"]
    assert served.headers["x-content-type-options"] == "nosniff"
    assert served.headers["referrer-policy"] == "same-origin"
    assert served.headers["content-security-policy"] == k.CSP
    assert hashlib.sha256(served.content).hexdigest() == sha(DIR / path)
