"""The licence gate (ADR-0006): GPL family refused, MPL only for an allow-list, unknown refused."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

PATH = Path(__file__).resolve().parents[2] / "dev" / "tools" / "check_licences.py"


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_licences", PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_licences"] = module
    spec.loader.exec_module(module)
    return module


MODULE = load()


def dist(
    name: str, expression: str = "", license: str = "", classifiers: tuple[str, ...] = ()
) -> object:
    return MODULE.Dist(name, expression, license, classifiers)


def problems(*dists: object) -> list[str]:
    return MODULE.problems(dists)


@pytest.mark.parametrize(
    "expression",
    [
        "MIT",
        "BSD-3-Clause",
        "Apache-2.0",
        "ISC",
        "PSF-2.0",
        "MIT-0",
        "Unlicense",
        "Apache-2.0 OR MIT",
    ],
)
def test_permissive_expressions_pass(expression: str) -> None:
    assert problems(dist("pkg", expression=expression)) == []


@pytest.mark.parametrize(
    "expression",
    ["GPL-3.0-or-later", "LGPL-3.0", "AGPL-3.0", "GPL-2.0-only WITH Classpath-exception-2.0"],
)
def test_copyleft_expressions_fail(expression: str) -> None:
    (line,) = problems(dist("pkg", expression=expression))
    assert line.startswith("pkg:") and "not allowed" in line


def test_an_alternative_that_is_permissive_rescues_a_dual_licence() -> None:
    assert problems(dist("dual", expression="MIT OR GPL-3.0-or-later")) == []


def test_and_needs_every_part_to_pass() -> None:
    assert problems(dist("both", expression="MIT AND GPL-3.0-only")) != []


def test_the_license_field_and_classifiers_are_read_when_there_is_no_expression() -> None:
    assert problems(dist("a", license="BSD License")) == []
    assert problems(dist("b", classifiers=("License :: OSI Approved :: MIT License",))) == []
    assert problems(dist("c", license="GNU Lesser General Public License v3 (LGPLv3)")) != []


def test_several_classifiers_mean_several_licences() -> None:
    docutils_like = (
        "License :: Public Domain",
        "License :: OSI Approved :: BSD License",
        "License :: OSI Approved :: GNU General Public License (GPL)",
    )
    assert problems(dist("docutils", classifiers=docutils_like)) == []
    only_gpl = ("License :: OSI Approved :: GNU General Public License (GPL)",)
    assert problems(dist("strict", classifiers=only_gpl)) != []


def test_a_long_license_field_is_licence_text() -> None:
    text = "MIT License\n\nCopyright (c) 2026 Somebody\n\n" + "Permission is hereby granted. " * 20
    assert problems(dist("texty", license=text)) == []


def test_mpl_is_allowed_only_for_the_named_distributions() -> None:
    for name in ("certifi", "tqdm", "fqdn", "hypothesis", "Hypothesis"):
        assert problems(dist(name, expression="MPL-2.0")) == []
    assert problems(dist("tqdm", license="MPL-2.0 AND MIT")) == []
    (line,) = problems(dist("newcomer", expression="MPL-2.0"))
    assert line.startswith("newcomer:")


def test_a_missing_licence_fails_and_unknown_counts_as_missing() -> None:
    assert problems(dist("nothing")) == ["nothing: no licence declared"]
    assert problems(dist("unk", license="UNKNOWN")) == ["unk: no licence declared"]


def test_an_unrecognised_licence_name_fails() -> None:
    assert problems(dist("odd", expression="LicenseRef-Proprietary")) != []


def test_workspace_packages_are_exempt() -> None:
    assert problems(dist("tl-core"), dist("tl_adapters")) == []


def test_problems_are_sorted_by_name_and_main_reports_them(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        MODULE, "collect", lambda: [dist("zeta", expression="GPL-3.0"), dist("alpha")]
    )
    assert MODULE.main() == 1
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("alpha:") and out[1].startswith("zeta:")
    monkeypatch.setattr(MODULE, "collect", lambda: [dist("fine", expression="MIT")])
    assert MODULE.main() == 0
    assert "licences ok" in capsys.readouterr().out
