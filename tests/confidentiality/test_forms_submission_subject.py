"""A form submission is never the subject of another record (V3-FN1, wave review F1).

``confidentiality._chain_sql`` checks a submission's own class only for the submission itself, not
on a hop, so a record about a privileged submission (or about someone's draft) would be seen by
readers who may not see that submission, and would name its id. The commands refuse such a subject
in the one ``no record with that id`` text, byte for byte the text of an absent id: the forms
(S2, S5 over a draft, an intake code's context) and every other command whose link column is in
``SUBJECT_LINKS`` and takes any record type (permit, isolation, inspection). A plain subject works.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
from tl_adapters.db import create_schema, open_uow
from tl_core import confidentiality as cf
from tl_core.services.errors import RecordNotFoundError
from tl_core.settings import resolver
from tl_core.util import new_ulid

_PACKAGES = Path(__file__).resolve().parents[2] / "packages"
for _tests in ("tl-modules/forms/tests", "tl-modules/qr/tests"):
    if str(_PACKAGES / _tests) not in sys.path:
        sys.path.insert(0, str(_PACKAGES / _tests))

from forms_world import SCOPE, World, answer  # noqa: E402
from qr_world import BASE  # noqa: E402
from tl_core.constraints.commands import RaiseConstraint  # noqa: E402
from tl_core.constraints.handlers import handle_raise_constraint  # noqa: E402
from tl_mod_forms.module import FORMS_COMMANDS  # noqa: E402
from tl_mod_permits.commands import RequestPermit  # noqa: E402
from tl_mod_permits.handlers.isolation import handle_apply_isolation  # noqa: E402
from tl_mod_permits.handlers.permit import handle_request_permit  # noqa: E402
from tl_mod_permits.iso_commands import ApplyIsolation  # noqa: E402
from tl_mod_qr import service  # noqa: E402
from tl_mod_qr.commands import IssueScanCode  # noqa: E402
from tl_mod_quality.commands import PlanInspection  # noqa: E402
from tl_mod_quality.handlers.inspection import handle_plan_inspection  # noqa: E402

LOW = cf.Viewer(actor="user:vera", level=0, account="user:vera")
UNKNOWN = "no record with that id"


@pytest.fixture
def world(tmp_path: Path) -> World:
    db = tmp_path / "tl.db"
    create_schema(db)
    w = World(db)
    w.people()
    return w


def _as_system(w: World, who: str, name: str, **fields: Any) -> Any:
    cmd = w.command(who, name, None, **fields)
    handler = next(c.handler for c in FORMS_COMMANDS if c.model.__name__ == name)
    with cf.system_view(), open_uow(w.db) as uow:
        return handler(uow, cmd)


def _refusal(run: Any) -> str:
    with pytest.raises(RecordNotFoundError) as caught:
        run()
    return str(caught.value)


def _hidden(w: World, record: str, viewer: cf.Viewer) -> bool:
    with open_uow(w.db, readonly=True) as uow:
        return cf.is_hidden(uow.conn(), record, viewer)


def _run_as_dora(w: World, handler: Any, command: Any) -> Any:
    with open_uow(w.db) as uow:
        viewer = cf.viewer_for_actor(uow.conn(), "user:dora")
        with cf.use_viewer(viewer):
            return handler(uow, command)


def test_submission_subjects_refused_like_an_absent_id(world: World) -> None:
    w = world
    x = w.record("awp.IWP", "OPEN-1")
    privileged = w.template(answer_class="privileged")
    plain = w.template()
    s1 = str(
        _as_system(
            w, "dora", "SubmitForm", template_id=privileged, subject_id=x,
            answers=[answer("topic", "SECRET-ANS")],
        ).stream_id
    )  # fmt: skip
    assert _hidden(w, s1, LOW)
    draft = str(w.save("uma", plain, subject_id=x).stream_id)

    absent = _refusal(
        lambda: w.submit("dora", plain, subject_id=new_ulid(), answers=[answer("topic", "a")])
    )
    assert absent == UNKNOWN
    # S2: about the privileged submission; S5: about a draft; each the absent id's text
    s2 = _refusal(lambda: w.submit("dora", plain, subject_id=s1, answers=[answer("topic", "b")]))
    s5 = _refusal(lambda: w.submit("uma", plain, subject_id=draft, answers=[answer("topic", "z")]))
    save = _refusal(lambda: w.save("dora", plain, subject_id=s1))
    assert s2.encode() == s5.encode() == save.encode() == absent.encode()

    # an intake code whose context is a submission
    it = w.intake_template()
    before = w.count()
    code = _refusal(lambda: w.issue(it, who="ada", context_id=s1))
    code_draft = _refusal(lambda: w.issue(it, who="ada", context_id=draft))
    assert code.encode() == code_draft.encode() == absent.encode()
    assert w.count() == before  # nothing was written by any refusal


def test_plain_subject_still_works(world: World) -> None:
    w = world
    x = w.record("awp.IWP", "OPEN-2")
    plain = w.template()
    made = w.submit("uma", plain, subject_id=x, answers=[answer("topic", "fine")])
    assert w.submission(str(made.stream_id))["subject_id"] == x
    it = w.intake_template()
    _code, code_id = w.issue(it, who="ada", context_id=x)
    assert code_id


def test_other_link_columns_refuse_a_submission(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Permit ``for_record_id``, isolation ``point_record_id``, inspection ``subject_id``, and the
    QR target (no scan-card provider for a submission) answer the absent id's text."""
    w = world
    plain = w.template()
    sub = str(w.submit("dora", plain, answers=[answer("topic", "s")]).stream_id)
    ghost = new_ulid()
    scope = SCOPE

    def permit(record: str) -> Any:
        cmd = RequestPermit(
            actor="user:dora", source="test", scope=scope, permit_type="general",
            for_record_id=record, area="A", location_text="L", work_description="W",
            holder="H", needed_from="2026-01-01", needed_until="2026-01-02",
        )  # fmt: skip
        return lambda: _run_as_dora(w, handle_request_permit, cmd)

    def isolation(record: str) -> Any:
        cmd = ApplyIsolation(
            actor="user:dora", source="test", scope=scope, point_text="P", energy="electrical",
            method="m", lock_number="1", tag_number="2", point_record_id=record,
        )  # fmt: skip
        return lambda: _run_as_dora(w, handle_apply_isolation, cmd)

    def inspection(record: str) -> Any:
        cmd = PlanInspection(
            actor="user:dora", source="test", scope=scope, title="T", subject_id=record,
            point="hold",
        )  # fmt: skip
        return lambda: _run_as_dora(w, handle_plan_inspection, cmd)

    for make in (permit, isolation, inspection):
        assert _refusal(make(sub)).encode() == _refusal(make(ghost)).encode() == UNKNOWN.encode()

    def scan(record: str) -> Any:
        def run() -> Any:
            with open_uow(w.db) as uow:
                cmd = IssueScanCode(actor="user:ada", source="test", scope=scope, target_id=record)
                with cf.system_view():
                    return service.issue(uow, cmd)

        return run

    real = resolver.value_of

    def value_of(conn: Any, key: str, **kwargs: Any) -> Any:
        return BASE if key == service.BASE_URL else real(conn, key, **kwargs)

    monkeypatch.setattr(service, "value_of", value_of)
    # the installed scan-card providers (awp, permits, quality) are the real ones: none for a form
    assert _refusal(scan(sub)).encode() == _refusal(scan(ghost)).encode() == UNKNOWN.encode()


def test_constraint_refuses_a_submission_subject(world: World) -> None:
    """A constraint's ``subject_id`` is a chain column: a submission is refused with the words an
    absent subject gets, writing nothing; a plain record still takes one."""
    w = world
    x = w.record("awp.IWP", "OPEN-3")
    privileged = w.template(answer_class="privileged")
    s1 = str(
        _as_system(
            w, "dora", "SubmitForm", template_id=privileged, answers=[answer("topic", "SECRET")]
        ).stream_id
    )

    def raise_on(record: str) -> Any:
        cmd = RaiseConstraint(
            actor="user:dora", source="test", scope=SCOPE, subject=record, phase="start",
            severity="advisory", category="other", owner="user:dora", description="about it",
        )  # fmt: skip
        return lambda: _run_as_dora(w, handle_raise_constraint, cmd)

    before = w.count()
    refused = _refusal(raise_on(s1))
    absent_id = new_ulid()
    assert (
        refused.replace(s1, "ID").encode()
        == _refusal(raise_on(absent_id)).replace(absent_id, "ID").encode()
    )
    assert w.count() == before
    assert raise_on(x)() is not None
