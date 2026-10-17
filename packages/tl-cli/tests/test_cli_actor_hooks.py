"""Every `--actor` option of the CLI is hooked and checked, and `tl derive` cannot act as another.

The hook (`tl_cli.actor_hook`) only installs on an option that is named `actor`, has the flag
`--actor` and defaults to `user:dev`. A command that declares it otherwise would take any actor
unchecked, so this walks the whole command tree (security review of P1-I3, finding 2).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
import typer.main
from auth_support import bootstrap, sign_in
from auth_support import run as tl
from derivecli_support import csv_file, derive_env, seed
from tl_adapters.db import DbTarget, as_target, is_postgres
from tl_cli import actor_hook
from tl_cli.main import app


def commands(command: Any, path: tuple[str, ...] = ()) -> Iterator[tuple[tuple[str, ...], Any]]:
    yield path, command
    for name, sub in getattr(command, "commands", {}).items():
        yield from commands(sub, (*path, name))


#: `--actor` here names a label, not who writes: the header of the TUI, and the actor a development
#: token is made for (a dev convenience that writes no event).
NOT_ACTING = {"tui", "dev token add"}


def test_every_actor_option_in_the_tree_is_hooked(tmp_path: Path) -> None:
    root = typer.main.get_command(app)
    actor_hook.install(root, tmp_path / "x.db")
    unhooked: list[str] = []
    seen = 0
    for path, command in commands(root):
        for param in getattr(command, "params", []):
            if getattr(param, "name", None) == "actor" or "--actor" in getattr(param, "opts", []):
                seen += 1
                hooked = isinstance(param.default, actor_hook._ActorDefault)  # pyright: ignore[reportPrivateUsage]
                checked = getattr(param.callback, "tl_checked", False)
                if not (hooked and checked):
                    unhooked.append(" ".join(path))
    assert seen > 40, "the walk found too few --actor options: is the tree being walked?"
    assert set(unhooked) <= NOT_ACTING, f"--actor is not hooked on: {unhooked}"


def test_every_derive_command_that_writes_has_the_hooked_actor_option(tmp_path: Path) -> None:
    root = typer.main.get_command(app)
    actor_hook.install(root, tmp_path / "x.db")
    derive = root.commands["derive"]  # type: ignore[attr-defined]
    writing = {
        ("schema", "register"),
        ("schema", "retire"),
        ("open",),
        ("content",),
        ("start",),
        ("cancel",),
        ("validate",),
        ("publish",),
        ("compensate",),
    }
    found = {path[1:] for path, cmd in commands(derive, ("derive",)) if cmd is not derive}
    assert writing <= found
    for path, command in commands(derive, ("derive",)):
        if path[1:] in writing:
            assert any("--actor" in getattr(p, "opts", []) for p in command.params), path


@pytest.fixture
def env(
    new_db: Callable[[], DbTarget], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> dict[str, str]:
    values = derive_env(new_db, monkeypatch, tmp_path)
    seed(values, tmp_path)
    return values | {"TL_ENV": "prod"}  # no setup that lets a file's owner act as anyone


def test_without_a_session_derive_cannot_act_as_someone(
    env: dict[str, str], tmp_path: Path
) -> None:
    if is_postgres(as_target(env["TL_DB"])):
        pytest.skip("on Postgres the conftest signs a session in for every command")
    data = csv_file(tmp_path, [("47-FV-1001", "Feed", "CV", "4")])
    result = tl(
        env,
        "derive",
        "content",
        "ISD-001@A/instrument-index",
        str(data),
        "--project",
        "P123",
        "--actor",
        "user:ceo",
    )
    assert result.exit_code == 1 and "not signed in" in result.output


def test_a_signed_in_person_cannot_name_another_actor(env: dict[str, str], tmp_path: Path) -> None:
    if is_postgres(as_target(env["TL_DB"])):
        pytest.skip("the conftest signs the same test user in on Postgres")
    assert bootstrap(env).exit_code == 0
    sign_in(env)
    for args in (
        ("derive", "cancel", "NOSUCH", "--project", "P123", "--actor", "user:ceo"),
        (
            "derive",
            "open",
            "ISD-001",
            "A",
            "--schema",
            "x",
            "--project",
            "P123",
            "--actor",
            "user:ceo",
        ),
        ("derive", "validate", "K", "--project", "P123", "--actor", "user:ceo"),
    ):
        result = tl(env, *args)
        assert result.exit_code == 1 and "is not the signed-in user" in result.output, args
