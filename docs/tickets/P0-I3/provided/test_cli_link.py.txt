"""`tl link add|suggest|list|accept|decline|verify|repin|retract|flag` on a temporary ledger
(P0-I3-T02b; brief 7)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text
from tl_adapters.sqlite.uow import open_uow
from tl_cli.main import app
from typer.testing import CliRunner
from typer.testing import Result as RunResult

runner = CliRunner()


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """A fresh ledger and the sample schema directory (it has one expected link)."""
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)
    values = {"TL_DB": str(tmp_path / "tl.db")}
    assert runner.invoke(app, ["init"], env=values).exit_code == 0
    return values


def run(env: dict[str, str], *args: str) -> RunResult:
    return runner.invoke(app, list(args), env=env)


def create(env: dict[str, str], title: str) -> str:
    result = run(env, "record", "create", "--project", "P123", "--title", title)
    assert result.exit_code == 0, result.output
    return next(line.split()[1] for line in result.stdout.splitlines() if line.startswith("key "))


def lnk(env: dict[str, str], *args: str) -> RunResult:
    return run(env, "link", *args)


def first_word_after(result: RunResult, word: str) -> str:
    """The id on the first output line, which reads `<word> <link id>`."""
    first = result.stdout.splitlines()[0].split()
    assert first[0] == word, result.output
    return first[1]


def listing(env: dict[str, str], key: str, *extra: str) -> list[str]:
    result = lnk(env, "list", "--project", "P123", key, *extra)
    assert result.exit_code == 0, result.output
    return result.stdout.splitlines()


@pytest.fixture
def pair(env: dict[str, str]) -> tuple[str, str]:
    return create(env, "NCR"), create(env, "Support")


# --- add and list ----------------------------------------------------------------------------


def test_add_prints_the_link_and_list_shows_it_from_both_sides(
    env: dict[str, str], pair: tuple[str, str]
) -> None:
    a, b = pair
    result = lnk(env, "add", "--project", "P123", a, b)
    assert result.exit_code == 0, result.output
    lines = result.stdout.splitlines()
    assert lines[0].startswith("added ")
    link_id = lines[0].split()[1]
    assert lines[1:] == ["relation references", "status active"]

    assert listing(env, a)[:2] == [
        f"key: {a}",
        f"out  references  {b}  active  floating  {link_id}",
    ]
    assert listing(env, b)[:2] == [
        f"key: {b}",
        f"in  referenced by  {a}  active  floating  {link_id}",
    ]


def test_add_takes_a_relation_a_pin_a_note_and_an_actor(
    env: dict[str, str], pair: tuple[str, str]
) -> None:
    a, b = pair
    result = lnk(
        env,
        "add",
        "--project",
        "P123",
        a,
        b,
        "--relation",
        "blocks",
        "--pin",
        "1",
        "--note",
        "needs it",
        "--actor",
        "user:ann",
    )
    assert result.exit_code == 0, result.output
    assert "relation blocks" in result.stdout.splitlines()
    first_id = first_word_after(result, "added")
    assert listing(env, a)[1] == f"out  blocks  {b}  active  1  {first_id}"
    with open_uow(env["TL_DB"], readonly=True) as uow:
        found = (
            uow.conn()
            .execute(
                text("SELECT actor, source, payload FROM events WHERE event_type = 'Link.Added'")
            )
            .one()
        )
    assert found.actor == "user:ann"
    assert found.source == "cli"
    assert '"note":"needs it"' in found.payload


def test_list_shows_the_expected_links_a_record_lacks(
    env: dict[str, str], pair: tuple[str, str]
) -> None:
    a, b = pair
    lines = listing(env, a)
    assert lines == [f"key: {a}", "missing supporting record (rule: references@Approved)"]
    assert lnk(env, "add", "--project", "P123", a, b).exit_code == 0
    assert not any(line.startswith("missing ") for line in listing(env, a))


def test_list_of_a_record_without_links_is_just_the_key_line_and_expectations(
    env: dict[str, str],
) -> None:
    a = create(env, "Alone")
    assert listing(env, a)[0] == f"key: {a}"


# --- suggest, accept, decline ----------------------------------------------------------------


def test_suggest_then_accept(env: dict[str, str], pair: tuple[str, str]) -> None:
    a, b = pair
    result = lnk(env, "suggest", "--project", "P123", a, b, "--confidence", "0.7")
    assert result.exit_code == 0, result.output
    link_id = first_word_after(result, "suggested")
    assert result.stdout.splitlines()[1:] == ["relation references", "status suggested"]
    assert f"out  references  {b}  suggested  floating  {link_id}" in listing(env, a)

    accepted = lnk(env, "accept", "--project", "P123", link_id, "--note", "yes")
    assert accepted.exit_code == 0, accepted.output
    assert accepted.stdout.splitlines() == [f"accepted {link_id}", "version 2"]
    assert f"out  references  {b}  active  floating  {link_id}" in listing(env, a)


def test_suggest_defaults_the_confidence_and_rejects_a_value_outside_zero_to_one(
    env: dict[str, str], pair: tuple[str, str]
) -> None:
    a, b = pair
    assert lnk(env, "suggest", "--project", "P123", a, b).exit_code == 0
    bad = lnk(env, "suggest", "--project", "P123", b, a, "--confidence", "2")
    assert bad.exit_code == 2


def test_decline_hides_the_link_and_blocks_the_same_suggestion(
    env: dict[str, str], pair: tuple[str, str]
) -> None:
    a, b = pair
    link_id = first_word_after(lnk(env, "suggest", "--project", "P123", a, b), "suggested")
    declined = lnk(env, "decline", "--project", "P123", link_id, "--reason", "no")
    assert declined.exit_code == 0, declined.output
    assert declined.stdout.splitlines() == [f"declined {link_id}", "version 2"]
    assert not any(line.startswith("out ") for line in listing(env, a))
    assert f"out  references  {b}  declined  floating  {link_id}" in listing(env, a, "--all")

    again = lnk(env, "suggest", "--project", "P123", a, b)
    assert again.exit_code == 1
    assert "error: this suggestion (references) was declined before" in again.stderr


# --- verify, flag, repin, retract ------------------------------------------------------------


def test_verify_flag_and_repin_walk_the_lifecycle(
    env: dict[str, str], pair: tuple[str, str]
) -> None:
    a, b = pair
    link_id = first_word_after(lnk(env, "add", "--project", "P123", a, b), "added")

    verified = lnk(env, "verify", "--project", "P123", link_id)
    assert verified.stdout.splitlines() == [f"verified {link_id}", "version 2"]

    flagged = lnk(
        env, "flag", "--project", "P123", link_id, "--status", "stale", "--reason", "moved on"
    )
    assert flagged.exit_code == 0, flagged.output
    assert flagged.stdout.splitlines() == [f"flagged {link_id}", "version 3"]
    assert f"out  references  {b}  stale  floating  {link_id}" in listing(env, a)

    repinned = lnk(env, "repin", "--project", "P123", link_id, "--pin", "1")
    assert repinned.stdout.splitlines() == [f"repinned {link_id}", "version 4"]
    assert f"out  references  {b}  active  1  {link_id}" in listing(env, a)


def test_retract_removes_the_link_from_the_default_listing_only(
    env: dict[str, str], pair: tuple[str, str]
) -> None:
    a, b = pair
    link_id = first_word_after(lnk(env, "add", "--project", "P123", a, b), "added")
    done = lnk(env, "retract", "--project", "P123", link_id, "--reason", "duplicate")
    assert done.exit_code == 0, done.output
    assert done.stdout.splitlines() == [f"retracted {link_id}", "version 2"]
    assert not any(line.startswith("out ") for line in listing(env, a))
    assert f"out  references  {b}  retracted  floating  {link_id}" in listing(env, a, "--all")


# --- errors ----------------------------------------------------------------------------------


def test_an_unknown_record_key_is_an_error(env: dict[str, str], pair: tuple[str, str]) -> None:
    a, _ = pair
    for args in (
        ("add", "--project", "P123", a, "NOPE-1"),
        ("add", "--project", "P123", "NOPE-1", a),
        ("list", "--project", "P123", "NOPE-1"),
    ):
        result = lnk(env, *args)
        assert result.exit_code == 1, args
        assert "error: no record with key 'NOPE-1' in project 'P123'" in result.stderr


def test_a_duplicate_a_self_link_and_an_unknown_relation_are_errors(
    env: dict[str, str], pair: tuple[str, str]
) -> None:
    a, b = pair
    assert lnk(env, "add", "--project", "P123", a, b).exit_code == 0
    duplicate = lnk(env, "add", "--project", "P123", a, b)
    assert duplicate.exit_code == 1
    assert "error: a references link already exists between these records" in duplicate.stderr
    own = lnk(env, "add", "--project", "P123", a, a)
    assert own.exit_code == 1
    assert "error: a record cannot be linked to itself" in own.stderr
    bogus = lnk(env, "add", "--project", "P123", b, a, "--relation", "bogus")
    assert bogus.exit_code == 1
    assert "error: unknown relation 'bogus'" in bogus.stderr


def test_a_wrong_state_unknown_link_or_bad_flag_status_is_an_error(
    env: dict[str, str], pair: tuple[str, str]
) -> None:
    a, b = pair
    link_id = first_word_after(lnk(env, "add", "--project", "P123", a, b), "added")
    wrong = lnk(env, "accept", "--project", "P123", link_id)
    assert wrong.exit_code == 1
    assert "error: Link.Accepted is not allowed on a active link" in wrong.stderr
    missing = lnk(env, "retract", "--project", "P123", "NOPE", "--reason", "x")
    assert missing.exit_code == 1
    assert "error: no link 'NOPE' in scope 'project:P123'" in missing.stderr
    weird = lnk(env, "flag", "--project", "P123", link_id, "--status", "weird", "--reason", "x")
    assert weird.exit_code == 1
    assert "error: status: Input should be 'stale' or 'broken'" in weird.stderr


def test_the_group_lists_its_commands(env: dict[str, str]) -> None:
    result = lnk(env, "--help")
    assert result.exit_code == 0
    for name in (
        "add",
        "suggest",
        "list",
        "accept",
        "decline",
        "verify",
        "repin",
        "retract",
        "flag",
    ):
        assert name in result.stdout
