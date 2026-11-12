"""P2-I5-T07a: `tl awp iwp pack` writes the work pack of one IWP as one HTML file."""

from __future__ import annotations

import os
import re
import stat
from pathlib import Path

import pytest
from sqlalchemy import text
from test_awp_progress import Built
from test_cli_awp import Cli, seed_copy
from tl_adapters.db import as_target, open_uow
from tl_core import confidentiality as cf
from tl_core import modules as core_modules
from tl_core.modules import ConfidentialSource
from tl_mod_awp.names import DOCUMENT_TYPE

LINE = re.compile(r"^pack (\S+)  (\d+) bytes  qr (yes|no)$")


@pytest.fixture
def built(tmp_path: Path) -> Built:
    return Built(Cli(seed_copy(tmp_path), tmp_path))


def slot_files(built: Built) -> list[dict[str, object]]:
    with open_uow(as_target(str(built.cli.db)), readonly=True) as uow:
        rows = uow.conn().execute(
            text(
                "SELECT file_id, superseded_by FROM cur_files "
                "WHERE record_id = :i AND slot = 'pack' ORDER BY uploaded_at, file_id"
            ),
            {"i": built.iwp},
        )
        return [dict(r._mapping) for r in rows]


def retitle(built: Built, title: str) -> None:
    with open_uow(as_target(str(built.cli.db))) as uow:
        uow.conn().execute(
            text("UPDATE cur_core_record SET title = :t WHERE id = :i"),
            {"t": title, "i": built.iwp},
        )


def test_pack_writes_the_file_with_mode_0600_and_prints_the_two_lines(
    built: Built, tmp_path: Path
) -> None:
    out = tmp_path / "pack.html"
    result = built.cli.project("iwp", "pack", built.number, "--out", str(out))
    assert result.exit_code == 0, result.output
    lines = result.stdout.splitlines()
    match = LINE.match(lines[0])
    assert match is not None and match.group(1) == built.number
    assert int(match.group(2)) == out.stat().st_size
    assert stat.S_IMODE(os.stat(out).st_mode) == 0o600
    assert out.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")
    if match.group(3) == "no":
        assert lines[1] == "note: QR codes not drawn: the pack extra is not installed."
    assert "Traceback" not in result.output


def test_pack_replaces_a_file_that_is_already_there(built: Built, tmp_path: Path) -> None:
    out = tmp_path / "pack.html"
    out.write_text("old", encoding="utf-8")
    result = built.cli.project("iwp", "pack", built.number, "--out", str(out))
    assert result.exit_code == 0, result.output
    assert out.read_text(encoding="utf-8") != "old"
    assert stat.S_IMODE(os.stat(out).st_mode) == 0o600


def test_an_unknown_number_is_an_error_and_writes_nothing(built: Built, tmp_path: Path) -> None:
    out = tmp_path / "nope.html"
    result = built.cli.project("iwp", "pack", "NO-SUCH-IWP", "--out", str(out))
    assert result.exit_code == 1
    assert "error: no IWP NO-SUCH-IWP" in result.output
    assert not out.exists()
    assert "Traceback" not in result.output


def test_attach_stores_the_file_in_the_pack_slot_and_a_second_run_replaces_it(
    built: Built, tmp_path: Path
) -> None:
    out = tmp_path / "pack.html"
    first = built.cli.write("iwp", "pack", built.number, "--out", str(out), "--attach")
    assert first.exit_code == 0, first.output
    assert "slot pack  file " in first.stdout
    assert len(slot_files(built)) == 1
    retitle(built, "Rack, second issue")  # new content, so the file service keeps a new revision
    second = built.cli.write("iwp", "pack", built.number, "--out", str(out), "--attach")
    assert second.exit_code == 0, second.output
    files = slot_files(built)
    assert len(files) == 2
    assert [f["superseded_by"] is None for f in files] == [False, True]
    assert "Traceback" not in second.output


def test_attach_is_refused_when_no_clearance_level_reads_the_iwp(
    built: Built, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F2: no level reads the IWP, so --attach refuses before anything is stored."""
    monkeypatch.setattr("tl_cli.awp_pack._record_viewer", lambda conn, record_id, who: None)
    out = tmp_path / "refused.html"
    result = built.cli.write("iwp", "pack", built.number, "--out", str(out), "--attach")
    assert result.exit_code != 0, result.output
    assert (
        "the pack cannot be attached: no clearance level reads this IWP; write it with --out only"
        in result.output
    )
    assert slot_files(built) == []
    assert not out.exists()
    assert "Traceback" not in result.output


def test_attach_builds_the_pack_at_the_iwp_class_and_a_plain_out_at_the_session_clearance(
    built: Built, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F1: the attached file is readable by every reader of the IWP (internal), so a restricted
    drawing the session may read stays out of it; the plain --out file is the session's own."""
    docs = built.w.documents(tmp_path / "objects", "ISO-1")
    built.w.call("uma", "PinIwpDocument", iwp=built.iwp, document=docs["ISO-1"], pin="A")
    title = str(built.w.scalar("SELECT title FROM cur_core_record WHERE id = :i", i=docs["ISO-1"]))
    with open_uow(as_target(str(built.cli.db))) as uow:
        conn = uow.conn()
        conn.execute(text("CREATE TABLE s7_doc_class (id TEXT PRIMARY KEY, cls TEXT)"))
        conn.execute(
            text("INSERT INTO s7_doc_class VALUES (:i, 'restricted')"), {"i": docs["ISO-1"]}
        )
    source = ConfidentialSource(
        record_types=frozenset({DOCUMENT_TYPE}),
        table="s7_doc_class",
        id_column="id",
        class_column="cls",
    )
    real = core_modules.confidential_sources
    monkeypatch.setattr(cf, "confidential_sources", lambda: [*real(), source])
    plain = tmp_path / "plain.html"
    attached = tmp_path / "attached.html"
    first = built.cli.project("iwp", "pack", built.number, "--out", str(plain))
    second = built.cli.write("iwp", "pack", built.number, "--out", str(attached), "--attach")
    assert first.exit_code == 0 and second.exit_code == 0, (first.output, second.output)
    assert "ISO-1" in plain.read_text(encoding="utf-8")
    stored = attached.read_text(encoding="utf-8")
    assert "ISO-1" not in stored
    assert title not in stored
