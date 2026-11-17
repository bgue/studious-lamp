"""The intake queue's read views (P2-FORMS I03): codes, items, claims, answers, secrets rule."""

from __future__ import annotations

import ast
import dataclasses
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from forms_world import MARKER, SCOPE, World, answer, intake_body
from sqlalchemy import event
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_core.util import new_ulid
from tl_mod_forms import intake_views as views
from tl_mod_forms.intake_views import CodeRow, ItemRow, Page

KNOWN_CODE = "5e6f7a8b" * 8  # a 64-hex code hash the test issues with; it must never be read back
OTHER_SCOPE = "project:P999"


def read(world: World, fn: Callable[..., Any], *args: Any, scope: str = SCOPE, **kw: Any) -> Any:
    with open_uow(world.db, readonly=True) as uow:
        return fn(uow.conn(), scope, *args, **kw)


def accept(world: World, item: str) -> None:
    world.call(
        "ada",
        "AcceptIntakeItem",
        item_id=item,
        command_type="SubmitForm",
        command_args={"template_id": world.template(), "answers": [answer("topic", "Ladders")]},
    )


def reject(world: World, item: str, reason: str = "spam") -> None:
    world.call("bea", "RejectIntakeItem", item_id=item, reason=reason)


def ids(rows: list[Any]) -> set[str]:
    return {r.id for r in rows}


# --- codes -------------------------------------------------------------------------------------


def test_code_list_counts_pending_items_and_filters_by_state(world: World) -> None:
    tpl = world.intake_template()
    busy = world.stage_code(tpl)
    quiet = world.stage_code(tpl)
    items = [world.stage_item(busy) for _ in range(3)]
    reject(world, items[0])
    world.call("ada", "RevokeIntakeCode", code_id=quiet, reason="withdrawn")
    page = read(world, views.code_list)
    assert isinstance(page, Page) and page.total == 2
    by_id = {r.id: r for r in page.rows}
    assert by_id[busy].pending == 2 and by_id[quiet].pending == 0
    assert by_id[busy].state == "Active" and by_id[quiet].state == "Revoked"
    assert by_id[quiet].revoked_by == "user:ada"
    active = read(world, views.code_list, state="Active")
    assert [r.id for r in active.rows] == [busy] and active.total == 1
    revoked = read(world, views.code_list, state="Revoked")
    assert [r.id for r in revoked.rows] == [quiet]


def test_code_list_clamps_limit_and_pages_by_offset(world: World) -> None:
    tpl = world.intake_template()
    codes = [world.stage_code(tpl) for _ in range(3)]
    everything = read(world, views.code_list)
    assert everything.total == 3 and len(everything.rows) == 3
    assert len(read(world, views.code_list, limit=0).rows) == 1  # clamped up to 1
    assert len(read(world, views.code_list, limit=10_000).rows) == 3  # clamped down, not an error
    second = read(world, views.code_list, limit=1, offset=1)
    assert [r.id for r in second.rows] == [everything.rows[1].id] and second.total == 3
    past = read(world, views.code_list, limit=2, offset=10)
    assert past.rows == [] and past.total == 3
    assert set(codes) == {r.id for r in everything.rows}


def test_code_list_refuses_an_unknown_state(world: World) -> None:
    with pytest.raises(ValueError, match="^unknown state$"):
        read(world, views.code_list, state="Sleeping")


# --- items -------------------------------------------------------------------------------------


def test_item_list_is_oldest_first_and_filters_by_state_and_code(world: World) -> None:
    tpl = world.intake_template()
    first = world.stage_code(tpl)
    second = world.stage_code(tpl)
    staged = []
    for code in (first, second, first):
        staged.append(world.stage_item(code))
        time.sleep(0.002)  # ULIDs of one millisecond may not sort: keep the creation order exact
    page = read(world, views.item_list)
    assert [r.id for r in page.rows] == staged and page.total == 3
    reject(world, staged[1])
    assert ids(read(world, views.item_list, state="Rejected").rows) == {staged[1]}
    assert ids(read(world, views.item_list, state="Pending").rows) == {staged[0], staged[2]}
    assert ids(read(world, views.item_list, state="Accepted").rows) == set()
    by_code = read(world, views.item_list, code_id=first)
    assert [r.id for r in by_code.rows] == [staged[0], staged[2]] and by_code.total == 2
    assert read(world, views.item_list, limit=1, offset=2).rows[0].id == staged[2]


def test_item_list_refuses_an_unknown_state(world: World) -> None:
    with pytest.raises(ValueError, match="^unknown state$"):
        read(world, views.item_list, state="Active")  # a code state, not an item state


def test_item_detail_and_pending_count(world: World) -> None:
    tpl = world.intake_template()
    code = world.stage_code(tpl)
    item = world.stage_item(code)
    other = world.stage_item(code)
    row = read(world, views.item_detail, item)
    assert isinstance(row, ItemRow)
    assert (row.state, row.code_id, row.template_id) == ("Pending", code, tpl)
    assert row.body_bytes == len(intake_body().encode()) and row.purged_at is None
    assert read(world, views.item_detail, new_ulid()) is None
    assert read(world, views.pending_count) == 2
    reject(world, other)
    assert read(world, views.pending_count) == 1


def test_an_accepted_item_shows_name_and_company_and_never_the_phone(world: World) -> None:
    tpl = world.intake_template()
    code = world.stage_code(tpl)
    item = world.stage_item(code, intake_body(phone="555-0199"))
    accept(world, item)
    row = read(world, views.item_detail, item)
    assert (row.state, row.accepted_as, row.accepted_by) == ("Accepted", "SubmitForm", "user:ada")
    assert (row.claim_name, row.claim_company) == ("Sam Smith", "Acme Scaffolding")
    assert row.purged_at is not None
    listed = read(world, views.item_list)
    assert "555" not in repr(row) and "555" not in repr(listed)
    assert "555" not in repr(read(world, views.code_list))


def test_a_claim_with_a_missing_key_gives_none_for_that_key(world: World) -> None:
    tpl = world.intake_template()
    code = world.stage_code(tpl)
    no_company = world.stage_item(code, intake_body(company=None))
    no_claim = world.stage_item(code, intake_body(name=None, company=None))
    accept(world, no_company)
    accept(world, no_claim)
    assert read(world, views.item_detail, no_company).claim_company is None
    assert read(world, views.item_detail, no_company).claim_name == "Sam Smith"
    row = read(world, views.item_detail, no_claim)
    assert (row.claim_name, row.claim_company) == (None, None)


def test_a_rejected_item_shows_its_reason_and_stays_listed(world: World) -> None:
    tpl = world.intake_template()
    item = world.stage_item(world.stage_code(tpl))
    reject(world, item, "duplicate")
    row = read(world, views.item_detail, item)
    assert (row.state, row.rejected_reason, row.rejected_by) == (
        "Rejected",
        "duplicate",
        "user:bea",
    )
    assert ids(read(world, views.item_list).rows) == {item}


# --- answers -----------------------------------------------------------------------------------


def test_item_answers_of_a_pending_item_and_none_for_the_rest(world: World) -> None:
    tpl = world.intake_template()
    code = world.stage_code(tpl)
    pending = world.stage_item(code, intake_body(topic="Need a ladder"))
    answers = read(world, views.item_answers, pending)
    assert [a["q"] for a in answers] == ["topic", "claim_name", "claim_company", "claim_phone"]
    assert answers[0]["value"] == "Need a ladder"
    accepted = world.stage_item(code)
    accept(world, accepted)
    assert read(world, views.item_answers, accepted) is None  # the body row is deleted at accept
    kept = world.stage_item(code)
    reject(world, kept)
    assert world.body_rows(kept) == 1
    assert read(world, views.item_answers, kept) is None  # Rejected, though its body is kept
    assert read(world, views.item_answers, new_ulid()) is None
    assert read(world, views.item_answers, pending, scope=OTHER_SCOPE) is None


def test_an_unreadable_body_gives_no_answers(world: World) -> None:
    code = world.stage_code(world.intake_template())
    not_json = world.stage_item(code, body="not json {")
    no_answers = world.stage_item(code, body='{"other": 1}')
    assert read(world, views.item_answers, not_json) is None
    assert read(world, views.item_answers, no_answers) is None


def test_a_list_runs_at_most_two_statements(world: World) -> None:
    tpl = world.intake_template()
    for _ in range(2):
        world.stage_item(world.stage_code(tpl))
    statements: list[str] = []

    def count(*args: Any) -> None:
        statements.append(str(args[2]))

    with open_uow(world.db, readonly=True) as uow:
        engine = uow.conn().engine
        event.listen(engine, "before_cursor_execute", count)
        try:
            page = views.code_list(uow.conn(), SCOPE)
        finally:
            event.remove(engine, "before_cursor_execute", count)
    assert len(page.rows) == 2 and all(r.pending == 1 for r in page.rows)
    assert len(statements) == 2


# --- secrets -----------------------------------------------------------------------------------


def test_the_row_types_have_no_secret_fields() -> None:
    for kind in (CodeRow, ItemRow, Page):
        names = {f.name for f in dataclasses.fields(kind)}
        assert names.isdisjoint({"code_hash", "body_mac", "salt", "body"}), kind.__name__


def test_a_known_hash_and_a_staged_body_marker_appear_in_no_read(world: World) -> None:
    tpl = world.intake_template()
    issued = world.call(
        "ada",
        "IssueIntakeCode",
        code_hash=KNOWN_CODE,
        template_id=tpl,
        heading="Scaffold request",
        controller_role="controller",
        expires_on=world.days_from_now(30),
    )
    code = str(issued.stream_id)
    item = world.stage_item(code, intake_body(topic=MARKER))
    accept(world, world.stage_item(code))
    seen = [
        repr(read(world, views.code_list)),
        repr(read(world, views.code_list, state="Active")),
        repr(read(world, views.item_list)),
        repr(read(world, views.item_list, code_id=code)),
        repr(read(world, views.item_detail, item)),
        repr(read(world, views.item_detail, item, viewer=cf.LOWEST)),
    ]
    assert read(world, views.item_answers, item)[0]["value"] == MARKER  # the one place it is read
    for text_seen in seen:
        assert KNOWN_CODE not in text_seen and MARKER not in text_seen
        assert "cd" * 32 not in text_seen  # the stored body MAC
    with pytest.raises(ValueError) as caught:
        read(world, views.code_list, state=KNOWN_CODE)
    assert KNOWN_CODE not in str(caught.value) and MARKER not in str(caught.value)


def test_the_module_source_has_no_star_select_and_no_secret_column() -> None:
    source = Path(views.__file__).read_text(encoding="utf-8")
    assert "SELECT *" not in source
    assert "code_hash" not in source
    assert "body_mac" not in source


def test_item_answers_is_the_only_function_that_names_the_body_table() -> None:
    tree = ast.parse(Path(views.__file__).read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or node.name == "item_answers":
            continue
        names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
        literals = {str(n.value) for n in ast.walk(node) if isinstance(n, ast.Constant)}
        assert "INTAKE_BODY_TABLE" not in names, node.name
        assert not any("forms_intake_body" in lit for lit in literals), node.name
    item_answers = next(
        n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "item_answers"
    )
    assert "INTAKE_BODY_TABLE" in {n.id for n in ast.walk(item_answers) if isinstance(n, ast.Name)}
