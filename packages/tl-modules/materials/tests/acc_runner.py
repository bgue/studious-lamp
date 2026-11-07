"""Runs a ported acceptance script's ``main`` over a fresh seed ledger inside pytest."""

from __future__ import annotations

from pathlib import Path
from types import ModuleType

import pytest
import seed_ledger

_SEED: list[Path] = []  # the seed is built once per session; every script copies it before use


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


def shared_seed(factory: pytest.TempPathFactory) -> Path:
    """The seed ledger, built once per session (scripts only ever copy it)."""
    if not _SEED:
        _SEED.append(seed_ledger.build_seed(factory.mktemp("seed") / "p2-i3.db"))
    return _SEED[0]


def point_at_seed(
    module: ModuleType, factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Aim ``module.LEDGER`` (and ``SHOTS``) at the shared seed; return the seed path.

    ``TL_PG_URL`` is unset only for this test (monkeypatch restores it): the scripts' own Postgres
    legs (S5, S6) stay out of the parity run, which covers Postgres with ``new_db`` elsewhere.
    """
    seed = shared_seed(factory)
    monkeypatch.setattr(module, "LEDGER", seed)
    if hasattr(module, "SHOTS"):
        monkeypatch.setattr(module, "SHOTS", factory.mktemp("shots"))
    monkeypatch.delenv("TL_PG_URL", raising=False)
    return seed


def check_ids(module: ModuleType) -> list[object]:
    """``pytest.param`` per entry of ``module.CHECKS``, identified by the check function's name."""
    return [pytest.param(label, id=fn.__name__) for label, fn in module.CHECKS]


def run_check(
    module: ModuleType,
    label: str | None,
    factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    *,
    screens: bool = False,
    cumulative: bool = False,
) -> None:
    """Run ``module.main`` with only the check ``label`` (``None``: none) and, if ``screens``,
    the script's screen checks; a failure shows the script's ``FAIL`` line for that one check.
    ``cumulative``: the checks of the script that build on one another run in order up to
    ``label``, the failing one being the last."""
    point_at_seed(module, factory, monkeypatch)
    names = [c[0] for c in module.CHECKS]
    keep = names[: names.index(label) + 1] if cumulative and label in names else [label]
    monkeypatch.setattr(module, "CHECKS", [c for c in module.CHECKS if c[0] in keep])
    if hasattr(module, "screen_checks") and not screens:
        monkeypatch.setattr(module, "screen_checks", lambda db: None)
    status = module.main()
    out = capsys.readouterr().out
    assert status == 0, (
        "\n".join(line for line in out.splitlines() if "FAIL" in line) or out[-2000:]
    )


def ledger_copy(module: ModuleType, tmp: Path) -> Path:
    """A private copy of the seed (with WAL sidecars) as ``tmp/tl.db``."""
    import shutil

    for src in module.LEDGER.parent.glob(module.LEDGER.name + "*"):
        shutil.copy(src, tmp / ("tl.db" + src.name[len(module.LEDGER.name) :]))
    return tmp / "tl.db"
