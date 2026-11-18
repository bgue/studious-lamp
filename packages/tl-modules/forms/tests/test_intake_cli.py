"""``tl intake`` (V3-F4; I01, I04): issue prints the code once and stores only its hash, revoke, the
queue, accept as the record the template proposes, reject, purge. Run on a dev ledger file as
``user:ada`` (the forms controller); the walk of five readers is ``tests/confidentiality``."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from forms_world import SCOPE, World
from sqlalchemy import text
from tl_adapters.db import open_uow
from tl_cli.main import app
from tl_core.qr.codes import code_hash, normalise_code
from typer.testing import CliRunner, Result

PROJECT = SCOPE.removeprefix("project:")
RECEIVED = datetime(2026, 12, 1, 9, 0, tzinfo=UTC)


class Cli:
    def __init__(self, world: World, tmp: Path) -> None:
        self.world = world
        self.env = {"TL_ENV": "dev", "TL_SESSION_FILE": str(tmp / "session.json")}

    def run(self, *argv: str, who: str = "ada") -> Result:
        result = CliRunner().invoke(
            app,
            ["--db", str(self.world.db), *argv, "--actor", f"user:{who}"],
            env=self.env,
        )
        assert "Traceback" not in result.output
        return result

    def issue(self, template: str, who: str = "ada", **more: str) -> Result:
        opts = {
            "--template": template,
            "--heading": "Scaffold request",
            "--controller-role": "controller",
            "--expires-on": self.world.days_from_now(10),
            **more,
        }
        flat = [x for kv in opts.items() for x in kv]
        return self.run("intake", "code", "issue", "--project", PROJECT, *flat, who=who)


@pytest.fixture
def cli(world: World, tmp_path: Path) -> Cli:
    return Cli(world, tmp_path)


def printed_code(out: str) -> str:
    line = next(x for x in out.splitlines() if x.startswith("code "))
    found = normalise_code(line.removeprefix("code "))
    assert found is not None
    return found


def test_issue_prints_the_code_once_and_stores_only_its_hash(cli: Cli, world: World) -> None:
    template = world.intake_template()
    key = world.rows("SELECT key FROM cur_core_record WHERE id = :i", i=template)[0]["key"]
    for ref in (template, key):  # by id or by key
        done = cli.issue(ref)
        assert done.exit_code == 0, done.output
        lines = done.stdout.splitlines()
        assert len(lines) == 2 and lines[0].startswith("issued ") and lines[1].startswith("code ")
        assert "shown once" in done.stderr
        code = printed_code(done.stdout)
        digest = code_hash(code)
        assert world.scalar(
            "SELECT count(*) FROM cur_forms_intake_code WHERE code_hash = :h", h=digest
        )
        everything = json.dumps(
            [
                world.rows("SELECT payload FROM events"),
                world.rows("SELECT * FROM cur_forms_intake_code"),
                world.rows("SELECT * FROM cur_core_record"),
            ],
            default=str,
        )
        assert code not in everything and lines[1].removeprefix("code ") not in everything
        assert done.stderr.count(code) == 0
        assert digest not in done.output  # the hash is no more shown than the code is kept
    assert printed_code(cli.issue(template).stdout) != code


def test_there_is_no_code_option_and_a_missing_option_is_a_usage_error(
    cli: Cli, world: World
) -> None:
    template = world.intake_template()
    before = world.count()
    bad = cli.run(
        "intake", "code", "issue", "--project", PROJECT, "--template", template, "--code", "ABCD"
    )
    assert bad.exit_code == 2
    lacking = cli.run("intake", "code", "issue", "--project", PROJECT, "--template", template)
    assert lacking.exit_code == 2 and world.count() == before


def test_a_refusal_prints_a_fixed_text_and_no_code(cli: Cli, world: World) -> None:
    draft = world.intake_template(publish=False)
    plain = world.template()
    open_template = world.intake_template()
    for ref, who in ((draft, "ada"), (plain, "ada"), ("TPL-9999", "ada"), (open_template, "uma")):
        out = cli.issue(ref, who=who)
        assert out.exit_code == 1 and "code " not in out.output.replace("error: ", "")
    past = cli.issue(world.intake_template(), **{"--expires-on": "2020-01-01"})
    assert past.exit_code == 1 and "expiry" in past.output
    junk = cli.issue(world.intake_template(), **{"--expires-on": "soon"})
    assert junk.exit_code == 2


def test_revoke_and_the_code_list_show_no_secret(cli: Cli, world: World) -> None:
    template = world.intake_template()
    made = cli.issue(template)
    code = printed_code(made.stdout)
    code_id = made.stdout.split()[1]
    listed = cli.run("intake", "code", "ls", "--project", PROJECT)
    assert listed.exit_code == 0 and listed.stdout.splitlines()[0] == "intake codes: 1"
    assert code_id in listed.stdout and "Active" in listed.stdout and "pending 0" in listed.stdout
    assert code not in listed.stdout and code_hash(code) not in listed.stdout
    revoked = cli.run(
        "intake", "code", "revoke", code_id, "--project", PROJECT, "--reason", "poster taken down"
    )
    assert revoked.exit_code == 0 and revoked.stdout.strip() == f"revoked {code_id}"
    again = cli.run("intake", "code", "revoke", code_id, "--project", PROJECT, "--reason", "x")
    assert again.exit_code == 1
    nobody = cli.run("intake", "code", "revoke", "01J0", "--project", PROJECT, "--reason", "x")
    other = cli.run("intake", "code", "revoke", code_id, "--project", "P999", "--reason", "x")
    assert nobody.output.split(":")[-1] == other.output.split(":")[-1]
    only = cli.run("intake", "code", "ls", "--project", PROJECT, "--state", "Revoked")
    assert only.stdout.splitlines()[0] == "intake codes: 1" and "Revoked" in only.stdout


def test_the_queue_accept_reject_and_purge(cli: Cli, world: World, tmp_path: Path) -> None:
    template = world.intake_template()
    general = world.template()
    code = world.stage_code(template)
    take, drop = world.stage_item(code), world.stage_item(code)
    listed = cli.run("intake", "ls", "--project", PROJECT)
    assert listed.exit_code == 0 and listed.stdout.splitlines()[0] == "intake items: 2"
    shown = cli.run("intake", "show", take, "--project", PROJECT)
    assert shown.exit_code == 0 and "Pending" in shown.stdout and "Need a ladder" in shown.stdout
    args = tmp_path / "args.json"
    args.write_text(
        json.dumps({"template_id": general, "answers": [{"q": "topic", "value": "Ladders"}]})
    )
    done = cli.run(
        "intake",
        "accept",
        take,
        "--project",
        PROJECT,
        "--as",
        "SubmitForm",
        "--args-file",
        str(args),
    )
    assert done.exit_code == 0, done.output
    made = cli.run("form", "ls", "--submissions", "--project", PROJECT)
    assert made.stdout.splitlines()[0] == "form submissions: 1"  # the record the item proposed
    after = cli.run("intake", "show", take, "--project", PROJECT)
    assert "accepted as SubmitForm" in after.stdout and "Need a ladder" not in after.stdout
    assert world.body_rows(take) == 0
    twice = cli.run(
        "intake",
        "accept",
        take,
        "--project",
        PROJECT,
        "--as",
        "SubmitForm",
        "--args-file",
        str(args),
    )
    assert twice.exit_code == 1
    refused = cli.run("intake", "reject", drop, "--project", PROJECT, "--reason", "spam", who="uma")
    assert refused.exit_code == 1 and "forbidden" in refused.output
    rejected = cli.run("intake", "reject", drop, "--project", PROJECT, "--reason", "spam")
    assert rejected.exit_code == 0 and world.body_rows(drop) == 1
    assert (
        cli.run("intake", "reject", drop, "--project", PROJECT, "--reason", "nope").exit_code == 2
    )
    states = cli.run("intake", "ls", "--project", PROJECT, "--state", "Rejected")
    assert states.stdout.splitlines()[0] == "intake items: 1" and "spam" in states.stdout
    assert cli.run("intake", "purge", "--project", PROJECT).stdout.strip() == "purged 0"
    with_old = world.rows("SELECT item_id FROM forms_intake_body")
    assert [r["item_id"] for r in with_old] == [drop]
    stale = RECEIVED - timedelta(days=60)
    with open_uow(world.db) as uow:
        uow.conn().execute(
            text("UPDATE forms_intake_body SET received_at = :r"), {"r": stale.isoformat()}
        )
    gone = cli.run("intake", "purge", "--project", PROJECT)
    assert gone.stdout.strip() == "purged 1" and world.body_rows(drop) == 0
    assert cli.run("intake", "purge", "--project", PROJECT).stdout.strip() == "purged 0"
    bad = tmp_path / "bad.json"
    bad.write_text("[1]")
    junk = cli.run(
        "intake",
        "accept",
        drop,
        "--project",
        PROJECT,
        "--as",
        "SubmitForm",
        "--args-file",
        str(bad),
    )
    assert junk.exit_code == 2


def test_help_lists_the_group_and_its_verbs(cli: Cli) -> None:
    top = CliRunner().invoke(app, ["intake", "--help"], env=cli.env).stdout
    for word in ("code", "ls", "show", "accept", "reject", "purge"):
        assert word in top
    sub = CliRunner().invoke(app, ["intake", "code", "--help"], env=cli.env).stdout
    for word in ("issue", "revoke", "ls"):
        assert word in sub


def test_show_strips_control_characters_from_the_senders_text(cli: Cli, world: World) -> None:
    from forms_world import answer

    body = json.dumps({"answers": [answer("topic\x1b[2J", "\x1b[31mred\x1b[0m ladder")]})
    item = world.stage_item(world.stage_code(world.intake_template()), body)
    shown = cli.run("intake", "show", item, "--project", PROJECT)
    assert shown.exit_code == 0 and "\x1b" not in shown.stdout
    assert "ladder" in shown.stdout
