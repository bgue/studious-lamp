"""``tl_tui.action_ui``: the terminal's action table without the terminal (P2-WEB1-S2).

The web client reads the same table, so a fresh ``import tl_tui.action_ui`` must load no ``textual``
and no other ``tl_tui`` module, the names that moved out of ``log_actions`` and
``widgets.action_form`` must still be the same objects through those modules, and the table must
keep its keys.
"""

from __future__ import annotations

import subprocess
import sys
from typing import Any

from tl_tui import action_ui, log_actions
from tl_tui.action_ui import ACTION_UI, ENVELOPE
from tl_tui.widgets import action_form

#: The sorted ``ACTION_UI`` keys when the table moved out of the terminal's widgets.
ACTION_UI_KEYS = [
    "AnswerTechnical", "AssessCommercial", "CloseCommercial", "CloseCorrespondence",
    "CloseTechnical", "EscalateTechnical", "IssueCommercial", "IssueCorrespondence",
    "IssueTechnical", "ReclassifyTag", "ReferCommercialToLegal", "ReissueTechnical", "RenameTag",
    "ReturnCommercial", "ReturnTechnical", "ReviewCommercial", "ReviewTechnicalAnswer",
    "SubmitCommercial", "SubmitTechnical", "VoidCorrespondence", "VoidDraft",
]  # fmt: skip


def test_a_fresh_import_loads_no_textual_and_no_other_tl_tui_module() -> None:
    code = (
        "import sys, tl_tui.action_ui\n"
        "bad = sorted(m for m in sys.modules if m.split('.')[0] == 'textual'"
        " or (m.startswith('tl_tui.') and m != 'tl_tui.action_ui'))\n"
        "print(bad)\nsys.exit(1 if bad else 0)"
    )
    done = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr


def test_the_moved_names_are_the_same_objects_through_the_old_modules() -> None:
    assert log_actions.ACTION_UI is action_ui.ACTION_UI
    assert log_actions.ActionUi is action_ui.ActionUi
    assert action_form.FormField is action_ui.FormField
    assert log_actions.FormField is action_ui.FormField
    assert log_actions.ENVELOPE is action_ui.ENVELOPE
    assert log_actions.stamp is action_ui.stamp
    assert log_actions.without_keys is action_ui.without_keys


def test_the_table_has_the_keys_it_had_when_it_moved() -> None:
    assert sorted(ACTION_UI) == ACTION_UI_KEYS


def test_a_field_less_entry_builds_a_command_on_its_stream_with_the_envelope() -> None:
    plain = {name: ui for name, ui in ACTION_UI.items() if not ui.fields}
    assert plain
    for name, ui in plain.items():
        cmd: Any = ui.build({}, "rec-1", 3)
        assert cmd.stream_id == "rec-1", name
        assert (cmd.actor, cmd.source, cmd.scope) == tuple(ENVELOPE.values()), name
