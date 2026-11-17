"""`tl report` rows for the in-process world modules (V3-P0): form submissions and templates and the
correspondence register. Header pinned, row count equal to the module's list view for the same
viewer, a restricted record present for a controller and absent for a low viewer, the low viewer's
output byte-identical to a ledger where that record never existed (hidden == missing), JSONL equal
to the CSV rows, and the command itself (list, CSV to a file, errors, no id column).
"""

from __future__ import annotations

import csv
import io
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from unittest import mock

import pytest
from tl_adapters.db import DbTarget, create_schema, open_uow
from tl_core import confidentiality as cf
from tl_core.modules import module_reports
from tl_core.report_out import render
from tl_mod_forms import views as forms_views

_ROOT = Path(__file__).resolve().parents[2] / "packages"
for _tests in ("tl-modules/forms/tests", "tl-api/tests"):
    if str(_ROOT / _tests) not in sys.path:
        sys.path.insert(0, str(_ROOT / _tests))

from forms_world import SCOPE, World  # noqa: E402

SUBMISSION_HEADER = (
    "key,state,template,template_version,subject,answer_class,author,submitted_on,reviewed_by,"
    "reviewed_on\n"
)
TEMPLATE_HEADER = (
    "key,title,version,state,intake,purpose,answer_class,bound_record_type,field_count,"
    "published_on,retired_on\n"
)
REGISTER_HEADER = (
    "number,kind,state,direction,domain,subtype,date,counterparty,response_due,class,subject\n"
)


def build(db: DbTarget, *, secret: bool) -> World:
    """People, one open template with two submissions and a draft; with ``secret`` also a
    restricted template with a restricted submission and a restricted letter, made last so the
    numbers of everything else are the same with and without them."""
    create_schema(db)
    world = World(db)
    world.people()
    open_tpl = world.template()
    world.submit("uma", open_tpl)
    world.submit("rob", open_tpl)
    world.save("uma", open_tpl)  # a draft: its author's alone
    if secret:
        restricted = world.template(answer_class="restricted")
        world.submit("dora", restricted)
        world.hidden_record()
    return world


@pytest.fixture
def pair(new_db: Callable[[], DbTarget]) -> tuple[World, World]:
    return build(new_db(), secret=True), build(new_db(), secret=False)


def viewer(world: World, who: str) -> cf.Viewer:
    with open_uow(world.db, readonly=True) as uow:
        return cf.viewer_for_actor(uow.conn(), f"user:{who}")


def text_of(world: World, name: str, who: str, fmt: str = "csv") -> str:
    seen = viewer(world, who)
    with open_uow(world.db, readonly=True) as uow:
        return "".join(render(module_reports()[name], uow.conn(), SCOPE, seen, fmt))


def table(body: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(body)))


def test_the_headers_are_pinned(pair: tuple[World, World]) -> None:
    world = pair[0]
    assert text_of(world, "form-submissions", "dora").startswith(SUBMISSION_HEADER)
    assert text_of(world, "form-templates", "dora").startswith(TEMPLATE_HEADER)
    assert text_of(world, "correspondence", "dora").startswith(REGISTER_HEADER)
    assert text_of(world, "form-submissions", "vera").splitlines(True)[0] == SUBMISSION_HEADER


@pytest.mark.parametrize("who", ["dora", "vera", "uma"])
def test_row_counts_equal_the_list_views(pair: tuple[World, World], who: str) -> None:
    world = pair[0]
    seen = viewer(world, who)
    with open_uow(world.db, readonly=True) as uow, cf.use_viewer(seen):
        subs = forms_views.submission_list(uow.conn(), SCOPE, viewer=seen).total
        tpls = forms_views.template_list(uow.conn(), viewer=seen).total
    assert len(table(text_of(world, "form-submissions", who))) == subs
    assert len(table(text_of(world, "form-templates", who))) == tpls


def test_a_draft_is_its_authors_row_alone(pair: tuple[World, World]) -> None:
    world = pair[0]
    states = lambda who: [r["state"] for r in table(text_of(world, "form-submissions", who))]  # noqa: E731
    assert states("uma").count("Draft") == 1
    assert "Draft" not in states("rob")
    assert "Draft" not in states("dora")


def test_a_restricted_record_is_a_row_for_a_controller_and_none_for_a_low_viewer(
    pair: tuple[World, World],
) -> None:
    world = pair[0]
    assert "restricted" in text_of(world, "form-submissions", "dora")
    assert "restricted" not in text_of(world, "form-submissions", "vera")
    assert "Secret" in text_of(world, "correspondence", "dora")
    assert "Secret" not in text_of(world, "correspondence", "vera")


@pytest.mark.parametrize("name", ["form-submissions", "correspondence"])
@pytest.mark.parametrize("fmt", ["csv", "jsonl"])
@pytest.mark.parametrize("who", ["vera", "uma", "rob"])
def test_hidden_is_missing(pair: tuple[World, World], name: str, fmt: str, who: str) -> None:
    with_secret, without = pair
    assert text_of(with_secret, name, who, fmt) == text_of(without, name, who, fmt)


def test_a_template_is_company_wide_and_not_confidential(pair: tuple[World, World]) -> None:
    """A template's answer class governs its submissions, not the template: every viewer lists
    both templates, with the same rows (no hidden-equals-missing run is needed)."""
    world = pair[0]
    low = text_of(world, "form-templates", "vera")
    assert low == text_of(world, "form-templates", "dora")
    assert len(table(low)) == 2


def test_the_controller_sees_more_than_the_low_viewer(pair: tuple[World, World]) -> None:
    world = pair[0]
    for name in ("form-submissions", "correspondence"):
        assert len(table(text_of(world, name, "dora"))) > len(table(text_of(world, name, "vera")))


@pytest.mark.parametrize("name", ["form-submissions", "form-templates", "correspondence"])
def test_jsonl_lines_match_the_csv_rows(pair: tuple[World, World], name: str) -> None:
    world = pair[0]
    rows = table(text_of(world, name, "dora"))
    lines = [json.loads(x) for x in text_of(world, name, "dora", "jsonl").splitlines()]
    assert len(lines) == len(rows) > 0
    for line, row in zip(lines, rows, strict=True):
        assert list(line) == list(row)
        for column, value in row.items():
            raw = line[column]
            assert (value == "") == (raw is None)
            if raw is not None:
                assert value == str(raw)


def test_no_internal_id_is_a_column(pair: tuple[World, World]) -> None:
    for report in module_reports().values():
        assert not [c for c in report.columns if c == "id" or c.endswith("_id")], report.name


# --- the command ----------------------------------------------------------------------------


def run(env: dict[str, str], *args: str) -> object:
    from tl_cli.main import app
    from typer.testing import CliRunner

    return CliRunner().invoke(app, list(args), env=env)


def test_the_command_lists_writes_and_refuses(tmp_path: Path) -> None:
    env = {"TL_DB": str(tmp_path / "tl.db"), "TL_ENV": "prod"}
    assert run(env, "init").exit_code == 0  # type: ignore[attr-defined]
    with mock.patch.dict(os.environ, env):
        listed = run(env, "report")
        assert listed.exit_code == 0  # type: ignore[attr-defined]
        names = [line.split("  ")[0] for line in listed.output.splitlines()]  # type: ignore[attr-defined]
        assert names == list(module_reports())
        assert {"rfis", "correspondence", "documents", "form-submissions", "form-templates"} <= set(
            names
        )
        assert run(env, "report", "nope", "--project", "P1").exit_code == 1  # type: ignore[attr-defined]
        assert run(env, "report", "rfis").exit_code == 1  # type: ignore[attr-defined]
        assert (
            run(env, "report", "rfis", "--project", "P1", "--format", "xml").exit_code == 1  # type: ignore[attr-defined]
        )
        out = tmp_path / "rfis.csv"
        done = run(env, "report", "rfis", "--project", "P1", "--out", str(out))
        assert done.exit_code == 0  # type: ignore[attr-defined]
        assert out.read_text().splitlines()[0].startswith("number,subtype,state")
        assert "wrote 0 rows" in done.output  # type: ignore[attr-defined]
