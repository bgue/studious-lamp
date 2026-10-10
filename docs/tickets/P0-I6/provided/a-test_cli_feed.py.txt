"""`tl feed post|ls|retract|react` on a temporary ledger (P0-I6-T05). Provided; do not edit."""

from __future__ import annotations

from pathlib import Path

import pytest
from tl_cli.main import app
from typer.testing import CliRunner
from typer.testing import Result as RunResult

runner = CliRunner()
P = "P123"


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)
    values = {"TL_DB": str(tmp_path / "tl.db")}
    assert runner.invoke(app, ["init"], env=values).exit_code == 0
    return values


def run(env: dict[str, str], *args: str) -> RunResult:
    return runner.invoke(app, list(args), env=env)


def create(env: dict[str, str], title: str) -> str:
    result = run(env, "record", "create", "--project", P, "--title", title)
    assert result.exit_code == 0, result.output
    return next(line.split()[1] for line in result.stdout.splitlines() if line.startswith("key "))


def post(env: dict[str, str], body: str, *extra: str) -> RunResult:
    return run(env, "feed", "post", "--project", P, body, *extra)


def post_id(result: RunResult) -> str:
    assert result.exit_code == 0, result.output
    first = result.stdout.splitlines()[0].split()
    assert first[0] == "posted" and len(first[1]) == 26
    return first[1]


def ls(env: dict[str, str], *extra: str) -> list[str]:
    result = run(env, "feed", "ls", "--project", P, *extra)
    assert result.exit_code == 0, result.output
    return result.stdout.splitlines()


def column(lines: list[str], index: int) -> list[str]:
    """One two-space-separated column of the `ls` lines (0: id, 1: kind)."""
    return [line.split("  ")[index] for line in lines]


def test_the_feed_group_is_in_the_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert "feed" in result.stdout
    assert "post" in runner.invoke(app, ["feed", "--help"]).stdout


def test_post_prints_the_id_and_its_tags(env: dict[str, str]) -> None:
    result = post(env, "Bevels damaged #hold #bevel-damage @party:fab-a #area:A12")
    pid = post_id(result)
    assert result.stdout.splitlines()[1:] == [
        "tags #hold (signal), #bevel-damage (topic), @party:fab-a (mention), #area:A12 (code)"
    ]
    (line,) = ls(env, "--posts")
    assert line.startswith(f"{pid}  post  ")
    assert line.endswith("  dev !  Bevels damaged #hold #bevel-damage @party:fab-a #area:A12")


def test_a_plain_post_prints_only_its_id(env: dict[str, str]) -> None:
    result = post(env, "just a note")
    assert len(result.stdout.splitlines()) == 1
    assert post_id(result)


def test_a_record_tag_reports_the_suggested_link(env: dict[str, str]) -> None:
    key = create(env, "Gate valve")
    result = post(env, f"look at #{key}")
    post_id(result)
    assert result.stdout.splitlines()[1:] == [f"tags #{key} (record)", "suggested 1 link"]
    result = run(env, "link", "list", "--project", P, key)
    assert "suggested" in result.stdout and "referenced by" in result.stdout


def test_post_takes_an_importance_and_an_actor(env: dict[str, str]) -> None:
    post_id(post(env, "quiet", "--importance", "low", "--actor", "agent:triage"))
    (line,) = ls(env)
    assert "  agent:triage  quiet" in line


def test_post_errors(env: dict[str, str]) -> None:
    blank = post(env, "   ")
    assert blank.exit_code == 1 and blank.stderr.startswith("error: body:")
    bad = post(env, "x", "--importance", "loud")
    assert bad.exit_code == 1 and "--importance" in bad.stderr


def test_ls_lists_newest_first_with_cards_and_filters(env: dict[str, str]) -> None:
    key = create(env, "Gate valve")
    first = post_id(post(env, f"about #{key}"))
    second = post_id(post(env, "stop #hold"))
    lines = ls(env)
    kinds = [line.split("  ")[1] for line in lines]
    assert kinds == ["post", "post", "card"]
    assert lines[0].startswith(second) and lines[1].startswith(first)
    assert lines[2].endswith(f"jo created a record ({key})".replace("jo", "dev"))
    assert column(ls(env, "--posts"), 1) == ["post", "post"]
    assert column(ls(env, "--events"), 1) == ["card"]
    assert column(ls(env, "--tag", "hold"), 0) == [second]
    assert column(ls(env, "--tag", "#HOLD"), 0) == [second]
    assert column(ls(env, "--record", key, "--posts"), 0) == [first]
    assert len(ls(env, "-n", "1")) == 1


def test_ls_linked_adds_the_records_one_link_away(env: dict[str, str]) -> None:
    a, b = create(env, "A"), create(env, "B")
    assert run(env, "link", "add", "--project", P, a, b).exit_code == 0
    on_b = post_id(post(env, f"on #{b}"))
    assert ls(env, "--record", a, "--posts") == []
    assert column(ls(env, "--record", a, "--linked", "--posts"), 0) == [on_b]


def test_ls_errors(env: dict[str, str]) -> None:
    for args, text in (
        (("--record", "NOPE-1"), "no record with key"),
        (("--posts", "--events"), "exclude each other"),
        (("--linked",), "--linked needs --record"),
    ):
        result = run(env, "feed", "ls", "--project", P, *args)
        assert result.exit_code == 1 and text in result.stderr


def test_retract_leaves_a_tombstone_and_cannot_repeat(env: dict[str, str]) -> None:
    pid = post_id(post(env, "wrong project #hold"))
    result = run(env, "feed", "retract", "--project", P, pid, "--reason", "wrong project")
    assert result.exit_code == 0 and result.stdout.strip() == f"retracted {pid}"
    (line,) = ls(env, "--posts")
    assert line.endswith("  dev  [retracted]")
    assert ls(env, "--tag", "hold") == []
    again = run(env, "feed", "retract", "--project", P, pid, "--reason", "again")
    assert again.exit_code == 1 and "retracted" in again.stderr
    missing = run(env, "feed", "retract", "--project", P, "nope", "--reason", "x")
    assert missing.exit_code == 1 and "no post" in missing.stderr
    needs = run(env, "feed", "retract", "--project", P, pid)
    assert needs.exit_code != 0


def test_react_sets_and_clears_a_reaction(env: dict[str, str]) -> None:
    pid = post_id(post(env, "hello #fyi"))
    result = run(env, "feed", "react", "--project", P, pid)
    assert result.exit_code == 0 and result.stdout.strip() == f"reacted {pid} ack"
    run(env, "feed", "react", "--project", P, pid, "--reaction", "+1", "--actor", "user:ann")
    run(env, "feed", "react", "--project", P, pid, "--actor", "user:ann")
    (line,) = ls(env, "--posts")
    assert line.endswith("  [+1 1, ack 2]")
    cleared = run(env, "feed", "react", "--project", P, pid, "--off", "--actor", "user:ann")
    assert cleared.stdout.strip() == f"cleared {pid} ack"
    (line,) = ls(env, "--posts")
    assert line.endswith("  [+1 1, ack 1]")


def test_react_errors(env: dict[str, str]) -> None:
    pid = post_id(post(env, "hello"))
    assert run(env, "feed", "react", "--project", P, pid).exit_code == 0
    twice = run(env, "feed", "react", "--project", P, pid)
    assert twice.exit_code == 1 and twice.stderr.startswith("error:")
    off = run(env, "feed", "react", "--project", P, pid, "--off", "--reaction", "resolved")
    assert off.exit_code == 1
    bad = run(env, "feed", "react", "--project", P, pid, "--reaction", "thumbs")
    assert bad.exit_code == 1 and "--reaction" in bad.stderr
    gone = run(env, "feed", "react", "--project", P, "nope")
    assert gone.exit_code == 1 and "no post" in gone.stderr
