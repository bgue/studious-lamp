"""forms section: general form templates and submissions of P200, built through the real commands
(V3-F1a; docs/tickets/P2-FORMS/T09-demo-generator.md is the reference).

Four published templates and fifteen submissions, one unit of work per command, as the roster
people, each read through its actor's own viewer (ADR-0016). ``mokafor`` (the administrator, who
holds the controller words) drafts and publishes the templates and reviews every submission
(accepts, returns, voids); the
filling is by the foremen ``cbrooks`` and ``pnair`` and the quality inspector ``hsato``. The
reviewer is never the submitter. Three templates are the fixtures of ``schema/fixtures/forms/
templates`` (toolbox talk, pre-use equipment check, job hazard assessment: the last is
``restricted``); the fourth, a near-miss report, is defined here and is ``privileged``.

The final state of each submission is fixed by position (``FINAL``): 4 Submitted, 4 Accepted,
2 Returned, 1 Voided, 2 Draft (saved, never submitted), 1 Discarded, and the one confidential
submission (the near-miss report, Submitted, read by its author alone). The first two
submissions are saved as drafts first and then submitted from the draft. 6 toolbox talks, 5
pre-use checks, 3 hazard assessments and the near-miss report.

Dates are the project calendar: every event falls on its day through ``world.on(day)``. Answers
are valid for the template (a ``no`` with a note on two pre-use checks). Draws come from the
section's own ``rng``; nothing reads the clock.
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import yaml
from tl_adapters.db import open_uow
from tl_core.confidentiality import use_viewer, viewer_for_actor
from tl_mod_forms.commands import (
    AcceptFormSubmission,
    DiscardFormDraft,
    DraftFormTemplate,
    PublishFormTemplate,
    ReturnFormSubmission,
    SaveFormDraft,
    SubmitForm,
    VoidFormSubmission,
)
from tl_mod_forms.handlers.review import (
    handle_accept_form_submission,
    handle_return_form_submission,
    handle_void_form_submission,
)
from tl_mod_forms.handlers.submission import (
    handle_discard_form_draft,
    handle_save_form_draft,
    handle_submit_form,
)
from tl_mod_forms.handlers.template import (
    handle_draft_form_template,
    handle_publish_form_template,
)

from dev.seed.demo_project.registry import register
from dev.seed.demo_project.world import TODAY, World, actor_of

CONTROLLER = "mokafor"  # the administrator: publishes the templates; accepts, returns, voids
FILLERS = ("cbrooks", "pnair", "hsato")
COMPANY = "company"
FIXTURES = Path(__file__).resolve().parents[3] / "schema" / "fixtures" / "forms" / "templates"
TEMPLATE_FILES = ("toolbox-talk", "pre-use-check", "job-hazard-assessment")
KEYS = ("toolbox", "preuse", "jha", "nearmiss")

TALK_TOPICS = (
    "Working at height",
    "Hot work permits",
    "Lifting and rigging",
    "Slips, trips and falls",
    "Confined space entry",
    "Manual handling",
)
EQUIPMENT = (
    "Welding set WS-12",
    "Angle grinder AG-04",
    "Mobile compressor MC-02",
    "Scissor lift SL-07",
    "Pipe threading machine PT-03",
)
TASKS = (
    "Replace the strainer on the cooling water line",
    "Erect scaffold at the fractionation column",
    "Hot tap on the nitrogen header",
)
AREAS = ("Pipe rack, bay 3", "Tank farm, north side", "Substation yard")
REMARKS = ("Checked and tagged.", "Used daily on the rack.", "Returned from service yesterday.")
NEAR_MISS_PLACES = ("Pipe rack level 2",)

#: Template of each position, and its final state (see the module docstring).
PLAN: tuple[tuple[str, str], ...] = (
    ("toolbox", "Submitted"),  # 0: saved as a draft first, then submitted from it
    ("preuse", "Submitted"),  # 1: the same
    ("toolbox", "Submitted"),  # 2
    ("jha", "Submitted"),  # 3
    ("toolbox", "Accepted"),  # 4
    ("preuse", "Accepted"),  # 5
    ("toolbox", "Accepted"),  # 6
    ("jha", "Accepted"),  # 7
    ("preuse", "Returned"),  # 8
    ("toolbox", "Returned"),  # 9
    ("preuse", "Voided"),  # 10
    ("toolbox", "Draft"),  # 11
    ("preuse", "Draft"),  # 12
    ("jha", "Discarded"),  # 13
    ("nearmiss", "Submitted"),  # 14: the confidential one
)
FINAL = tuple(state for _, state in PLAN)
VIA_DRAFT = (0, 1)
NO_NOTE_PRE_USE = (5, 8)  # a guard answered `no`, with a note, on two pre-use checks


def _q(fid: str, text: str, kind: str, *, required: bool = True, **more: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": fid,
        "text": text,
        "kind": kind,
        "required": required,
        "unit": None,
        "min": None,
        "max": None,
        "choices": None,
        "fails_when": None,
        "section": None,
        "help": None,
        "visible_when": None,
    }
    base.update(more)
    return base


NEAR_MISS_FIELDS: list[dict[str, Any]] = [
    _q("what_happened", "What happened?", "text"),
    _q("where", "Where?", "text"),
    _q("injury_risk", "Could someone have been hurt?", "yes_no_na"),
    _q("action_taken", "What was done at once?", "text", required=False),
]


def _templates() -> list[dict[str, Any]]:
    """The four template bodies, in ``KEYS`` order."""
    bodies: list[dict[str, Any]] = []
    for name in TEMPLATE_FILES:
        loaded = yaml.safe_load((FIXTURES / f"{name}.yaml").read_text(encoding="utf-8"))
        bodies.append(
            {k: v for k, v in loaded.items() if k != "intake" and v is not None}  # drop nulls
        )
    bodies.append(
        {
            "title": "Near-miss report",
            "format_version": 2,
            "answer_class": "privileged",
            "fields": NEAR_MISS_FIELDS,
        }
    )
    return bodies


def _run(world: World, who: str, day: date, handler: Any, model: Any, **fields: Any) -> Any:
    """One command as ``who`` on ``day``, read through ``who``'s own viewer (ADR-0016)."""
    with open_uow(world.target, readonly=True) as uow:
        viewer = viewer_for_actor(uow.conn(), actor_of(who))
    with world.on(day), use_viewer(viewer):
        return world.run(handler, model, by=who, **fields)


def _ans(q: str, value: Any, note: str | None = None) -> dict[str, Any]:
    return {"q": q, "value": value, "note": note}


def _answers(kind: str, pos: int, rng: random.Random, day: date) -> list[dict[str, Any]]:
    """Valid answers for the template ``kind``; ``pos`` picks the text and the ``no`` cases."""
    when = day.isoformat()
    if kind == "toolbox":
        topic = TALK_TOPICS[pos % len(TALK_TOPICS)]
        picked = sorted(rng.sample(["Falls", "Lifting", "Electrical", "Hot work"], 2))
        return [
            _ans("topic", topic),
            _ans("talk_date", when),
            _ans("led_by", "Foreman"),
            _ans("hazards_covered", picked),
            _ans("ppe_checked", "yes"),
            _ans("attendees", rng.randint(4, 18)),
        ]
    if kind == "preuse":
        no = pos in NO_NOTE_PRE_USE
        return [
            _ans("equipment", EQUIPMENT[pos % len(EQUIPMENT)]),
            _ans("check_date", when),
            _ans(
                "guards_fitted", "no" if no else "yes", "Guard missing, tagged out" if no else None
            ),
            _ans("leaks", "no"),
            _ans("run_hours", rng.randint(10, 4000)),
            _ans("fit_for_use", "No" if no else "Yes"),
            _ans("remarks", REMARKS[pos % len(REMARKS)]),
        ]
    if kind == "jha":
        return [
            _ans("task", TASKS[pos % len(TASKS)]),
            _ans("work_area", AREAS[pos % len(AREAS)]),
            _ans("assess_date", when),
            _ans("hazard_type", rng.choice(["Height", "Energy", "Mechanical"])),
            _ans("controls_in_place", "yes"),
            _ans("controls_notes", "Barriers, harness points and a spotter."),
            _ans("residual_risk", rng.choice(["Low", "Medium"])),
            _ans("workers_briefed", "yes"),
        ]
    return [
        _ans("what_happened", "A pipe support clip fell from the rack."),
        _ans("where", NEAR_MISS_PLACES[0]),
        _ans("injury_risk", "yes"),
        _ans("action_taken", "Area barricaded and the clips re-checked."),
    ]


def build(world: World, rng: random.Random) -> None:
    ids: dict[str, str] = {}
    start = TODAY - timedelta(days=45)
    for key, body in zip(KEYS, _templates(), strict=True):
        made = _run(
            world, CONTROLLER, start, handle_draft_form_template, DraftFormTemplate,
            scope=COMPANY, **body,
        )  # fmt: skip
        _run(
            world, CONTROLLER, start, handle_publish_form_template, PublishFormTemplate,
            scope=COMPANY, template_id=made.stream_id,
        )  # fmt: skip
        ids[key] = str(made.stream_id)
    for pos, (kind, state) in enumerate(PLAN):
        who = FILLERS[pos % len(FILLERS)]
        day = TODAY - timedelta(days=40 - 2 * pos)
        answers = _answers(kind, pos, rng, day)
        template = ids[kind]
        if state == "Draft":
            _run(world, who, day, handle_save_form_draft, SaveFormDraft,
                 template_id=template, answers=answers[:2])  # fmt: skip
            continue
        if state == "Discarded":
            saved = _run(world, who, day, handle_save_form_draft, SaveFormDraft,
                         template_id=template, answers=answers[:3])  # fmt: skip
            _run(world, who, day, handle_discard_form_draft, DiscardFormDraft,
                 submission_id=saved.stream_id)  # fmt: skip
            continue
        if pos in VIA_DRAFT:
            saved = _run(world, who, day, handle_save_form_draft, SaveFormDraft,
                         template_id=template, answers=answers[:3])  # fmt: skip
            sent = _run(world, who, day, handle_submit_form, SubmitForm,
                        draft_id=saved.stream_id, answers=answers)  # fmt: skip
        else:
            sent = _run(world, who, day, handle_submit_form, SubmitForm,
                        template_id=template, answers=answers)  # fmt: skip
        sid = str(sent.stream_id)
        reviewed = day + timedelta(days=1)
        if state == "Accepted":
            accept = (handle_accept_form_submission, AcceptFormSubmission)
            _run(world, CONTROLLER, reviewed, *accept, submission_id=sid, note="Checked and filed.")
        elif state == "Returned":
            back = (handle_return_form_submission, ReturnFormSubmission)
            _run(
                world, CONTROLLER, reviewed, *back, submission_id=sid, note="Add the tag, resubmit."
            )
        elif state == "Voided":
            void = (handle_void_form_submission, VoidFormSubmission)
            _run(world, CONTROLLER, reviewed, *void, submission_id=sid, reason="Wrong machine.")


register("forms", build, needs=("forms.Template", "forms.Submission"))
