"""`tl doc register|show|ls|update|supersede|void` on a temporary ledger (P1-I2-T09a)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from auth_support import bootstrap, sign_in
from doccli_support import docs_env, load_document_standards, world
from engcli_support import ordinary_env
from tl_adapters.db import DbTarget, as_target, is_postgres
from tl_cli.main import app
from typer.testing import CliRunner
from typer.testing import Result as RunResult

runner = CliRunner()


@pytest.fixture
def env(new_db: Callable[[], DbTarget], monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    return docs_env(new_db, monkeypatch)


def run(env: dict[str, str], *args: str, ok: bool = True) -> RunResult:
    result = runner.invoke(app, list(args), env=env)
    assert result.exception is None or isinstance(result.exception, SystemExit), result.exception
    assert (result.exit_code == 0) is ok, result.output
    return result


def doc(env: dict[str, str], *args: str, ok: bool = True) -> RunResult:
    return run(env, "doc", *args, ok=ok)


def register(
    env: dict[str, str], number: str = "ISO-1234", *more: str, ok: bool = True
) -> RunResult:
    return doc(
        env,
        "register",
        number,
        "--project",
        "P123",
        "--title",
        "Isometric, line 47-P-101",
        *more,
        ok=ok,
    )


def show(env: dict[str, str], number: str = "ISO-1234") -> dict[str, str]:
    """The ``name: value`` lines of ``tl doc show`` as a dict (the revision lines excluded)."""
    lines = doc(env, "show", number, "--project", "P123").stdout.splitlines()
    return dict(line.split(": ", 1) for line in lines if ": " in line)


# --- register -------------------------------------------------------------------------------------


def test_register_prints_the_document_its_state_and_scheme(env: dict[str, str]) -> None:
    result = register(
        env, "ISO-1234", "--type", "ISO", "--discipline", "PIP", "--originator", "Acme"
    )
    lines = result.stdout.splitlines()
    assert lines[0].startswith("registered ") and len(lines[0].split()[1]) == 26
    assert lines[1:] == ["document ISO-1234", "state Registered", "scheme alpha"]
    fields = show(env)
    assert fields["title"] == "Isometric, line 47-P-101"
    assert (fields["type"], fields["discipline"], fields["originator"]) == ("ISO", "PIP", "Acme")
    assert fields["current"] == "-" and fields["links"] == "0 (0 stale)"


def test_register_can_start_the_first_revision_as_a_draft(env: dict[str, str]) -> None:
    result = register(
        env, "SPC-0001", "--type", "SPC", "--first-revision", "--purpose", "First draft"
    )
    lines = result.stdout.splitlines()
    assert lines[1:] == [
        "document SPC-0001",
        "state Registered",
        "scheme numeric",
        "revision 0 Draft",
    ]
    shown = doc(env, "show", "SPC-0001", "--project", "P123").stdout.splitlines()
    assert "revision 0 Draft - - -" in shown


def test_a_number_that_breaks_the_pattern_is_refused_with_each_problem(env: dict[str, str]) -> None:
    load_document_standards(env)
    register(env, "ISO-1234", "--type", "ISO")  # fits
    result = register(env, "XXX-12", ok=False)
    assert result.stderr.splitlines()[0].startswith("error: document number 'XXX-12'")
    problems = result.stderr.splitlines()[1:]
    assert any(line.startswith("  - doctype: ") for line in problems)
    assert any(line.startswith("  - seq: ") for line in problems)
    assert "Traceback" not in result.output


def test_a_type_that_is_not_in_the_registered_list_is_refused(env: dict[str, str]) -> None:
    load_document_standards(env)
    result = register(env, "ISO-1235", "--type", "NOPE", ok=False)
    assert result.stderr.strip() == "error: document type 'NOPE' is not a value of DocumentType"


def test_the_same_number_twice_and_an_unknown_scheme_are_refused(env: dict[str, str]) -> None:
    register(env)
    again = register(env, ok=False)
    assert again.stderr.startswith("error: key 'ISO-1234' is already used")
    bad = register(env, "ISO-9", "--scheme", "roman", ok=False)
    assert bad.stderr.startswith("error: no revision scheme 'roman'")


def test_a_blank_title_is_an_error_line_not_a_trace(env: dict[str, str]) -> None:
    result = doc(env, "register", "ISO-1", "--project", "P123", "--title", "  ", ok=False)
    assert result.stderr.startswith("error: title: ")
    assert "Traceback" not in result.output


# --- show and ls ----------------------------------------------------------------------------------


def test_show_prints_the_current_revision_every_revision_and_the_links(
    env: dict[str, str], tmp_path: Path
) -> None:
    w = world(env, tmp_path)
    w.issued_document("ISO-1234", "IFR")
    w.link(w.tag(), "ISO-1234", "A")
    issued_on = w.revision("ISO-1234", "A").issued_on or ""
    lines = doc(env, "show", "ISO-1234", "--project", "P123").stdout.splitlines()
    assert lines[1:3] == ["number: ISO-1234", "title: Isometric, line 47-P-101"]
    assert "state: Issued" in lines and f"current: A IFR review {issued_on}" in lines
    assert "superseded_by: -" in lines and "scheme: alpha" in lines
    assert lines[-2] == f"revision A Issued IFR review {issued_on} current"
    assert lines[-1] == "links: 1 (0 stale)"
    w.create_revision("ISO-1234")
    w.attach("ISO-1234", "B", data=b"%PDF-1.7 b", name="b.pdf")
    w.issue("ISO-1234", "B", "IFC")
    lines = doc(env, "show", "ISO-1234", "--project", "P123").stdout.splitlines()
    assert lines[-3].startswith("revision A Issued IFR review ") and lines[-3].endswith(" current")
    assert lines[-2].startswith("revision B Issued IFC construction ") and lines[-2].endswith(
        " current"
    )
    assert lines[-1] == "links: 1 (1 stale)"
    assert any(line.startswith("current: B IFC construction ") for line in lines)


def test_show_of_an_unknown_document_is_an_error_line(env: dict[str, str]) -> None:
    result = doc(env, "show", "NOPE-1", "--project", "P123", ok=False)
    assert result.stderr.strip() == "error: no document 'NOPE-1' in project 'P123'"
    other = doc(env, "show", "NOPE-1", "--project", "P999", ok=False)
    assert "project 'P999'" in other.stderr


def test_ls_lists_by_number_and_filters(env: dict[str, str], tmp_path: Path) -> None:
    w = world(env, tmp_path)
    w.issued_document("ISO-1234", "IFC")
    register(env, "SPC-0001", "--type", "SPC", "--discipline", "MEC")
    register(env, "PID-0001", "--type", "PID")
    rows = doc(env, "ls", "--project", "P123").stdout.splitlines()
    assert [r.split("  ")[0] for r in rows] == ["ISO-1234", "PID-0001", "SPC-0001"]
    assert rows[0].split("  ")[1:3] == ["Issued", "A(IFC)"]
    assert rows[2].split("  ")[1:5] == ["Registered", "-", "SPC", "MEC"]
    assert rows[0].endswith("Isometric, line 47-P-101")
    only = doc(env, "ls", "--project", "P123", "--type", "SPC").stdout.splitlines()
    assert [r.split("  ")[0] for r in only] == ["SPC-0001"]
    issued = doc(env, "ls", "--project", "P123", "--state", "Issued").stdout.splitlines()
    assert [r.split("  ")[0] for r in issued] == ["ISO-1234"]
    assert doc(env, "ls", "--project", "P999").stdout == ""


# --- update, supersede, void ----------------------------------------------------------------------


def test_update_changes_fields_and_an_empty_value_clears_one(env: dict[str, str]) -> None:
    register(env, "ISO-1234", "--originator", "Acme", "--discipline", "MEC")
    result = doc(
        env,
        "update",
        "ISO-1234",
        "--project",
        "P123",
        "--title",
        "New title",
        "--discipline",
        "PIP",
        "--originator",
        "",
        "--reason",
        "re-assigned",
    )
    assert result.stdout.strip() == "updated ISO-1234"
    fields = show(env)
    assert fields["title"] == "New title" and fields["discipline"] == "PIP"
    assert fields["originator"] == "-"


def test_update_needs_a_field_and_a_difference(env: dict[str, str]) -> None:
    register(env)
    nothing = doc(env, "update", "ISO-1234", "--project", "P123", ok=False)
    assert nothing.stderr.startswith("error: give at least one field")
    same = doc(
        env,
        "update",
        "ISO-1234",
        "--project",
        "P123",
        "--title",
        "Isometric, line 47-P-101",
        ok=False,
    )
    assert "differs from the request" in same.stderr


def test_supersede_is_for_a_controller_and_needs_an_issued_replacement(
    env: dict[str, str], tmp_path: Path
) -> None:
    register(env, "ISO-1000")
    register(env, "ISO-2000")
    args = ("supersede", "ISO-1000", "--by", "ISO-2000", "--project", "P123", "--reason", "x")
    if not is_postgres(as_target(env["TL_DB"])):
        assert bootstrap(env).exit_code == 0
        sign_in(env)
        amy = ordinary_env(env, tmp_path)
        refused = doc(amy, *args, ok=False)
        assert refused.stderr.startswith("error: ") and "admin" in refused.stderr
        assert show(env, "ISO-1000")["state"] == "Registered"
    no_issue = doc(env, *args, ok=False)  # the replacement has no issued revision yet
    assert "no issued revision yet" in no_issue.stderr, no_issue.stderr
    made = world(env, tmp_path)
    made.create_revision("ISO-2000")
    made.attach("ISO-2000", "A")
    made.issue("ISO-2000", "A", "IFR")
    result = doc(
        env,
        "supersede",
        "ISO-1000",
        "--by",
        "ISO-2000",
        "--project",
        "P123",
        "--reason",
        "re-drawn",
    )
    assert result.stdout.strip() == "superseded ISO-1000 by ISO-2000"
    fields = show(env, "ISO-1000")
    assert fields["state"] == "Superseded" and fields["superseded_by"] == "ISO-2000"
    again = doc(
        env,
        "supersede",
        "ISO-1000",
        "--by",
        "ISO-2000",
        "--project",
        "P123",
        "--reason",
        "x",
        ok=False,
    )
    assert "Superseded and takes no more changes" in again.stderr
    ghost = doc(
        env,
        "supersede",
        "ISO-2000",
        "--by",
        "NOPE-1",
        "--project",
        "P123",
        "--reason",
        "x",
        ok=False,
    )
    assert ghost.stderr.strip() == "error: no document 'NOPE-1' in project 'P123'"


def test_void_is_for_a_controller_and_voids_the_document(
    env: dict[str, str], tmp_path: Path
) -> None:
    register(env, "ISO-1234")
    if not is_postgres(as_target(env["TL_DB"])):
        assert bootstrap(env).exit_code == 0
        sign_in(env)
        amy = ordinary_env(env, tmp_path)
        refused = doc(
            amy, "void", "ISO-1234", "--project", "P123", "--reason", "in error", ok=False
        )
        assert refused.stderr.startswith("error: ") and "admin" in refused.stderr
        assert show(env)["state"] == "Registered"
    result = doc(env, "void", "ISO-1234", "--project", "P123", "--reason", "registered in error")
    assert result.stdout.strip() == "voided ISO-1234"
    assert show(env)["state"] == "Void"
    assert doc(env, "ls", "--project", "P123").stdout == ""
    assert doc(env, "ls", "--project", "P123", "--all").stdout.startswith("ISO-1234  Void")
    again = doc(env, "void", "ISO-1234", "--project", "P123", "--reason", "again", ok=False)
    assert "takes no more changes" in again.stderr


def test_the_confidentiality_help_says_the_class_is_enforced(env: dict[str, str]) -> None:
    text = " ".join(doc(env, "confidentiality", "--help").stdout.split())
    assert "is enforced" in text and "ADR-0016" in text


def test_confidentiality_is_for_a_controller_and_keeps_the_reason(
    env: dict[str, str], tmp_path: Path
) -> None:
    register(env, "ISO-1234")
    args = ("confidentiality", "ISO-1234", "--project", "P123", "--class", "restricted")
    args += ("--reason", "client request")
    if not is_postgres(as_target(env["TL_DB"])):
        assert bootstrap(env).exit_code == 0
        sign_in(env)
        refused = doc(ordinary_env(env, tmp_path), *args, ok=False)
        assert refused.stderr.startswith("error: ") and "admin" in refused.stderr
        assert show(env)["confidentiality"] == "-"
    done = doc(env, *args)
    assert done.stdout.strip() == "confidentiality of ISO-1234: - -> restricted"
    assert show(env)["confidentiality"] == "restricted"
    same = doc(env, *args, ok=False)
    assert "already has that confidentiality" in same.stderr
    cleared = doc(
        env, "confidentiality", "ISO-1234", "--project", "P123", "--clear", "--reason", "lifted"
    )
    assert cleared.stdout.strip() == "confidentiality of ISO-1234: restricted -> -"
    both = doc(env, "confidentiality", "ISO-1234", "--project", "P123", "--reason", "x", ok=False)
    assert both.stderr.strip() == "error: give the new class with --class, or --clear to remove it"
