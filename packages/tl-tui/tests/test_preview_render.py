"""render_first_page: bounded, off the process, cached; hostile files (P1-UX2-S4)."""

from __future__ import annotations

import hashlib
import json
import os
import struct
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from doc_support import pdf_bytes
from tl_tui.preview import _worker as worker
from tl_tui.preview import cache, render
from tl_tui.preview.render import MAX_BYTES, render_first_page


class Children:
    """Counts the child processes ``render_first_page`` starts."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.started: list[list[str]] = []
        real = subprocess.Popen

        def spy(argv: list[str], *args: object, **kwargs: object) -> subprocess.Popen[bytes]:
            self.started.append(list(argv))
            return real(argv, *args, **kwargs)  # type: ignore[call-overload,no-any-return]

        monkeypatch.setattr(subprocess, "Popen", spy)


@pytest.fixture
def children(monkeypatch: pytest.MonkeyPatch) -> Children:
    return Children(monkeypatch)


def stored(tmp_path: Path, data: bytes, name: str = "doc.pdf") -> tuple[Path, str]:
    path = tmp_path / name
    path.write_bytes(data)
    return path, hashlib.sha256(data).hexdigest()


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    return struct.unpack(">II", data[16:24])  # type: ignore[no-any-return]


def big_page_pdf(side: int) -> bytes:
    """A one-page PDF whose MediaBox is ``side`` x ``side`` points."""
    body = b"%PDF-1.4\n"
    offsets = []
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {side} {side}] >>".encode(),
    ]
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(body))
        body += f"{number} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(body)
    body += b"xref\n0 4\n0000000000 65535 f \n"
    for offset in offsets:
        body += f"{offset:010d} 00000 n \n".encode()
    body += f"trailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return body


def test_a_real_pdf_renders_page_one_into_the_cache(tmp_path: Path, children: Children) -> None:
    path, sha = stored(tmp_path, pdf_bytes(pages=3))
    done = render_first_page(path, sha, root=tmp_path / "cache")
    assert done.state == "ok" and done.pages == 3
    assert done.png == tmp_path / "cache" / f"{sha}.png"
    assert done.png is not None and png_size(done.png) == (
        600,
        800,
    )  # a small page is drawn at twice its size
    assert len(children.started) == 1
    assert [p.name for p in (tmp_path / "cache").iterdir()] == [f"{sha}.png"]


def test_the_second_call_is_a_cache_hit_without_a_child(tmp_path: Path, children: Children) -> None:
    path, sha = stored(tmp_path, pdf_bytes(pages=2))
    first = render_first_page(path, sha, root=tmp_path / "cache")
    path.unlink()  # the hit does not need the file
    again = render_first_page(path, sha, root=tmp_path / "cache")
    assert again.state == "ok" and again.pages == 2 and again.png == first.png
    assert len(children.started) == 1


def test_a_file_that_is_not_a_pdf_is_refused_without_a_child(
    tmp_path: Path, children: Children
) -> None:
    path, sha = stored(tmp_path, b"MZ\x90\x00 this is a program, not a PDF" * 10)
    assert render_first_page(path, sha, root=tmp_path / "cache").state == "not_pdf"
    assert children.started == []


def test_a_file_over_the_cap_is_refused_without_a_child(tmp_path: Path, children: Children) -> None:
    path = tmp_path / "huge.pdf"
    with open(path, "wb") as handle:
        handle.write(b"%PDF-1.4\n")
        handle.truncate(60 * 1024 * 1024)
    done = render_first_page(path, "b" * 64, root=tmp_path / "cache")
    assert done.state == "too_big" and done.png is None
    assert children.started == [] and MAX_BYTES == 50 * 1024 * 1024


def test_a_file_just_under_the_cap_is_not_refused_for_its_size(
    tmp_path: Path, children: Children
) -> None:
    path = tmp_path / "edge.pdf"
    with open(path, "wb") as handle:
        handle.write(b"%PDF-1.4\n")
        handle.truncate(MAX_BYTES)
    done = render_first_page(path, "c" * 64, root=tmp_path / "cache")
    assert done.state == "error" and len(children.started) == 1  # the child tried and failed


def test_a_huge_media_box_comes_out_within_1200_pixels(tmp_path: Path) -> None:
    path, sha = stored(tmp_path, big_page_pdf(14400))
    done = render_first_page(path, sha, root=tmp_path / "cache")
    assert done.state == "ok" and done.png is not None
    width, height = png_size(done.png)
    assert max(width, height) <= 1200 and width * height <= 1_500_000


def test_a_worker_that_sleeps_is_killed_at_the_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pidfile = tmp_path / "pid"
    script = tmp_path / "sleeper.py"
    script.write_text(
        textwrap.dedent(
            f"""
            import os, time
            open({str(pidfile)!r}, "w").write(str(os.getpid()))
            time.sleep(60)
            """
        )
    )
    monkeypatch.setattr(render, "WORKER_COMMAND", (sys.executable, "-I", str(script)))
    path, sha = stored(tmp_path, pdf_bytes())
    done = render_first_page(path, sha, timeout_s=1.0, root=tmp_path / "cache")
    assert done.state == "timeout" and done.png is None
    pid = int(pidfile.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)  # the child is gone, not left running


def test_cancelling_kills_the_child_and_says_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = tmp_path / "sleeper.py"
    script.write_text("import time\ntime.sleep(60)\n")
    monkeypatch.setattr(render, "WORKER_COMMAND", (sys.executable, "-I", str(script)))
    path, sha = stored(tmp_path, pdf_bytes())
    done = render_first_page(path, sha, root=tmp_path / "c", cancelled=lambda: True)
    assert done.state == "error"


def test_a_truncated_pdf_is_an_error_with_no_traceback_text(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    data = pdf_bytes(pages=2)
    path, sha = stored(tmp_path, data[: len(data) // 2])
    done = render_first_page(path, sha, root=tmp_path / "cache")
    assert done.state == "error" and done.png is None and done.pages is None
    seen = capfd.readouterr()
    assert "Traceback" not in seen.out + seen.err
    assert list((tmp_path / "cache").iterdir()) == []


def test_a_child_that_prints_garbage_is_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = tmp_path / "liar.py"
    script.write_text('print("not json")\n')
    monkeypatch.setattr(render, "WORKER_COMMAND", (sys.executable, "-I", str(script)))
    path, sha = stored(tmp_path, pdf_bytes())
    assert render_first_page(path, sha, root=tmp_path / "c").state == "error"


def test_a_child_that_claims_success_without_a_picture_is_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = tmp_path / "liar.py"
    script.write_text("print('{\"pages\": 4}')\n")
    monkeypatch.setattr(render, "WORKER_COMMAND", (sys.executable, "-I", str(script)))
    path, sha = stored(tmp_path, pdf_bytes())
    assert render_first_page(path, sha, root=tmp_path / "c").state == "error"


def test_a_bad_hash_or_a_missing_file_is_an_error_without_a_child(
    tmp_path: Path, children: Children
) -> None:
    path, sha = stored(tmp_path, pdf_bytes())
    assert render_first_page(path, "../x", root=tmp_path / "c").state == "error"
    assert render_first_page(tmp_path / "gone.pdf", sha, root=tmp_path / "c").state == "error"
    assert children.started == []


def test_the_child_command_is_an_argument_list_with_a_stripped_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, object] = {}
    real = subprocess.Popen

    def spy(argv: list[str], *args: object, **kwargs: object) -> subprocess.Popen[bytes]:
        seen.update(argv=argv, **kwargs)
        return real(argv, *args, **kwargs)  # type: ignore[call-overload,no-any-return]

    monkeypatch.setattr(subprocess, "Popen", spy)
    monkeypatch.setenv("SECRET_TOKEN", "hunter2")
    path, sha = stored(tmp_path, pdf_bytes())
    render_first_page(path, sha, root=tmp_path / "c")
    assert seen["argv"][:4] == [sys.executable, "-I", "-m", "tl_tui.preview._worker"]  # type: ignore[index]
    assert seen["shell"] is False and seen["stdin"] is subprocess.DEVNULL
    assert "SECRET_TOKEN" not in seen["env"]  # type: ignore[operator]


@pytest.fixture
def no_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    """``worker.main`` sets process limits; never in the test runner's own process."""
    monkeypatch.setattr(worker, "_limit_resources", lambda: None)


def test_the_worker_itself_refuses_a_file_without_the_header(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], no_limits: None
) -> None:
    path, sha = stored(tmp_path, b"PK\x03\x04 a zip, not a PDF")
    assert worker.main([str(path), sha, str(tmp_path / "c")]) == 1
    assert json.loads(capsys.readouterr().out) == {"error": "not_pdf"}
    assert not (tmp_path / "c").exists()


def test_the_worker_refuses_a_link_and_a_bad_hash_and_wrong_arguments(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], no_limits: None
) -> None:
    path, sha = stored(tmp_path, pdf_bytes())
    link = tmp_path / "link.pdf"
    link.symlink_to(path)
    assert worker.main([str(link), sha, str(tmp_path / "c")]) == 1
    assert worker.main([str(path), "nothex", str(tmp_path / "c")]) == 1
    assert worker.main([str(path)]) == 2
    assert not (tmp_path / "c").exists()
    capsys.readouterr()


def test_the_worker_scale_keeps_the_longer_side_and_the_area_in_bounds() -> None:
    assert worker.scale_for(0, 100) == 0.0
    assert worker.scale_for(300, 400) == worker.MAX_SCALE  # a small page is drawn at 2x
    assert worker.scale_for(600, 800) == 1.5  # the longer side stops at 1200
    for width, height in ((14400, 14400), (14400, 10), (100, 14400), (5000, 4000)):
        scale = worker.scale_for(width, height)
        assert max(width, height) * scale <= worker.MAX_SIDE + 1e-6
        assert width * scale * height * scale <= worker.MAX_PIXELS + 1e-6


def test_the_worker_imports_no_network_module() -> None:
    probe = (
        "import sys, tl_tui.preview._worker as w\n"
        "import pypdfium2, PIL.Image\n"
        "names = ('socket', 'ssl', 'http.client', 'urllib.request', 'httpx')\n"
        "bad = [m for m in names if m in sys.modules]\n"
        "print(bad)\n"
    )
    out = subprocess.run(
        [sys.executable, "-I", "-c", probe], capture_output=True, text=True, check=True
    ).stdout.strip()
    assert out == "[]", out


def test_the_caps_are_the_documented_ones() -> None:
    assert worker.MAX_SIDE == 1200 and worker.MAX_PIXELS == 1_500_000
    assert worker.MEMORY_LIMIT == 1 << 30
    assert cache.MAX_ENTRIES == 200


def test_the_worker_limits_its_own_process_only(monkeypatch: pytest.MonkeyPatch) -> None:
    import resource

    set_to: dict[int, tuple[int, int]] = {}
    monkeypatch.setattr(resource, "setrlimit", lambda which, pair: set_to.update({which: pair}))
    worker._limit_resources()
    assert set_to[resource.RLIMIT_AS] == (worker.MEMORY_LIMIT, worker.MEMORY_LIMIT)
    assert set_to[resource.RLIMIT_CPU] == (worker.CPU_SECONDS, worker.CPU_SECONDS)
