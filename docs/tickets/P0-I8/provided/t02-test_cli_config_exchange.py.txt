"""`tl config diff|export|import` on temporary ledgers (P0-I8-T02). Provided; do not edit."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml
from tl_adapters.sqlite.uow import open_uow
from tl_cli.config_exchange import diff_line
from tl_cli.main import app
from tl_core import settings
from tl_core.services.errors import SettingLockedError
from tl_core.settings.registry import get_definition
from tl_core.settings.types import EffectiveSetting, SettingDiff
from typer.testing import CliRunner
from typer.testing import Result as RunResult

runner = CliRunner()


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, str]]:
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)
    monkeypatch.delenv("TL_SETTINGS_PLATFORM_FILE", raising=False)
    values = {"TL_DB": str(tmp_path / "tl.db")}
    assert runner.invoke(app, ["init"], env=values).exit_code == 0
    yield values


def run(env: dict[str, str], *args: str) -> RunResult:
    return runner.invoke(app, ["config", *args], env=env)


def ok(env: dict[str, str], *args: str) -> str:
    result = run(env, *args)
    assert result.exit_code == 0, (args, result.output)
    assert result.exception is None
    return result.stdout


def refused(env: dict[str, str], *args: str) -> str:
    result = run(env, *args)
    assert result.exit_code == 1, (args, result.output)
    assert result.stderr.startswith("error: ")
    return result.stderr


def put(env: dict[str, str], key: str, layer: str, value: object, **kw: object) -> None:
    """Set a key with the service (this file does not depend on the other `tl config` commands)."""
    with open_uow(Path(env["TL_DB"])) as uow:
        settings.set_setting(
            uow,
            key=key,
            layer=layer,
            value=value,
            actor="user:dev",
            source="test",
            **kw,  # type: ignore[arg-type]
        )


def lock(env: dict[str, str], key: str) -> None:
    with open_uow(Path(env["TL_DB"])) as uow:
        settings.lock_setting(
            uow, key=key, locked=True, bounds=None, actor="user:dev", source="test", reason="policy"
        )


def value(env: dict[str, str], key: str, project: str | None = None) -> object:
    with open_uow(Path(env["TL_DB"]), readonly=True) as uow:
        return settings.value_of(uow.conn(), key, project=project)


def changes(env: dict[str, str], key: str) -> int:
    with open_uow(Path(env["TL_DB"]), readonly=True) as uow:
        return len(settings.history(uow.conn(), key))


def side(key: str, value: object) -> EffectiveSetting:
    return EffectiveSetting(
        key=key,
        value=value,
        origin="default",
        modified_here=False,
        locked=False,
        bounds=None,
        scheduled=[],
        pending_effect=None,
    )


def test_diff_line_shows_both_sides() -> None:
    key = "feed.reactions.enabled"
    assert diff_line(SettingDiff(key=key, left=side(key, True), right=side(key, False))) == (
        "feed.reactions.enabled  true -> false"
    )
    tags = "feed.signal_tags"
    both = SettingDiff(key=tags, left=side(tags, ["a", "b", "c", "d"]), right=side(tags, ["x"]))
    assert diff_line(both) == "feed.signal_tags  [a, b, c, +1] -> [x]"
    assert get_definition(tags).key == tags


# --- diff ---------------------------------------------------------------------------------------


def test_diff_lists_the_keys_that_differ(env: dict[str, str]) -> None:
    assert ok(env, "diff", "default", "company") == ""
    put(env, "feed.reactions.enabled", "company", False)
    put(env, "feed.signal_tags", "project:P1", ["a", "b"])
    assert ok(env, "diff", "default", "company").splitlines() == [
        "feed.reactions.enabled  true -> false"
    ]
    assert ok(env, "diff", "company", "project:P1").splitlines() == [
        "feed.signal_tags  [safety, hold, decision, +2] -> [a, b]"
    ]
    assert len(ok(env, "diff", "default", "project:P1").splitlines()) == 2


def test_diff_refuses_a_layer_that_is_not_one(env: dict[str, str]) -> None:
    assert "not a layer" in refused(env, "diff", "company", "elsewhere")


# --- export -------------------------------------------------------------------------------------


def test_export_prints_a_yaml_document(env: dict[str, str]) -> None:
    put(env, "feed.reactions.enabled", "project:P1", False)
    document = yaml.safe_load(ok(env, "export", "--project", "P1"))
    assert document == {
        "version": 1,
        "layer": "project:P1",
        "settings": {"feed.reactions.enabled": False},
    }
    empty = yaml.safe_load(ok(env, "export", "--company"))
    assert empty["settings"] == {} and empty["layer"] == "company"


def test_export_out_writes_a_file(env: dict[str, str], tmp_path: Path) -> None:
    put(env, "feed.reactions.enabled", "company", False)
    target = tmp_path / "company.yaml"
    assert ok(env, "export", "--company", "--out", str(target)) == f"wrote {target}\n"
    assert yaml.safe_load(target.read_text(encoding="utf-8"))["settings"] == {
        "feed.reactions.enabled": False
    }


def test_export_needs_exactly_one_layer(env: dict[str, str]) -> None:
    assert "exactly one of --company, --project and --user" in refused(env, "export")
    assert "exactly one of" in refused(env, "export", "--company", "--project", "P1")


def test_the_company_export_carries_locks(env: dict[str, str]) -> None:
    lock(env, "feed.reactions.enabled")
    document = yaml.safe_load(ok(env, "export", "--company"))
    assert document["locks"] == {"feed.reactions.enabled": {"locked": True, "bounds": None}}


# --- import -------------------------------------------------------------------------------------


def write(tmp_path: Path, data: object, name: str = "in.yaml") -> Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_import_applies_a_file_to_a_layer(env: dict[str, str], tmp_path: Path) -> None:
    path = write(
        tmp_path, {"settings": {"feed.reactions.enabled": False, "feed.signal_tags": ["x"]}}
    )
    assert ok(env, "import", str(path), "--project", "P2") == "imported 2 keys into project:P2\n"
    assert value(env, "feed.reactions.enabled", "P2") is False
    assert value(env, "feed.signal_tags", "P2") == ["x"]
    assert value(env, "feed.reactions.enabled") is True


def test_an_export_is_a_template_for_another_project(env: dict[str, str], tmp_path: Path) -> None:
    put(env, "feed.reactions.enabled", "project:P1", False)
    exported = tmp_path / "p1.yaml"
    ok(env, "export", "--project", "P1", "--out", str(exported))
    assert (
        ok(env, "import", str(exported), "--project", "P2") == "imported 1 keys into project:P2\n"
    )
    assert ok(env, "diff", "project:P1", "project:P2") == ""
    assert changes(env, "feed.reactions.enabled") == 2


def test_importing_the_same_file_again_changes_nothing(env: dict[str, str], tmp_path: Path) -> None:
    path = write(tmp_path, {"settings": {"feed.reactions.enabled": False}})
    ok(env, "import", str(path), "--company")
    before = changes(env, "feed.reactions.enabled")
    ok(env, "import", str(path), "--company")
    assert changes(env, "feed.reactions.enabled") == before == 1


def test_import_takes_one_reason_for_the_keys_that_need_it(
    env: dict[str, str], tmp_path: Path
) -> None:
    path = write(tmp_path, {"settings": {"webhooks.retry.max_hours": 48}})
    assert "say why" in refused(env, "import", str(path), "--company")
    out = ok(env, "import", str(path), "--company", "--reason", "template v2")
    assert out == "imported 1 keys into company\n"
    with open_uow(Path(env["TL_DB"]), readonly=True) as uow:
        (only,) = settings.history(uow.conn(), "webhooks.retry.max_hours")
    assert only.reason == "template v2"
    risky = write(
        tmp_path, {"settings": {"webhooks.egress.allowlist": ["h.example.com"]}}, "r.yaml"
    )
    assert "accept the risk" in refused(env, "import", str(risky), "--company", "--reason", "r")
    ok(env, "import", str(risky), "--company", "--reason", "r", "--accept-risk")


def test_import_is_all_or_nothing(env: dict[str, str], tmp_path: Path) -> None:
    path = write(
        tmp_path, {"settings": {"feed.reactions.enabled": False, "lake.sync.interval": "1s"}}
    )
    assert "below the minimum" in refused(env, "import", str(path), "--company")
    assert value(env, "feed.reactions.enabled") is True
    assert changes(env, "feed.reactions.enabled") == 0


def test_import_refuses_a_bad_file_and_a_missing_one(env: dict[str, str], tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("settings: [", encoding="utf-8")
    assert "not valid YAML" in refused(env, "import", str(bad), "--company")
    unknown = write(tmp_path, {"settings": {"no.such": 1}}, "u.yaml")
    assert "there is no setting" in refused(env, "import", str(unknown), "--company")
    missing = run(env, "import", str(tmp_path / "nope.yaml"), "--company")
    assert missing.exit_code != 0
    assert "exactly one of" in refused(env, "import", str(unknown))


def test_locks_are_imported_into_the_company_only(env: dict[str, str], tmp_path: Path) -> None:
    path = write(tmp_path, {"locks": {"feed.reactions.enabled": {"locked": True, "bounds": None}}})
    assert "company layer" in refused(env, "import", str(path), "--project", "P1", "--reason", "r")
    assert ok(env, "import", str(path), "--company", "--reason", "policy") == (
        "imported 1 keys into company\n"
    )
    with open_uow(Path(env["TL_DB"])) as uow, pytest.raises(SettingLockedError):
        settings.set_setting(
            uow,
            key="feed.reactions.enabled",
            layer="project:P1",
            value=False,
            actor="user:dev",
            source="test",
        )
