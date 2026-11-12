"""The wave 1 tour runs headless on the demo project and writes its seven SVGs (P2-SEED-T03).

One run of ``main`` builds P200 in a temporary ledger (the generator, in this process), drives the
TUI over it and writes the screenshots. The tour changes the process's environment and working
directory and freezes the clock and the ULID source of ``tl_core`` (and the "today" of two modules)
for the rest of the process, so the test puts all of them back afterwards. ``seed_demo_project``
must stay the only place the tour seeds the ledger: no ``tl init --dev`` (the demo account)
anywhere in the module text.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOUR = ROOT / "dev" / "tour" / "wave1.py"


def _load_tour() -> ModuleType:
    """``dev/tour/wave1.py`` is a script, not a package: load it by path."""
    spec = importlib.util.spec_from_file_location("wave1_under_test", TOUR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # its dataclasses look their module up by name
    spec.loader.exec_module(module)
    return module


#: The module attributes the tour replaces (``dev/tour/tourkit.py``).
_PATCHED = (
    ("tl_core.util", "datetime"),
    ("tl_core.util", "ULID"),
    ("tl_core.webhooks.base", "datetime"),
    ("tl_lake.sync", "datetime"),
    ("tl_lake.query", "datetime"),
    ("tl_tui.widgets.domain_screen", "date"),
    ("tl_core.archive.signing", "generate_signer"),
)


@pytest.fixture
def restored_process() -> Iterator[None]:
    """Put the environment, the working directory and the patched module names back as the tour
    found them (a frozen clock put every later ledger event on the tour's day)."""
    saved_env = dict(os.environ)
    saved_cwd = Path.cwd()
    saved_names = [
        (module, name, getattr(module, name))
        for module, name in ((importlib.import_module(m), n) for m, n in _PATCHED)
    ]
    try:
        yield
    finally:
        for module, name, value in saved_names:
            setattr(module, name, value)
        os.environ.clear()
        os.environ.update(saved_env)
        os.chdir(saved_cwd)


def test_tour_writes_seven_svgs(tmp_path: Path, restored_process: None) -> None:
    tour = _load_tour()
    out = tmp_path / "wave1"
    code = tour.main(["--out", str(out)])
    assert code == 0, "the tour exits 1 on a TourFailed or a leak; see the output above"
    svgs = sorted(path.name for path in out.glob("*.svg"))
    assert len(svgs) >= 7, svgs
    assert [name[:2] for name in svgs[:7]] == ["01", "02", "03", "04", "05", "06", "07"], svgs


def test_tour_seeds_only_through_the_generator() -> None:
    text = TOUR.read_text(encoding="utf-8")
    assert 'init", "--dev"' not in text
    assert text.count("run(as_target(") == 1, "seed_demo_project is the one seeding call"
