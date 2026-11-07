"""The constraint routes check ``core.constraint.view`` the way the CLI and the embedded client do
(P2-I2-T04c3): through ``require_word`` on the project, before any read; a hidden subject answers
as a missing one; a key shared by two record types resolves to the subject (F3).

Readers: ``vic`` (a ``user`` account whose ``holds_word`` is stubbed to False: the shipped role
table grants ``read`` to every role, and a dev token always carries the ``user`` role, so no real
reader lacks the word), ``uma`` (``user``, low clearance, has the word) and ``ada`` (``admin``,
high clearance). The agent case uses a dev agent token.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from harness import Harness
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from tl_adapters.db import open_uow
from tl_api.routes import constraints as routes
from tl_api.tokens import add_token
from tl_core import confidentiality as cf
from tl_core import modules as tl_modules
from tl_core.auth import module_roles, sessions
from tl_core.constraints import command_table
from tl_core.modules import ConfidentialSource
from tl_mod_awp.names import IWP

PASSWORD = "correct horse battery"
SCOPE = "project:P123"
BASE = "/projects/P123/constraints"
CLASS_TABLE = "t04c3_class"
CMDS = {c.model.__name__: c for c in command_table()}
ROOT = Path(__file__).resolve().parents[3]


def load_world() -> ModuleType:
    """The awp test world (``awp_world``), loaded by path as ``test_api_awp.load_world`` does."""
    name = "awp_world"
    if name in sys.modules:
        return sys.modules[name]
    import importlib.util

    path = ROOT / "packages" / "tl-modules" / "awp" / "tests" / "awp_world.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@dataclass
class Rig:
    h: Harness
    target: Any
    shown: str  # key of the visible IWP
    hidden: str  # key of the restricted IWP (low clearance cannot read it)
    shown_con: str  # key of the constraint on the visible IWP
    hidden_con: str  # key of the constraint on the restricted IWP
    shown_id: str
    hidden_id: str

    def client(self, username: str | None) -> Any:
        client = self.h.client_for(None)
        if username is not None:
            _, token = sessions.sign_in(self.h.backend, username=username, password=PASSWORD)
            client.headers.update({"Authorization": f"Bearer {token}"})
        return client


def run(target: Any, who: str, name: str, **fields: Any) -> Any:
    spec = CMDS[name]
    cmd = spec.model(actor=f"user:{who}", source="test", scope=SCOPE, **fields)
    with open_uow(target) as uow, cf.use_viewer(cf.viewer_for_actor(uow.conn(), cmd.actor)):
        return spec.handler(uow, cmd)


def raise_on(target: Any, subject: str, description: str) -> Any:
    return run(
        target,
        "uma",
        "RaiseConstraint",
        subject=subject,
        phase="ready",
        severity="blocking",
        category="materials",
        owner="user:uma",
        due_at="2026-12-01",
        description=description,
    )


def _classify(target: Any, record_id: Any, cls: str) -> None:
    """A row in the test class table (every IWP must have one, or the source hides it)."""
    with open_uow(target) as uow:
        uow.conn().execute(
            text(f"INSERT INTO {CLASS_TABLE} (id, cls) VALUES (:i, :c)"),
            {"i": str(record_id), "c": cls},
        )


def key_of(target: Any, record_id: str) -> str:
    with open_uow(target, readonly=True) as uow:
        return str(
            uow.conn()
            .execute(text("SELECT key FROM cur_core_record WHERE id = :i"), {"i": record_id})
            .scalar_one()
        )


@pytest.fixture
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Rig]:
    h = Harness.build(tmp_path)
    try:
        target = h.target or h.db
        world = load_world().World(target)
        world.people()
        world.editions()
        world.person("vic", ("user",))
        shown_id = world.iwp(discipline="PIP", title="Spools")
        hidden_id = world.iwp(discipline="CIV", title="Footing")
        shown_con = raise_on(target, shown_id, "Spools late")
        hidden_con = raise_on(target, hidden_id, "Footing open")
        # the class source goes in after the seed: uma (low clearance) cannot read the hidden IWP
        with open_uow(target) as uow:
            conn = uow.conn()
            conn.execute(text(f"CREATE TABLE {CLASS_TABLE} (id TEXT PRIMARY KEY, cls TEXT)"))
            for record_id, cls in ((shown_id, "internal"), (hidden_id, "restricted")):
                conn.execute(
                    text(f"INSERT INTO {CLASS_TABLE} (id, cls) VALUES (:i, :c)"),
                    {"i": str(record_id), "c": cls},
                )
        source = ConfidentialSource(
            record_types=frozenset({IWP}), table=CLASS_TABLE, id_column="id", class_column="cls"
        )
        original = tl_modules.confidential_sources
        monkeypatch.setattr(cf, "confidential_sources", lambda: [*original(), source])
        yield Rig(
            h=h,
            target=target,
            shown=key_of(target, str(shown_id)),
            hidden=key_of(target, str(hidden_id)),
            shown_con=key_of(target, str(shown_con.stream_id)),
            hidden_con=key_of(target, str(hidden_con.stream_id)),
            shown_id=str(shown_id),
            hidden_id=str(hidden_id),
        )
    finally:
        h.close()


def stub_no_word(monkeypatch: pytest.MonkeyPatch, actor: str) -> None:
    """``actor`` holds no access word (a test stub of ``holds_word``; see the module docstring)."""
    real = module_roles.holds_word

    def fake(conn: Any, holder: Any, **kwargs: Any) -> bool:
        if holder.actor == actor:
            return False
        return real(conn, holder, **kwargs)

    monkeypatch.setattr(module_roles, "holds_word", fake)


READ_ROUTES = [
    ("list", BASE, {}),
    ("groups", f"{BASE}/groups", {"by": "owner"}),
    ("detail", f"{BASE}/{{key}}", {}),
]


def _path(route: str, key: str) -> tuple[str, dict[str, Any]]:
    for name, path, params in READ_ROUTES:
        if name == route:
            return path.format(key=key), dict(params)
    raise KeyError(route)


# --- 1. a role without the word: 403 before any read ---------------------------------------


@pytest.mark.parametrize("route", ["list", "groups", "detail"])
def test_no_word_is_refused_before_any_read(
    rig: Rig, monkeypatch: pytest.MonkeyPatch, route: str
) -> None:
    stub_no_word(monkeypatch, "user:vic")

    def boom(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("a constraint read ran before the word check")

    for name in ("list_constraints", "get_constraint", "review_groups", "count_constraints"):
        monkeypatch.setattr(routes, name, boom)
    client = rig.client("vic")
    path, params = _path(route, "P123-CON-9999")
    response = client.get(path, params=params)
    assert response.status_code == 403, response.text
    assert response.json()["error"] == "forbidden"


def test_unknown_key_without_the_word_is_403_not_404(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_no_word(monkeypatch, "user:vic")
    client = rig.client("vic")
    unknown = client.get(f"{BASE}/P123-CON-9999")
    known = client.get(f"{BASE}/{rig.shown_con}")
    assert unknown.status_code == known.status_code == 403
    assert unknown.json()["error"] == "forbidden"


# --- 2. the word, low clearance: a hidden subject is unknown ------------------------------


def test_low_clearance_hidden_constraint_is_404_as_missing(rig: Rig) -> None:
    client = rig.client("uma")
    hidden = client.get(f"{BASE}/{rig.hidden_con}")
    missing = client.get(f"{BASE}/P123-CON-9999")
    assert hidden.status_code == missing.status_code == 404
    assert hidden.json()["error"] == missing.json()["error"] == "record_not_found"
    assert hidden.text.replace(rig.hidden_con, "KEY") == missing.text.replace(
        "P123-CON-9999", "KEY"
    )


def test_low_clearance_total_does_not_count_the_hidden_subject(rig: Rig) -> None:
    client = rig.client("uma")
    body = client.get(BASE).json()
    assert body["total"] == 1
    assert [r["key"] for r in body["rows"]] == [rig.shown_con]
    groups = client.get(f"{BASE}/groups", params={"by": "owner"}).json()
    assert sum(g["count"] for g in groups["groups"]) == 1
    hidden_subject = client.get(BASE, params={"subject": rig.hidden}).json()
    assert hidden_subject == {"rows": [], "total": 0}


# --- 3. the word, high clearance: served ----------------------------------------------------


def test_high_clearance_reads_the_hidden_constraint(rig: Rig) -> None:
    client = rig.client("ada")
    assert client.get(f"{BASE}/{rig.hidden_con}").status_code == 200
    body = client.get(BASE).json()
    assert body["total"] == 2
    assert {r["key"] for r in body["rows"]} == {rig.shown_con, rig.hidden_con}


# --- 4. an agent with the word: still closed by the pinned agent table ----------------------


def test_agent_is_refused_by_the_pinned_agent_rule_even_with_the_word(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = add_token(rig.h.settings.tokens_path, "agent:triage")
    client = rig.h.client_for(None)
    client.headers.update({"Authorization": f"Bearer {token}"})
    assert client.get(BASE).status_code == 403
    monkeypatch.setattr(module_roles, "holds_word", lambda *a, **k: True)
    assert client.get(BASE).status_code == 403


# --- 5. F3: the subject key lookup -----------------------------------------------------------


def test_a_key_is_unique_per_scope_so_the_subject_lookup_has_one_row(rig: Rig) -> None:
    """F3 premise check. The ticket said a key is unique per type, not per scope; the generated
    DDL says the opposite (``ux_cur_core_record_scope_key``), so a constraint cannot share its
    subject's key in one scope and the ``LIMIT 1`` on the subject lookup is a guard, not a fix.
    This pins the index so a change of premise is seen here."""
    with pytest.raises(IntegrityError), open_uow(rig.target) as uow:
        uow.conn().execute(
            text("UPDATE cur_core_record SET key = :k WHERE id = :i"),
            {"k": rig.shown, "i": rig.hidden_id},
        )
