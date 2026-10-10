"""``seed``: the dev MCP tool that seeds the dev ledger through the API, and what it must refuse."""

from __future__ import annotations

import dataclasses
import socket
import subprocess
import time
from pathlib import Path

import pytest
from dev_harness import DevHarness
from mcp.server.mcpserver.exceptions import ToolError
from tl_mcp.dev.guard import DevTarget, find_repo_root
from tl_mcp.dev.runtime import DevContext

REPO = find_repo_root()


def _port_refused(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return False
    except ConnectionRefusedError:
        return True


def _wait_refused(port: int, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if _port_refused(port):
            return True
        time.sleep(0.2)
    return _port_refused(port)


def _git_status(repo: Path) -> list[str]:
    done = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True, check=False
    )
    return sorted(done.stdout.splitlines())


def test_seed_xs_adds_a_simulated_project(dev_env: DevHarness, tmp_path: Path) -> None:
    before = _git_status(REPO)
    out = dev_env.structured("seed", scale="xs")
    after = _git_status(REPO)

    assert out["ok"] is True and out["timed_out"] is False and out["exit_code"] == 0
    assert out["scale"] == "xs"
    assert out["run"]
    assert out["scope"].startswith("project:sim-")
    assert out["records"] > 0
    assert "ok: " in out["output_tail"]

    count = dev_env.structured(
        "query_db",
        sql=f"SELECT count(*) FROM cur_core_record WHERE scope = '{out['scope']}'",
    )
    assert count["rows"][0][0] >= out["records"]

    seed_lines = [line for line in dev_env.audit_lines() if line["tool"] == "seed"]
    assert seed_lines[-1]["outcome"] == "ok"

    assert (tmp_path / "seed-tokens.json").is_file()
    assert (tmp_path / "sim").is_dir()
    assert after == before  # nothing new in the repository from this call


def test_no_api_is_left_running_after_seed(dev_env: DevHarness) -> None:
    out = dev_env.structured("seed", scale="xs")
    assert out["ok"] is True
    assert _wait_refused(out["api_port"], 5.0), "the API started by seed still answers"


def test_a_timeout_is_a_result_and_frees_the_port(dev_env: DevHarness) -> None:
    out = dev_env.structured("seed", scale="xs", timeout_s=1)
    assert out["timed_out"] is True
    assert out["ok"] is False
    assert out["exit_code"] == -1
    assert _wait_refused(out["api_port"], 15.0), "the API started by seed still answers"


def test_a_postgres_target_is_refused(tmp_path: Path, dev_pg_target: DevTarget) -> None:
    assert dev_pg_target.kind == "postgres"
    env = DevHarness.build(tmp_path, target=dev_pg_target)
    with pytest.raises(ToolError, match="refused"):
        env.call("seed", scale="xs")
    assert env.audit_lines()[-1]["outcome"] == "refused"


def test_a_repository_without_the_seed_script_is_refused(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "dev").mkdir(parents=True)
    (repo / "AGENTS.md").write_text("# agents\n", encoding="ascii")
    (repo / "justfile").write_text("check:\n\ttrue\n", encoding="ascii")
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    env = DevHarness.build(ledger, repo_root=repo)
    with pytest.raises(ToolError, match="seed.sh"):
        env.call("seed", scale="xs")


def test_the_schema_rejects_an_unknown_scale_and_a_zero_timeout(dev_env: DevHarness) -> None:
    with pytest.raises(ToolError):
        dev_env.call("seed", scale="l")
    with pytest.raises(ToolError):
        dev_env.call("seed", timeout_s=0)


def test_the_child_environment_drops_the_servers_other_variables(dev_env: DevHarness) -> None:
    ctx: DevContext = dataclasses.replace(
        dev_env.ctx,
        environ={"PATH": "/usr/bin:/bin", "HOME": "/root", "SECRET": "x", "TL_ENV": "prod"},
    )
    env = ctx.child_env({"TL_DB": "/tmp/x.db"})
    assert "SECRET" not in env
    assert env["TL_ENV"] == "dev"
    assert env["PATH"] == "/usr/bin:/bin" and env["HOME"] == "/root"
    assert env["TL_DB"] == "/tmp/x.db"


def test_stop_api_on_kills_a_server_started_in_its_own_session() -> None:
    """The SIGKILL fallback cannot reach an API started with setsid: it is found by its port."""
    import os
    import subprocess
    import sys
    import time

    from tl_mcp.dev.tool_seed import _free_loopback_port, _stop_api_on  # pyright: ignore

    port = _free_loopback_port()
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)", "serve", "--port", str(port)],
        start_new_session=True,
    )
    try:
        time.sleep(0.3)
        _stop_api_on(port)
        assert child.wait(timeout=5) != 0
        assert os.getpid() != child.pid
    finally:
        if child.poll() is None:
            child.kill()
