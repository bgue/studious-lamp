"""V3-F2 walk: resuming a draft with ``tl form fill TEMPLATE --resume [DRAFT]``.

The author continues her own latest draft (or the one she names) and submits it; the number is
taken at submit only. Another person's draft id, and an id that never existed, answer exactly the
same words on ``--resume`` (the caller's own reference aside) for the other three readers (a user,
the document controller, an admin); a person with no draft of a template is told so without a
name. The save bound's refusal is shown as the module words it.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from pathlib import Path
from unittest import mock

import pytest
from harness import Harness
from tl_cli import session as cli_session
from tl_cli.main import app as cli_app
from tl_core.auth import sessions
from typer.testing import CliRunner

_FORMS_TESTS = str(Path(__file__).resolve().parents[2] / "packages/tl-modules/forms/tests")
if _FORMS_TESTS not in sys.path:
    sys.path.insert(0, _FORMS_TESTS)

from forms_world import PASSWORD, World, two_fields  # noqa: E402
from tl_mod_forms.errors import MSG_DRAFT_SAVES  # noqa: E402

PROJECT = "P123"
FAKE_ULID = "01J000000000000000000000"
PEOPLE = ("uma", "rob", "dora", "ada")


class Rig:
    def __init__(self, h: Harness, world: World, tmp: Path) -> None:
        self.h = h
        self.world = world
        self.tmp = tmp
        self.tokens: dict[str, str] = {}
        self.template = ""
        self.key = ""

    def cli(self, who: str, *args: str) -> tuple[int, str]:
        target = self.world.db
        env = {
            "TL_DB": str(target),
            "TL_SESSION_FILE": str(self.tmp / f"{who}.json"),
            "TL_ENV": "test",
        }
        with mock.patch.dict(os.environ, env):
            cli_session.save(
                cli_session.StoredSession(
                    target=cli_session.db_target(target),
                    username=who,
                    actor=f"user:{who}",
                    expires_at="2099-01-01T00:00:00Z",
                    token=self.tokens[who],
                )
            )
            result = CliRunner().invoke(cli_app, list(args), env=env)
        return result.exit_code, result.output

    def number_of(self, draft: str) -> str | None:
        return self.world.key(draft)


@pytest.fixture
def rig(tmp_path: Path) -> Iterator[Rig]:
    h = Harness.build(tmp_path)
    world = World(h.target or h.db)
    world.people()
    r = Rig(h, world, tmp_path)
    r.tokens = {n: sessions.sign_in(h.backend, username=n, password=PASSWORD)[1] for n in PEOPLE}
    r.template = world.template(fields=two_fields())
    r.key = str(world.key(r.template))
    yield r
    h.close()


def _saved(out: str) -> str:
    assert out.startswith("saved "), out
    return out.split()[1]


def test_resume_continues_the_latest_own_draft_and_the_number_comes_at_submit(rig: Rig) -> None:
    code, out = rig.cli(
        "uma", "form", "fill", rig.key, "--project", PROJECT, "--answer", "topic=Ladders"
    )
    assert code == 0
    draft = _saved(out)
    code, out = rig.cli(
        "uma", "form", "fill", rig.key, "--resume", "--project", PROJECT, "--answer", "count=3"
    )
    assert code == 0 and _saved(out) == draft
    assert rig.world.submission(draft)["draft_saves"] == 2
    assert rig.number_of(draft) is None  # no number while it is a draft
    code, shown = rig.cli("uma", "form", "show", draft, "--submission", "--project", PROJECT)
    assert code == 0 and "Ladders" in shown and "3" in shown  # the first answer was kept
    code, out = rig.cli("uma", "form", "submit", draft, "--project", PROJECT)
    assert code == 0 and out.startswith("submitted P123-FRM-"), out
    assert rig.number_of(draft) == out.split()[1]


def test_resume_names_a_draft_and_takes_the_latest_when_none_is_named(rig: Rig) -> None:
    first = _saved(
        rig.cli("uma", "form", "fill", rig.key, "--project", PROJECT, "--answer", "topic=A")[1]
    )
    second = _saved(
        rig.cli("uma", "form", "fill", rig.key, "--project", PROJECT, "--answer", "topic=B")[1]
    )
    assert first != second
    code, out = rig.cli("uma", "form", "fill", rig.key, "--resume", first, "--project", PROJECT)
    assert code == 0 and _saved(out) == first
    code, out = rig.cli("uma", "form", "fill", rig.key, "--resume", "--project", PROJECT)
    assert code == 0 and _saved(out) == max(first, second)


def test_a_person_with_no_draft_is_told_so_and_nothing_is_saved(rig: Rig) -> None:
    before = rig.world.count()
    code, out = rig.cli("uma", "form", "fill", rig.key, "--resume", "--project", PROJECT)
    assert code == 1 and f"no draft of {rig.key}" in out
    assert rig.world.count() == before


@pytest.mark.parametrize("who", ("rob", "dora", "ada"))
def test_another_persons_draft_answers_as_a_missing_one(rig: Rig, who: str) -> None:
    draft = _saved(
        rig.cli("uma", "form", "fill", rig.key, "--project", PROJECT, "--answer", "topic=A")[1]
    )
    before = rig.world.count()
    args = ("form", "fill", rig.key, "--project", PROJECT, "--resume")
    h_code, h_out = rig.cli(who, *args, draft)
    m_code, m_out = rig.cli(who, *args, FAKE_ULID)
    assert h_code == m_code == 1
    assert h_out.replace(draft, "<ref>") == m_out.replace(FAKE_ULID, "<ref>")
    assert "no submission" in h_out
    assert rig.world.count() == before
    assert rig.world.submission(draft)["draft_saves"] == 1  # untouched


def test_a_draft_of_another_template_is_a_miss(rig: Rig) -> None:
    other = rig.world.template(fields=two_fields())
    other_key = str(rig.world.key(other))
    draft = _saved(
        rig.cli("uma", "form", "fill", other_key, "--project", PROJECT, "--answer", "topic=A")[1]
    )
    code, out = rig.cli("uma", "form", "fill", rig.key, "--resume", draft, "--project", PROJECT)
    assert code == 1 and "no submission" in out


def test_the_save_bound_refusal_is_shown_as_the_module_words_it(rig: Rig) -> None:
    rig.world.setting("forms.draft_saves_max", 2)
    draft = _saved(
        rig.cli("uma", "form", "fill", rig.key, "--project", PROJECT, "--answer", "topic=A")[1]
    )
    code, _ = rig.cli("uma", "form", "fill", rig.key, "--resume", "--project", PROJECT)
    assert code == 0
    code, out = rig.cli("uma", "form", "fill", rig.key, "--resume", "--project", PROJECT)
    assert code == 1 and MSG_DRAFT_SAVES in out
    assert rig.world.submission(draft)["draft_saves"] == 2
    code, out = rig.cli("uma", "form", "submit", draft, "--project", PROJECT)
    assert code == 0 and out.startswith("submitted ")  # a submit is not a save
