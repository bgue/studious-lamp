"""ReferenceTray, NavHistory and the command list (P0-I3; brief 7.2, 7.5)."""

from __future__ import annotations

from tl_tui.commands import APP_COMMANDS, command_by_id
from tl_tui.navigation import NavHistory
from tl_tui.tray import ReferenceTray, TrayItem

P = "project:P123"


def item(n: int) -> TrayItem:
    return TrayItem(record_id=f"id{n}", key=f"K-{n}", type="core.Record", title=f"title {n}")


def test_tray_item_from_a_record_envelope() -> None:
    found = TrayItem.from_record({"id": "i1", "key": "K-1", "type": "core.Record", "title": "t"})
    assert found == TrayItem("i1", "K-1", "core.Record", "t")
    keyless = TrayItem.from_record({"id": "i2", "key": None, "type": None, "title": None})
    assert (keyless.key, keyless.type, keyless.title) == ("i2", "", "")


def test_add_keeps_order_and_refuses_duplicates() -> None:
    tray = ReferenceTray()
    assert tray.add(item(1)) is True
    assert tray.add(item(2)) is True
    assert tray.add(item(1)) is False
    assert [i.key for i in tray.items] == ["K-1", "K-2"]
    assert len(tray) == 2
    assert tray.contains("id1") and not tray.contains("id9")


def test_new_items_are_checked_and_toggle_flips() -> None:
    tray = ReferenceTray()
    tray.add(item(1))
    tray.add(item(2))
    assert [i.key for i in tray.checked_items()] == ["K-1", "K-2"]
    tray.toggle("id1")
    assert not tray.is_checked("id1") and tray.is_checked("id2")
    assert [i.key for i in tray.checked_items()] == ["K-2"]
    tray.toggle("id1")
    assert tray.is_checked("id1")
    tray.toggle("nope")  # ignored
    assert len(tray) == 2


def test_remove_and_clear() -> None:
    tray = ReferenceTray()
    for n in (1, 2, 3):
        tray.add(item(n))
    tray.toggle("id2")
    tray.remove("id2")
    assert [i.key for i in tray.items] == ["K-1", "K-3"]
    tray.add(item(2))  # comes back checked
    assert tray.is_checked("id2")
    tray.clear()
    assert len(tray) == 0 and tray.checked_items() == []


def test_the_items_property_is_a_copy() -> None:
    tray = ReferenceTray()
    tray.add(item(1))
    tray.items.clear()
    assert len(tray) == 1


def test_history_walks_back_and_forward() -> None:
    history = NavHistory()
    assert history.current is None and not history.can_back and not history.can_forward
    assert history.back() is None and history.forward() is None
    for key in ("A", "B", "C"):
        history.visit(P, key)
    assert history.current == (P, "C")
    assert history.back() == (P, "B")
    assert history.back() == (P, "A")
    assert history.back() is None
    assert history.can_forward
    assert history.forward() == (P, "B")
    assert history.current == (P, "B")


def test_visiting_drops_the_forward_entries_and_ignores_the_current_one() -> None:
    history = NavHistory()
    for key in ("A", "B", "C"):
        history.visit(P, key)
    history.back()
    history.visit(P, "B")  # already current: nothing changes
    assert history.can_forward
    history.visit(P, "X")
    assert not history.can_forward
    assert history.back() == (P, "B")
    assert history.forward() == (P, "X")


def test_trail_is_a_breadcrumb_of_the_path_taken() -> None:
    history = NavHistory()
    assert history.trail() == ""
    for key in ("A", "B", "C", "D", "E"):
        history.visit(P, key)
    assert history.trail() == "… › B › C › D › E"
    assert history.trail(limit=10) == "A › B › C › D › E"
    history.back()
    history.back()
    assert history.trail() == "A › B › C"


def test_app_commands_have_unique_ids_and_actions() -> None:
    ids = [c.id for c in APP_COMMANDS]
    assert len(ids) == len(set(ids))
    assert command_by_id("link") is not None
    assert command_by_id("nope") is None
    assert all(c.label and c.action for c in APP_COMMANDS)
