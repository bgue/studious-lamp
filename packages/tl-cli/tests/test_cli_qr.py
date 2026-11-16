"""`tl qr` (P2-QR-T07): the six verbs, the label file, the register rows, resolve from stdin.

The ledger comes from the QR module's ``qr_world`` (people, a fake scan-card provider, a
``quality.PunchItem`` record). The provider is injected in place of the entry points and the public
address is the one the module's tests stand in for (``service.value_of``). Reads run signed in as
the person they name; writes run with ``--actor`` on the dev ledger file.
"""

from __future__ import annotations

import csv
import io
import json
import re
import sys
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import click
import pytest
import tl_mod_qr.resolve as resolve_module
import typer.main
from auth_support import sign_in
from tl_adapters.db import as_target, create_schema
from tl_cli.derive_support import cell
from tl_cli.main import app
from tl_core.qr import registry
from tl_core.settings import resolver
from tl_core.util import utcnow
from tl_mod_qr import service
from tl_mod_qr.codes import new_code
from tl_mod_qr.labels import NO_QR_NOTE
from typer.testing import CliRunner, Result

QR_TESTS = Path(__file__).resolve().parents[2] / "tl-modules" / "qr" / "tests"
sys.path.insert(0, str(QR_TESTS))

from qr_world import (  # noqa: E402
    CARDED,
    PASSWORD,
    SECRET,
    FakeProvider,
    World,
    providers_of,
)

PROJECT = "P123"
KEY = "P123-PUN-0001"
SIX = ("label", "ls", "revoke", "rotate", "resolve", "export")
MISS = "no such code\n"
GROUPED = re.compile(r'<div class="code">([A-Z0-9-]{19})</div>')
CODE16 = re.compile(r"[A-Z0-9]{16}")


class Later(datetime):
    """``datetime`` whose ``now`` is far past every expiry the tests set."""

    @classmethod
    def now(cls, tz: Any = None) -> datetime:
        return datetime(2099, 1, 1, tzinfo=UTC)


class Qr:
    """``tl --db DB qr ...`` through the CliRunner, with a session file of its own."""

    def __init__(self, db: Path, tmp_path: Path, world: World) -> None:
        self.db = db
        self.tmp = tmp_path
        self.world = world
        self.env = {"TL_ENV": "dev", "TL_SESSION_FILE": str(tmp_path / "session.json")}

    def run(self, *argv: str, env: dict[str, str] | None = None, stdin: str = "") -> Result:
        result = CliRunner().invoke(
            app, ["--db", str(self.db), "qr", *argv], env=env or self.env, input=stdin
        )
        assert result.exception is None or isinstance(result.exception, SystemExit), result.output
        assert "Traceback" not in result.output
        return result

    def as_person(self, name: str) -> dict[str, str]:
        env = {
            "TL_ENV": "dev",
            "TL_DB": str(self.db),
            "TL_SESSION_FILE": str(self.tmp / f"session-{name}.json"),
        }
        sign_in(env, name, PASSWORD)
        return env

    def label(self, out: Path, *more: str, who: str = "uma") -> Result:
        argv = ["label", KEY, "--project", PROJECT, "--output", str(out), *more]
        return self.run(*argv, "--actor", f"user:{who}")

    def ls(self, who: str = "uma") -> list[str]:
        result = self.run(
            "ls", KEY, "--project", PROJECT, "--actor", f"user:{who}", env=self.as_person(who)
        )
        assert result.exit_code == 0, result.output
        return result.output.splitlines()

    def export(self, fmt: str, who: str = "uma") -> Result:
        return self.run(
            "export", KEY, "--project", PROJECT, "--format", fmt, "--actor", f"user:{who}",
            env=self.as_person(who),
        )  # fmt: skip

    def resolve(self, code: str, who: str = "uma") -> Result:
        return self.run(
            "resolve", "--project", PROJECT, "--actor", f"user:{who}",
            env=self.as_person(who), stdin=code + "\n",
        )  # fmt: skip


def grouped_code(path: Path) -> str:
    """The code as the label file prints it, grouped; the only place a code is printed."""
    match = GROUPED.search(path.read_text(encoding="utf-8"))
    assert match is not None, "no grouped code in the label file"
    return match.group(1)


def plain(grouped: str) -> str:
    return grouped.replace("-", "")


def register_of(result: Result) -> str:
    """The register id a verb prints: the second word of its one line."""
    assert result.exit_code == 0, result.output
    return result.output.split()[1]


@pytest.fixture
def qr(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Qr]:
    path = tmp_path / "tl.db"
    target = as_target(str(path))
    create_schema(target)
    made = World(target)
    made.people()
    made.person("nobody", ("user",))  # no view word is granted in the test (see five_misses)
    made.record(CARDED, key=KEY)
    real = resolver.value_of

    def value_of(conn: Any, key: str, **kwargs: Any) -> Any:
        return made.public if key == service.BASE_URL else real(conn, key, **kwargs)

    fake = FakeProvider()
    monkeypatch.setattr(service, "value_of", value_of)
    monkeypatch.setattr(
        registry, "load_scan_cards", lambda *a, **k: providers_of(fake, FakeProvider(SECRET))
    )
    monkeypatch.setenv("TL_WEB", "on")
    yield Qr(path, tmp_path, made)


def labelled(qr: Qr, name: str = "label.html") -> tuple[Path, str]:
    """Set the public address, label the punch record once; the file and the register id."""
    qr.world.base()
    out = qr.tmp / name
    return out, register_of(qr.label(out))


# --- 1. label -------------------------------------------------------------------------------------


def test_label_without_the_public_address_is_refused_and_writes_nothing(qr: Qr) -> None:
    out = qr.tmp / "label.html"
    result = qr.label(out)
    assert result.exit_code == 1
    assert "error: set api.public_base_url first" in result.output
    assert not out.exists()
    assert qr.ls() == ["scan codes: 0"]


def test_label_writes_an_svg_or_the_note_and_prints_no_code(qr: Qr) -> None:
    qr.world.base()
    out = qr.tmp / "label.html"
    # The world titles every record with its key, so the default text would print the key; an
    # explicit text keeps the key out of the printed page (see the Decision in the report).
    result = qr.label(out, "--label", "Pump room")
    assert result.exit_code == 0, result.output
    page = out.read_text(encoding="utf-8")
    assert "<svg" in page or NO_QR_NOTE in page
    code = plain(grouped_code(out))
    assert code not in result.output
    assert grouped_code(out) not in result.output
    assert CODE16.search(result.output.replace(result.output.split()[1], "")) is None
    assert str(out) in result.output
    assert "http" not in result.output
    # Outside the grouped print the file holds no key, id, project code or 16-character code.
    register = result.output.split()[1]
    record = qr.world.rows("SELECT id FROM cur_core_record WHERE key = :key", key=KEY)
    rest = GROUPED.sub("", page)
    for leaked in (KEY, PROJECT, register, str(record[0]["id"]), code):
        assert leaked not in rest, leaked
    assert CODE16.search(rest) is None


def test_label_keeps_an_existing_file_unless_forced(qr: Qr) -> None:
    out, _ = labelled(qr)
    before = out.read_text(encoding="utf-8")
    result = qr.label(out)
    assert result.exit_code == 1, result.output
    assert out.read_text(encoding="utf-8") == before
    assert qr.ls()[0] == "scan codes: 1"  # the refusal came before anything was issued


def test_label_size_card_gives_the_renderer_refusal_and_issues_nothing(qr: Qr) -> None:
    qr.world.base()
    out = qr.tmp / "card.html"
    result = qr.label(out, "--size", "card")
    assert result.exit_code == 1
    assert "label size card is not available yet" in result.output
    assert not out.exists()
    assert qr.ls() == ["scan codes: 0"]


# --- 2. ls and export -----------------------------------------------------------------------------


def test_ls_shows_the_row_and_no_code(qr: Qr) -> None:
    out, register = labelled(qr)
    lines = qr.ls()
    assert lines[0] == "scan codes: 1"
    assert lines[1].split()[0] == register
    assert plain(grouped_code(out)) not in "\n".join(lines)


def ls_line(row: Mapping[str, Any]) -> str:
    """The `ls` line a register row prints: the same cells, in the same order, as `tl qr ls`."""
    return (
        f"{row['id']}  {cell(row['label_text'], 40)}  {row['size']}  {row['state']}  "
        f"{cell(row['issued_by'], 120)}  {cell(row['issued_at'])}  {cell(row['expires_on'])}"
    )


def test_export_csv_and_jsonl_rows_equal_the_ls_rows(qr: Qr) -> None:
    out, register = labelled(qr)
    shown = qr.ls()[1]
    csv_out = qr.export("csv")
    jsonl_out = qr.export("jsonl")
    assert csv_out.exit_code == 0, csv_out.output
    assert jsonl_out.exit_code == 0, jsonl_out.output
    rows = list(csv.DictReader(io.StringIO(csv_out.output)))
    lines = [json.loads(line) for line in jsonl_out.output.splitlines()]
    assert len(rows) == len(lines) == 1
    # Every field of the row is the cell `ls` prints (label, issued by, issued at, expires too).
    assert shown == ls_line(rows[0]) == ls_line(lines[0])
    assert rows[0]["id"] == register
    assert plain(grouped_code(out)) not in csv_out.output + jsonl_out.output


def test_export_with_a_bad_format_is_a_usage_error(qr: Qr) -> None:
    assert qr.export("xml").exit_code == 2


# --- 3. rotate and revoke -------------------------------------------------------------------------


def test_rotate_replaces_the_code_and_revoke_ends_the_new_one(qr: Qr) -> None:
    out, old_id = labelled(qr)
    old_code = plain(grouped_code(out))
    new_out = qr.tmp / "new.html"
    rotated = qr.run("rotate", old_id, "--project", PROJECT, "--reason", "lost",
                     "--output", str(new_out), "--actor", "user:uma")  # fmt: skip
    new_id = register_of(rotated)
    assert new_id != old_id
    new_code = plain(grouped_code(new_out))
    assert qr.resolve(old_code).output == MISS
    assert qr.resolve(new_code).exit_code == 0
    assert qr.ls()[0] == "scan codes: 2"

    revoked = qr.run("revoke", new_id, "--project", PROJECT, "--reason", "site",
                     "--actor", "user:ada")  # fmt: skip
    assert revoked.exit_code == 0, revoked.output
    assert qr.resolve(new_code).output == MISS


# --- 4. resolve -----------------------------------------------------------------------------------


def test_resolve_from_stdin_prints_the_banner_and_the_card_lines(qr: Qr) -> None:
    out, _ = labelled(qr)
    result = qr.resolve(plain(grouped_code(out)))
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert lines[0] == "OK"
    assert "Fake card" in lines
    assert lines[-1].startswith("as of ")


def test_five_misses_print_the_same_text_and_exit_one(
    qr: Qr, monkeypatch: pytest.MonkeyPatch
) -> None:
    out, _ = labelled(qr)
    live = plain(grouped_code(out))
    real_held = resolve_module.view_word_held

    def held(conn: Any, actor: str, word: str, scope: str) -> bool:
        # Every role the test ledger grants holds the word, so "no view word" is simulated here.
        return actor != "user:nobody" and real_held(conn, actor, word, scope)

    monkeypatch.setattr(resolve_module, "view_word_held", held)
    revoked_out = qr.tmp / "revoked.html"
    revoked_id = register_of(qr.label(revoked_out, "--label", "R"))
    revoked = plain(grouped_code(revoked_out))
    qr.run("revoke", revoked_id, "--project", PROJECT, "--reason", "x", "--actor", "user:ada")
    soon_out = qr.tmp / "soon.html"
    soon = (utcnow().date() + timedelta(days=1)).isoformat()
    register_of(qr.label(soon_out, "--expires", soon, "--label", "E"))
    expired = plain(grouped_code(soon_out))
    secret = qr.world.hidden_record()
    hidden = qr.world.serve(service.issue, "dora", "IssueScanCode", target_id=secret).code

    monkeypatch.setattr(resolve_module, "datetime", Later)
    cases = {
        "unknown": (new_code(), "uma"),
        "revoked": (revoked, "uma"),
        "expired": (expired, "uma"),
        "hidden": (hidden, "uma"),
        "no view word": (live, "nobody"),
    }
    for name, (code, who) in cases.items():
        result = qr.resolve(code, who=who)
        assert result.exit_code == 1, name
        assert result.output == MISS, name


# --- 5. a reader who cannot see the record --------------------------------------------------------


def test_a_reader_who_cannot_see_the_record_gets_the_unknown_key_text(qr: Qr) -> None:
    qr.world.base()
    secret = qr.world.hidden_record()
    rows = qr.world.rows("SELECT key FROM cur_core_record WHERE id = :id", id=secret)
    hidden_key = str(rows[0]["key"])
    out = qr.tmp / "hidden.html"
    env = qr.as_person("vera")
    for argv in (
        ["label", hidden_key, "--project", PROJECT, "--output", str(out)],
        ["ls", hidden_key, "--project", PROJECT],
        ["export", hidden_key, "--project", PROJECT, "--format", "csv"],
    ):
        result = qr.run(*argv, "--actor", "user:vera", env=env)
        assert result.exit_code == 1, result.output
        assert result.output.strip() == f"error: no record {hidden_key}"
        absent = qr.run(*argv[:1], "P123-NOPE-0001", *argv[2:], "--actor", "user:vera", env=env)
        assert absent.output.strip() == "error: no record P123-NOPE-0001"
    assert not out.exists()


# --- 6. the placeholder is gone -------------------------------------------------------------------


def test_the_group_lists_the_six_verbs_and_no_placeholder() -> None:
    root = cast(click.Group, typer.main.get_command(app))
    group = cast(click.Group, root.commands["qr"])
    assert sorted(group.commands) == sorted(SIX)
