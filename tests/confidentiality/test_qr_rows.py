"""Scan code confidentiality row (P2-QR S2): a code is hidden when its target is (ADR-0016,
ADR-0030). The subject chain follows two hops; the record reached on the last hop governs.

Records are made through the forms, quality and correspondence modules' own commands; codes through
the QR service with a fake scan-card provider for each target type.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from tl_adapters.db import DbTarget, create_schema, open_uow
from tl_core import confidentiality as cf
from tl_core.qr import registry
from tl_core.services import queries
from tl_core.services.errors import RecordNotFoundError
from tl_core.settings import resolver
from tl_core.util import new_ulid

_PACKAGES = Path(__file__).resolve().parents[2] / "packages"
for _tests in ("tl-modules/forms/tests", "tl-modules/qr/tests"):
    if str(_PACKAGES / _tests) not in sys.path:
        sys.path.insert(0, str(_PACKAGES / _tests))

from forms_world import SCOPE, World, answer  # noqa: E402
from qr_world import BASE, FakeProvider, providers_of  # noqa: E402
from tl_mod_qr import service  # noqa: E402
from tl_mod_qr.commands import IssueScanCode  # noqa: E402

LOW = cf.Viewer(actor="user:vera", level=0, account="user:vera")
AGENT = cf.Viewer(actor="agent:bot", level=0, account="")
NOBODY = cf.LOWEST
CLEARED = cf.Viewer(actor="user:dora", level=1, account="user:dora")
ADMIN = cf.Viewer(actor="user:ada", level=1, account="user:ada")
LOWS = {"user": LOW, "agent": AGENT, "nobody": NOBODY}
TYPES = (
    "awp.IWP",
    "correspondence.Correspondence",
    "quality.PunchItem",
    "forms.Submission",
)


@pytest.fixture
def world(new_db: Callable[[], DbTarget], monkeypatch: pytest.MonkeyPatch) -> World:
    target = new_db()
    create_schema(target)
    made = World(target)
    made.people()
    real = resolver.value_of

    def value_of(conn: Any, key: str, **kwargs: Any) -> Any:
        return BASE if key == service.BASE_URL else real(conn, key, **kwargs)

    monkeypatch.setattr(service, "value_of", value_of)
    fakes = providers_of(*(FakeProvider(t) for t in TYPES))
    monkeypatch.setattr(registry, "load_scan_cards", lambda *a, **k: fakes)
    return made


def issue(world: World, target: str, who: str = "dora") -> str:
    """The id of a code for ``target``, issued by ``who`` as that person's viewer."""
    cmd = IssueScanCode(actor=f"user:{who}", source="test", scope=SCOPE, target_id=target)
    with open_uow(world.db) as uow:
        with cf.use_viewer(cf.viewer_for_actor(uow.conn(), cmd.actor)):
            return service.issue(uow, cmd).result.stream_id


def hidden(world: World, record: str, viewer: cf.Viewer) -> bool:
    with open_uow(world.db, readonly=True) as uow:
        return cf.is_hidden(uow.conn(), record, viewer)


def raise_punch(world: World, source: str) -> str:
    """A punch item raised by the controller from ``source``, by the quality module's command."""
    from tl_core.auth.module_roles import require_command_access
    from tl_mod_quality.commands import RaisePunchItem
    from tl_mod_quality.module import PUNCH_COMMANDS

    row = next(c for c in PUNCH_COMMANDS if c.model is RaisePunchItem)
    cmd = RaisePunchItem(
        actor="user:dora", source="test", scope=SCOPE, subject="Rail", from_record_id=source
    )
    with open_uow(world.db) as uow:
        require_command_access(uow.conn(), cmd)
        with cf.use_viewer(cf.viewer_for_actor(uow.conn(), cmd.actor)):
            return str(row.handler(uow, cmd).stream_id)


def submission(world: World, subject: str) -> str:
    """A submission about ``subject``, filed by the controller with nothing hidden."""
    template = world.template()
    cmd = world.command("dora", "SubmitForm", None, template_id=template, subject_id=subject,
                        answers=[answer("topic", "x")])  # fmt: skip
    from tl_mod_forms.module import FORMS_COMMANDS

    handler = next(c.handler for c in FORMS_COMMANDS if c.model.__name__ == "SubmitForm")
    with cf.system_view(), open_uow(world.db) as uow:
        return str(handler(uow, cmd).stream_id)


# --- the row ----------------------------------------------------------------------------------


def test_the_row_is_appended_after_the_forms_rows_and_the_hops_are_unchanged() -> None:
    assert cf.SUBJECT_LINKS[9:] == (("qr.ScanCode", "cur_qr_scan_code", "id", "target_id"),)
    assert [row[0] for row in cf.SUBJECT_LINKS[6:9]] == [
        "forms.Submission",
        "forms.IntakeItem",
        "forms.IntakeCode",
    ]
    assert cf._HOPS == 2  # pyright: ignore[reportPrivateUsage]


# --- a code for a restricted record -----------------------------------------------------------


def test_a_code_for_a_restricted_record_is_absent_for_the_five_readers(world: World) -> None:
    secret = world.hidden_record()
    plain = world.record("awp.IWP", "OPEN-1")
    hidden_code, open_code = issue(world, secret), issue(world, plain)
    ghost = new_ulid()
    with open_uow(world.db, readonly=True) as uow:
        events = uow.ledger.read_after(0, scope=SCOPE, limit=1000)
    own = {e.event_id for e in events if e.stream_id == hidden_code}
    assert len(own) == 2  # Record.Created and ScanCode.Issued
    rows = world.rows("SELECT event_id, stream_id, stream_type, payload FROM events")
    for name, viewer in LOWS.items():
        assert hidden(world, hidden_code, viewer) and not hidden(world, open_code, viewer), name
        with open_uow(world.db, readonly=True) as uow, cf.use_viewer(viewer):
            conn = uow.conn()
            assert queries.record_history(uow, hidden_code) == queries.record_history(uow, ghost)
            assert queries.get_record_by_id(uow, hidden_code) is None
            with pytest.raises(RecordNotFoundError) as caught:
                cf.require_visible(conn, hidden_code)
            assert str(caught.value) == f"no record {hidden_code!r}"
            clause, params = cf.not_hidden("r.id", viewer)
            listed = conn.execute(
                text(f"SELECT r.id FROM cur_qr_scan_code r WHERE {clause}"), params
            ).all()
            counted = conn.execute(
                text(f"SELECT COUNT(*) FROM cur_qr_scan_code r WHERE {clause}"), params
            ).scalar_one()
            assert [r.id for r in listed] == [open_code] and counted == 1, name
            shown = {e.event_id for e in cf.filter_events(conn, events)}
            assert not own & shown, name
            assert cf.hidden_row_ids(conn, rows) & own == own, name
    for viewer in (CLEARED, ADMIN):
        assert not hidden(world, hidden_code, viewer)
        with open_uow(world.db, readonly=True) as uow, cf.use_viewer(viewer):
            clause, params = cf.not_hidden("r.id", viewer)
            counted = (
                uow.conn()
                .execute(text(f"SELECT COUNT(*) FROM cur_qr_scan_code r WHERE {clause}"), params)
                .scalar_one()
            )
            assert counted == 2
            assert own <= {e.event_id for e in cf.filter_events(uow.conn(), events)}
            assert cf.hidden_row_ids(uow.conn(), rows) & own == set()


def test_a_code_for_a_privileged_record_is_hidden_from_the_admin_too(world: World) -> None:
    secret = world.hidden_record("privileged")
    code = issue(world, secret)
    for viewer in (*LOWS.values(), ADMIN):
        assert hidden(world, code, viewer)
    assert not hidden(world, code, CLEARED)  # the one named on the item


# --- hops -------------------------------------------------------------------------------------


def test_a_code_for_a_punch_item_raised_from_a_restricted_record_is_hidden_on_the_second_hop(
    world: World,
) -> None:
    secret = world.hidden_record()
    punch = raise_punch(world, secret)
    code = issue(world, punch)
    assert hidden(world, punch, LOW)
    for name, viewer in LOWS.items():
        assert hidden(world, code, viewer), name
    assert not hidden(world, code, CLEARED) and not hidden(world, code, ADMIN)


def test_a_chain_of_three_stops_at_two_hops_and_the_last_record_governs(world: World) -> None:
    """code -> submission -> punch item -> restricted record: the punch item is reached on the
    last hop and governs (it is internal), so the code is not hidden; the submission, two hops from
    the secret, is."""
    secret = world.hidden_record()
    punch = raise_punch(world, secret)
    filed = submission(world, punch)
    code = issue(world, filed)
    assert hidden(world, filed, LOW)
    assert hidden(world, punch, LOW)
    assert not hidden(world, code, LOW)
    assert not hidden(world, code, CLEARED)
