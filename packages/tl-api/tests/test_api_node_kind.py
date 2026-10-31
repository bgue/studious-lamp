"""Node kind (OC-S2): the 503 ``node_kind_not_built`` row and the start-up refusal.

``TL_NODE_KIND`` ``site`` or ``device`` stops ``tl serve`` and ``tl tui`` before any ledger is
opened, because the replica layer arrives in Phase 3.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from tl_api import main as server
from tl_api.errors import body_for, exception_for, spec_for
from tl_core import offline
from tl_core.offline import NodeKindNotBuiltError, OnlineOnlyError

PHASE_3 = "offline replicas arrive in Phase 3"


def test_node_kind_not_built_is_a_503_row_that_round_trips() -> None:
    row = spec_for(NodeKindNotBuiltError("x"))
    assert row is not None and (row.error, row.status) == ("node_kind_not_built", 503)
    mapped = body_for(NodeKindNotBuiltError(PHASE_3))
    assert mapped is not None
    status, body = mapped
    assert (status, body.error) == (503, "node_kind_not_built")
    rebuilt = exception_for(status, body.model_dump(mode="json", exclude_none=True))
    assert type(rebuilt) is NodeKindNotBuiltError and str(rebuilt) == PHASE_3


def test_online_only_is_a_409_row() -> None:
    row = spec_for(OnlineOnlyError("x"))
    assert row is not None and (row.error, row.status) == ("online_only", 409)


@pytest.fixture
def nothing_opens(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Make every step after the node-kind check fail loudly if it runs."""
    touched: list[str] = []

    def boom(name: str) -> Any:
        def fail(*args: object, **kwargs: object) -> None:
            touched.append(name)
            raise AssertionError(f"{name} ran before the node-kind refusal")

        return fail

    monkeypatch.setattr(server, "parse_args", boom("parse_args"))
    monkeypatch.setattr(server, "check_bind", boom("check_bind"))
    import tl_adapters.backend as backend

    monkeypatch.setattr(backend, "ledger_exists", boom("ledger_exists"))
    return touched


@pytest.mark.parametrize("kind", ["device", "site"])
def test_serve_refuses_a_replica_kind_before_any_ledger_opens(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    nothing_opens: list[str],
    kind: str,
) -> None:
    monkeypatch.setenv(offline.NODE_KIND_VARIABLE, kind)
    assert server.main(["--db", "/nonexistent/never.db"]) == 2
    err = capsys.readouterr().err
    assert err == f"error: {PHASE_3}\n"
    assert nothing_opens == []


def test_serve_refuses_an_unknown_node_kind(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], nothing_opens: list[str]
) -> None:
    monkeypatch.setenv(offline.NODE_KIND_VARIABLE, "moon")
    assert server.main([]) == 2
    assert "TL_NODE_KIND must be one of authority, site, device" in capsys.readouterr().err
    assert nothing_opens == []


@pytest.mark.parametrize("value", [None, "", "authority"])
def test_serve_on_an_authority_goes_on_to_the_ledger_check(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    value: str | None,
) -> None:
    if value is None:
        monkeypatch.delenv(offline.NODE_KIND_VARIABLE, raising=False)
    else:
        monkeypatch.setenv(offline.NODE_KIND_VARIABLE, value)
    assert server.main(["--db", str(tmp_path / "missing.db")]) == 2
    err = capsys.readouterr().err
    assert "tl init" in err and PHASE_3 not in err


@pytest.mark.parametrize("kind", ["device", "site"])
def test_the_tui_refuses_a_replica_kind_before_it_signs_in(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], kind: str
) -> None:
    from tl_tui import main as tui

    def no_sign_in(**kwargs: object) -> None:
        raise AssertionError("sign-in started before the node-kind refusal")

    monkeypatch.setattr(tui, "sign_in_first", no_sign_in)
    monkeypatch.setenv(offline.NODE_KIND_VARIABLE, kind)
    with pytest.raises(SystemExit) as raised:
        tui.run(db="/nonexistent/never.db")
    assert raised.value.code == 2
    assert capsys.readouterr().err == f"error: {PHASE_3}\n"
