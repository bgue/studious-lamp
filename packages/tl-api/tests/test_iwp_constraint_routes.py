"""The seven IWP and constraint read routes, walked as five kinds of reader on a SEEDED ledger
(P2-I2-S5, items 7 to 9; T04c1 review F1 to F3; T04c3 word walk).

The ledger holds, for every reader kind to find something: a visible IWP and a restricted one (low
clearance cannot read it), a constraint on each, a readiness evaluation on each (the visible
IWP's names the hidden one among its refs), and a third IWP whose subject is later deleted. The
five readers are ``vera`` (viewer), ``uma`` (user), ``bot`` (agent), ``ctl`` (document controller)
and ``ada`` (admin). A walk over an empty ledger proves nothing, so each test first asserts that
the high readers do read the hidden rows.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pytest
from sqlalchemy import text
from test_constraint_route_word import (  # noqa: F401  (rig is the seeded fixture of T04c3)
    BASE,
    SCOPE,
    Rig,
    _classify,
    key_of,
    load_world,
    raise_on,
    rig,
    stub_no_word,
)
from tl_adapters.db import open_uow
from tl_api.tokens import add_token

AWP = "/projects/P123/awp/iwps"
READERS = ("vera", "uma", "bot", "ctl", "ada")
HIGH = {"ctl", "ada"}
MISSING_ID = "01J00000000000000000MISSING"


@dataclass
class Seed:
    rig: Rig
    clients: dict[str, Any]
    spare: str  # key of a third visible IWP (readiness names a hidden record)
    spare_id: str
    twin: str  # key of a fourth IWP (readiness names a record that does not exist)
    twin_id: str


def readiness(target: Any, iwp: str, refs: list[str]) -> None:
    now = "2026-11-07T08:00:00Z"
    via = json.dumps([{"record_id": r, "record_type": "awp.IWP", "key": r} for r in refs])
    with open_uow(target) as uow:
        conn = uow.conn()
        conn.execute(
            text(
                "INSERT INTO cur_awp_readiness (iwp_id, scope, evaluated_at, today, ready, "
                "facts_hash, as_of_seq) VALUES (:i, :s, :n, '2026-11-07', :r, :h, 1)"
            ),
            {"i": iwp, "s": SCOPE, "n": now, "r": False, "h": "0" * 64},
        )
        conn.execute(
            text(
                "INSERT INTO cur_awp_readiness_check (row_id, scope, iwp_id, name, version, "
                "state, detail, count_ok, count_total, resolve_via_json, as_of_seq) VALUES "
                "(:r, :s, :i, 'rfis_answered', '1', 'blocked', 'fixed', 0, 1, :v, 1)"
            ),
            {"r": f"{iwp}:rfis", "s": SCOPE, "i": iwp, "v": via},
        )


@pytest.fixture
def seeded(rig: Rig) -> Iterator[Seed]:  # noqa: F811
    world = load_world().World(rig.target)
    world.person("ctl", ("document_controller",))
    spare, twin = (str(world.iwp(discipline="PIP", title=t)) for t in ("Spare", "Twin"))
    for record_id in (spare, twin):
        _classify(rig.target, record_id, "internal")
    readiness(rig.target, rig.shown_id, [rig.hidden_id])
    readiness(rig.target, rig.hidden_id, [])
    readiness(rig.target, spare, [rig.hidden_id])
    readiness(rig.target, twin, [MISSING_ID])
    clients: dict[str, Any] = {}
    for who in ("vera", "uma", "ctl", "ada"):
        clients[who] = rig.client(who)
    token = add_token(rig.h.settings.tokens_path, "agent:triage")
    bot = rig.h.client_for(None)
    bot.headers.update({"Authorization": f"Bearer {token}"})
    clients["bot"] = bot
    yield Seed(rig, clients, key_of(rig.target, spare), spare, key_of(rig.target, twin), twin)


def routes(s: Seed) -> dict[str, tuple[str, dict[str, str]]]:
    r = s.rig
    return {
        "iwp list": (AWP, {}),
        "iwp detail shown": (f"{AWP}/{r.shown}", {}),
        "iwp detail hidden": (f"{AWP}/{r.hidden}", {}),
        "iwp scope shown": (f"{AWP}/{r.shown}/scope", {}),
        "iwp scope hidden": (f"{AWP}/{r.hidden}/scope", {}),
        "readiness shown": (f"{AWP}/{r.shown}/readiness", {}),
        "readiness hidden": (f"{AWP}/{r.hidden}/readiness", {}),
        "readiness spare": (f"{AWP}/{s.spare}/readiness", {}),
        "constraint list": (BASE, {}),
        "constraint list by hidden subject": (BASE, {"subject": r.hidden}),
        "constraint groups": (f"{BASE}/groups", {"by": "owner"}),
        "constraint detail shown": (f"{BASE}/{r.shown_con}", {}),
        "constraint detail hidden": (f"{BASE}/{r.hidden_con}", {}),
    }


def answers(s: Seed, who: str) -> dict[str, Any]:
    return {n: s.clients[who].get(p, params=q) for n, (p, q) in routes(s).items()}


def hidden_markers(s: Seed) -> list[str]:
    r = s.rig
    return [r.hidden, r.hidden_id, r.hidden_con, "Footing"]


@pytest.mark.parametrize("who", READERS)
def test_five_readers_see_only_what_they_may_read_on_every_new_route(
    seeded: Seed, who: str
) -> None:
    got = answers(seeded, who)
    assert all(a.status_code < 500 for a in got.values()), who
    blob = " ".join(a.text for a in got.values() if a.status_code == 200)
    if who in HIGH:  # the walk is not vacuous: these readers do read the hidden rows
        assert all(a.status_code == 200 for n, a in got.items() if "by hidden" not in n), who
        assert all(m in blob for m in hidden_markers(seeded)), who
        return
    if who == "bot":  # the pinned agent table closes the constraint routes
        assert all(a.status_code == 403 for n, a in got.items() if n.startswith("constraint"))
    else:
        assert got["constraint list"].json()["total"] == 1
        assert got["iwp detail shown"].status_code == 200
        assert got["readiness shown"].status_code == 200
    for marker in hidden_markers(seeded):
        assert marker not in blob, (who, marker)
    for name in ("iwp detail hidden", "iwp scope hidden", "readiness hidden"):
        assert got[name].status_code in (403, 404), (who, name)


@pytest.mark.parametrize("who", ["vera", "uma"])
def test_a_hidden_record_answers_as_one_that_never_existed_on_the_route_bodies(
    seeded: Seed, who: str
) -> None:
    r, c = seeded.rig, seeded.clients[who]
    pairs = [
        (f"{AWP}/{r.hidden}", f"{AWP}/P123-IWP-PIP-8888", r.hidden, "P123-IWP-PIP-8888"),
        (
            f"{AWP}/{r.hidden}/scope",
            f"{AWP}/P123-IWP-PIP-8888/scope",
            r.hidden,
            "P123-IWP-PIP-8888",
        ),
        (
            f"{AWP}/{r.hidden}/readiness",
            f"{AWP}/P123-IWP-PIP-8888/readiness",
            r.hidden,
            "P123-IWP-PIP-8888",
        ),
        (f"{BASE}/{r.hidden_con}", f"{BASE}/P123-CON-9999", r.hidden_con, "P123-CON-9999"),
    ]
    for hidden, missing, hk, mk in pairs:
        a, b = c.get(hidden), c.get(missing)
        assert a.status_code == b.status_code == 404, hidden
        assert a.text.replace(hk, "K") == b.text.replace(mk, "K"), hidden
        assert sorted(a.headers) == sorted(b.headers)


def test_readiness_route_twin_hidden_ref_equals_missing_ref(seeded: Seed) -> None:
    """A check that names a hidden record answers like one that names a missing record."""
    c = seeded.clients["uma"]
    shown = c.get(f"{AWP}/{seeded.spare}/readiness")
    gone = c.get(f"{AWP}/{seeded.twin}/readiness")
    assert shown.status_code == gone.status_code == 200
    a, b = shown.json(), gone.json()
    assert a["checks"][0]["resolve_via"] == b["checks"][0]["resolve_via"] == []
    for body, ident in ((a, seeded.spare_id), (b, seeded.twin_id)):
        body["iwp_id"] = "ID"
        assert ident not in json.dumps(body)
    assert a == b
    assert seeded.rig.hidden_id not in shown.text and seeded.rig.hidden not in shown.text
    high = seeded.clients["ada"].get(f"{AWP}/{seeded.spare}/readiness").json()
    assert [x["record_id"] for x in high["checks"][0]["resolve_via"]] == [seeded.rig.hidden_id]


def test_a_constraint_whose_subject_is_hidden_or_deleted_is_absent_from_a_page(
    seeded: Seed,
) -> None:
    """T04c1 F2: rows and total agree, and no row is without its subject."""
    r = seeded.rig
    gone = raise_on(r.target, seeded.twin_id, "Twin open")
    gone_key = key_of(r.target, str(gone.stream_id))
    ada = seeded.clients["ada"]
    before = ada.get(BASE).json()
    assert {x["key"] for x in before["rows"]} >= {r.shown_con, r.hidden_con, gone_key}
    with open_uow(r.target) as uow:  # the subject's record row goes
        uow.conn().execute(text("DELETE FROM cur_core_record WHERE id = :i"), {"i": seeded.twin_id})
    for who in ("ada", "uma"):
        body = seeded.clients[who].get(BASE).json()
        assert gone_key not in {x["key"] for x in body["rows"]}, who
        assert len(body["rows"]) == body["total"], (who, body["total"], len(body["rows"]))
        assert all(x["subject_key"] for x in body["rows"])
        groups = seeded.clients[who].get(f"{BASE}/groups", params={"by": "owner"}).json()
        members = [m for g in groups["groups"] for m in g["members"]]
        assert gone_key not in {m["key"] for m in members}
        assert sum(g["count"] for g in groups["groups"]) == len(members)
    uma = seeded.clients["uma"].get(BASE).json()
    assert uma["total"] == 1 and uma["rows"][0]["key"] == r.shown_con  # the hidden one is absent


def test_the_subject_filter_picks_the_constraints_own_subject(seeded: Seed) -> None:
    """T04c1 F3: a record with the subject's key in another scope does not confuse the lookup (the
    index makes a key unique per scope, so a clash in one scope cannot be built; see T04c3)."""
    r = seeded.rig
    with open_uow(r.target) as uow:
        uow.conn().execute(
            text(
                "INSERT INTO cur_core_record (id, key, type, scope, title, status, version, "
                "last_seq, created_at, updated_at) VALUES ('other-scope-1', :k, 'awp.IWP', "
                "'project:P999', 'x', 'Draft', 1, 1, '2026-11-01', '2026-11-01')"
            ),
            {"k": r.shown},
        )
    body = seeded.clients["uma"].get(BASE, params={"subject": r.shown}).json()
    assert body["total"] == 1
    assert [(x["key"], x["subject_key"]) for x in body["rows"]] == [(r.shown_con, r.shown)]


# --- T04c3 word walk: three entry points, one refusal --------------------------------------------


def via_route(rig_: Rig, route: str) -> tuple[bool, str]:
    client = rig_.client("vic")
    path = {"list": BASE, "groups": f"{BASE}/groups", "detail": f"{BASE}/{rig_.shown_con}"}[route]
    got = client.get(path, params={"by": "owner"} if route == "groups" else {})
    return got.status_code == 403 and got.json()["error"] == "forbidden", got.text


def via_embedded(rig_: Rig, route: str) -> tuple[bool, str]:
    from tl_adapters.db import make_uow_factory
    from tl_core.auth.errors import ForbiddenError
    from tl_tui.embedded import EmbeddedClient

    client = EmbeddedClient(make_uow_factory(rig_.target), actor="user:vic")
    call = {
        "list": lambda: client.list_constraints("P123"),
        "groups": lambda: client.constraint_groups("P123", "owner"),
        "detail": lambda: client.get_constraint("P123", rig_.shown_con),
    }[route]
    try:
        call()
    except ForbiddenError as exc:
        return True, str(exc)
    return False, "served"


def via_cli(rig_: Rig, route: str) -> tuple[bool, str]:
    from tl_cli.main import app
    from typer.testing import CliRunner

    verb = {
        "list": ["ls"],
        "groups": ["groups", "--by", "owner"],
        "detail": ["show", rig_.shown_con],
    }
    result = CliRunner().invoke(
        app,
        [
            "--db",
            str(rig_.target),
            "constraint",
            *verb[route],
            "--project",
            "P123",
            "--actor",
            "user:vic",
        ],
    )
    out = result.output + (result.stderr if result.stderr_bytes else "")
    return result.exit_code != 0 and "forbidden" in out, out


@pytest.mark.parametrize("route", ["list", "groups", "detail"])
@pytest.mark.parametrize("entry", [via_route, via_embedded, via_cli], ids=lambda f: f.__name__)
def test_a_role_without_the_word_is_refused_the_same_way_at_every_entry_point(
    rig: Rig,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    entry: Any,
    route: str,
) -> None:
    stub_no_word(monkeypatch, "user:vic")
    refused, said = entry(rig, route)
    assert refused, said
    assert "core.constraint.view" in said or entry is via_route, said
    assert rig.hidden_con not in said and "Footing" not in said
