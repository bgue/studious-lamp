"""Runs a ported acceptance script's ``main`` over a fresh seed ledger inside pytest."""

from __future__ import annotations

from pathlib import Path
from types import ModuleType

import pytest
import seed_ledger


def run_main(
    module: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Point the script at a fresh seed ledger (and its screenshots at ``tmp_path``) and call
    ``main``; the test fails with the script's own output when ``main`` does not return 0."""
    (tmp_path / "seed").mkdir()
    seed = seed_ledger.build_seed(tmp_path / "seed" / "p2-i3.db")
    monkeypatch.setattr(module, "LEDGER", seed)
    if hasattr(module, "SHOTS"):
        monkeypatch.setattr(module, "SHOTS", tmp_path / "shots")
    monkeypatch.delenv("TL_PG_URL", raising=False)  # the parity run covers Postgres elsewhere
    status = module.main()
    out = capsys.readouterr().out
    assert status == 0, (
        "\n".join(line for line in out.splitlines() if "FAIL" in line) or out[-2000:]
    )
