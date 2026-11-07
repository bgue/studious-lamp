# ruff: noqa: E501  (the RFI and letter texts are long lines of data)
"""correspondence section: parties, 36 RFIs and technical queries, and the letters around them.

RFIs and technical queries go through the real flow (raise, submit, issue, answer, review, close)
and end in mixed states: drafts, in review, waiting (some past the day they were needed), answered,
accepted, rejected and closed. The letters are logged, triaged, answered and issued. At the fixed
"today" the clock sweep records the expiries, so overdue items show as overdue.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import timedelta

from tl_mod_correspondence.handlers.clocks import SweepClocks, handle_sweep_clocks
from tl_mod_correspondence.handlers.issue import IssueCorrespondence, handle_issue_correspondence
from tl_mod_correspondence.handlers.items import (
    ReceiveCorrespondence,
    handle_receive_correspondence,
)
from tl_mod_correspondence.handlers.parties import RegisterParty, handle_register_party
from tl_mod_correspondence.handlers.responses import (
    CloseCorrespondence,
    DraftCorrespondence,
    handle_close_correspondence,
    handle_draft_correspondence,
)
from tl_mod_correspondence.handlers.technical import (
    RaiseTechnical,
    SubmitTechnical,
    handle_raise_technical,
    handle_submit_technical,
)
from tl_mod_correspondence.handlers.technical_flow import (
    AnswerTechnical,
    CloseTechnical,
    IssueTechnical,
    ReviewTechnicalAnswer,
    handle_answer_technical,
    handle_close_technical,
    handle_issue_technical,
    handle_review_technical_answer,
)
from tl_mod_correspondence.handlers.triage import ConfirmTriage, handle_confirm_triage

from dev.seed.demo_project.pdf import make_pdf
from dev.seed.demo_project.registry import register
from dev.seed.demo_project.world import START, TODAY, World

AUTHOR = "odoyle"
ENGINEER = "lhartmann"
CONTROLLER = "ipetrov"

PARTIES = (
    (
        "CLIENT",
        "North Refinery Company",
        "client",
        "northrefinery.example",
        (
            ("Grace Whitfield", "grace.whitfield", "Client representative", True),
            ("Jonas Eklund", "jonas.eklund", "Operations manager", False),
        ),
    ),
    (
        "DESIGN",
        "Halden Engineering",
        "engineer",
        "haldeneng.example",
        (
            ("Ruth Calloway", "ruth.calloway", "Lead process engineer", True),
            ("Samir Aziz", "samir.aziz", "Piping lead", False),
        ),
    ),
    (
        "MERIDIAN",
        "Meridian Mechanical",
        "contractor",
        "meridian-mech.example",
        (("Dale Kowalski", "dale.kowalski", "Site manager", True),),
    ),
    (
        "NORTHLINE",
        "Northline Civil",
        "contractor",
        "northline-civil.example",
        (("Mei Tanaka", "mei.tanaka", "Site manager", True),),
    ),
    (
        "BAYFIELD",
        "Bayfield Electrical",
        "contractor",
        "bayfield-elec.example",
        (("Rosa Delgado", "rosa.delgado", "Project manager", True),),
    ),
    (
        "KESTREL",
        "Kestrel Insulation",
        "subcontractor",
        "kestrel-ins.example",
        (("Piotr Zielinski", "piotr.zielinski", "Supervisor", True),),
    ),
)

RFI_TOPICS = (
    (
        "Support interference at the pipe rack",
        "The isometric for line {line} shows a support that clashes with the cable tray on rack level 2. Confirm the support location or the tray route.",
    ),
    (
        "Nozzle orientation of {tag}",
        "The vessel datasheet and the general arrangement give different nozzle orientations for {tag}. Which one governs?",
    ),
    (
        "Insulation thickness on line {line}",
        "The piping specification and the P&ID note differ on the insulation thickness for personnel protection. Confirm the thickness.",
    ),
    (
        "Tie-in point at the live plant",
        "The tie-in shown on {doc} falls inside the hot-work exclusion zone. Confirm an alternative tie-in point or a shutdown window.",
    ),
    (
        "Foundation level for {tag}",
        "The civil drawing shows the top of concrete at a different level to the equipment datasheet for {tag}. Confirm the level.",
    ),
    (
        "Instrument range of {tag}",
        "The loop diagram and the instrument datasheet give different calibrated ranges for {tag}. Confirm the range.",
    ),
    (
        "Material change on line {line}",
        "The line list shows carbon steel, the isometric shows low-temperature carbon steel. Confirm the material.",
    ),
    (
        "Valve type for {tag}",
        "The P&ID shows a ball valve for {tag}, the material take-off a gate valve. Confirm the valve type.",
    ),
    (
        "Cable route to the substation",
        "The cable schedule routes through the tank farm bund. Confirm that the route may cross the bund wall.",
    ),
    (
        "Hydrotest pressure on line {line}",
        "The test pack shows a test pressure above the flange rating of the connected equipment. Confirm the test pressure.",
    ),
    (
        "Platform access for {tag}",
        "No access platform is shown for {tag} on the general arrangement. Confirm whether one is required.",
    ),
    (
        "Painting system for the pipe rack",
        "The painting specification lists two systems for galvanised steel. Confirm which one applies.",
    ),
)
ANSWERS = (
    "Support relocated 400 mm east; the isometric is reissued at the next revision.",
    "The general arrangement governs; the datasheet is corrected.",
    "Confirmed as marked on the P&ID; the specification is revised.",
    "Alternative tie-in agreed with operations; see the attached sketch.",
    "Top of concrete as the civil drawing; the datasheet is corrected.",
    "Range as the instrument datasheet; the loop diagram is revised.",
    "Low-temperature carbon steel applies; the line list is corrected.",
    "Gate valve as the take-off; the P&ID is revised.",
    "Route accepted with a sleeve through the bund wall, to be sealed after install.",
    "Test pressure reduced to the flange rating; the test pack is revised.",
)
REJECT_NOTE = (
    "The answer does not name the revision of the drawing that governs; please be specific."
)
LETTERS = (
    (
        "Revised programme for the tie-in shutdown",
        "Please confirm the revised programme for the shutdown window of area 600.",
    ),
    (
        "Request for the as-built piping records",
        "Please send the as-built isometrics for the lines already in service.",
    ),
    (
        "Notice of delay: delivery of structural steel",
        "Delivery of the rack steel is delayed by two weeks.",
    ),
    (
        "Confirmation of the hot work permit procedure",
        "Please confirm the hot work permit procedure for the live plant tie-ins.",
    ),
    (
        "Access to the tank farm bund",
        "Please arrange access to the bund for the foundation survey.",
    ),
    (
        "Submission of the welding procedure specifications",
        "The welding procedure specifications are enclosed for approval.",
    ),
    (
        "Request for a site meeting on the cooling water headers",
        "We ask for a meeting to settle the routing of the cooling water headers.",
    ),
    ("Weekly progress report", "The progress report for the week is enclosed."),
    (
        "Quality inspection hold points",
        "Please confirm the hold points for the piping fabrication.",
    ),
    (
        "Temporary power for the substation works",
        "Please confirm the temporary power supply for the substation works.",
    ),
    (
        "Early delivery of the control valves",
        "The manufacturer offers early delivery of the control valves.",
    ),
    (
        "Insulation material submittal",
        "The insulation material submittal is enclosed for approval.",
    ),
)
MINUTES = (
    ("Minutes of the coordination meeting", "minutes"),
    ("Site notice: road closure at gate 2", "notification"),
    ("Internal memo: reporting lines on site", "memo"),
    ("Minutes of the safety review", "minutes"),
)
DISCIPLINES = ("PIP", "STR", "CIV", "ELE", "INS", "MEC")


@dataclass(frozen=True)
class Plan:
    subtype: str
    outcome: str  # draft review overdue waiting answered accepted rejected closed


OUTCOMES = (
    ["draft"] * 3
    + ["review"] * 2
    + ["overdue"] * 9
    + ["waiting"] * 5
    + ["answered"] * 4
    + ["accepted"] * 9
    + ["rejected"] * 2
    + ["closed"] * 2
)


def names_from(
    world: World, record_type: str, rng: random.Random, fallback: list[str], n: int
) -> list[str]:
    found = [
        r["key"]
        for r in world.rows(
            "SELECT key FROM cur_core_record WHERE type = :t AND voided = :v ORDER BY key",
            t=record_type,
            v=False,
        )
    ]
    pool = found or fallback
    return [rng.choice(pool) for _ in range(n)]


def build(world: World, rng: random.Random) -> None:
    parties = register_parties(world)
    tags = names_from(world, "engineering.Tag", rng, ["200-P-1001"], 64)
    docs = names_from(world, "documents.Document", rng, ["P200-200-PID-0001"], 64)
    lines = [
        t for t in names_from(world, "engineering.Tag", rng, ['6"-P-200-1001-A1A'], 400) if '"' in t
    ][:16] or ['6"-P-200-1001-A1A']
    rfis(world, rng, parties, tags, docs, lines)
    letters(world, rng, parties)
    with world.today():
        world.run(handle_sweep_clocks, SweepClocks, by=CONTROLLER)


def register_parties(world: World) -> dict[str, str]:
    ids: dict[str, str] = {}
    with world.on(START):
        for code, name, role, domain, contacts in PARTIES:
            made = world.run(
                handle_register_party,
                RegisterParty,
                by=CONTROLLER,
                code=code,
                name=name,
                project_role=role,
                email_domains=[domain],
                contacts=[
                    {
                        "name": who,
                        "email": f"{mail}@{domain}",
                        "title": title,
                        "is_authorised": auth,
                    }
                    for who, mail, title, auth in contacts
                ],
            )
            ids[code] = made.stream_id
    return ids


def recipient(parties: dict[str, str], code: str) -> dict[str, str]:
    row = next(p for p in PARTIES if p[0] == code)
    return {"name": row[4][0][0], "email": f"{row[4][0][1]}@{row[3]}", "party_id": parties[code]}


def rfis(
    world: World,
    rng: random.Random,
    parties: dict[str, str],
    tags: list[str],
    docs: list[str],
    lines: list[str],
) -> None:
    outcomes = list(OUTCOMES)
    rng.shuffle(outcomes)
    for position, outcome in enumerate(outcomes):
        topic, question = RFI_TOPICS[position % len(RFI_TOPICS)]
        values = {
            "tag": tags[position % len(tags)],
            "doc": docs[position % len(docs)],
            "line": lines[position % len(lines)],
        }
        subject, question = topic.format(**values), question.format(**values)
        subtype = "tq" if position % 5 == 4 else "rfi"
        to = recipient(parties, rng.choice(("DESIGN", "DESIGN", "CLIENT")))
        # the day the item is raised, counted back from today by the outcome it ends in
        if outcome in ("draft", "review"):
            raised = TODAY - timedelta(days=rng.randint(1, 6))
        elif outcome == "overdue":
            raised = TODAY - timedelta(days=rng.randint(20, 40))
        elif outcome == "waiting":
            raised = TODAY - timedelta(days=rng.randint(2, 5))
        else:
            raised = TODAY - timedelta(days=rng.randint(30, 60))
        issued = raised + timedelta(days=2)
        if outcome == "overdue":
            needed = issued + timedelta(days=rng.randint(7, 12))
        elif outcome == "waiting":
            needed = TODAY + timedelta(days=rng.randint(3, 12))
        else:
            needed = max(issued + timedelta(days=10), raised + timedelta(days=12))
        refs = [{"record_id": rid} for rid in references(world, values, position)]
        with world.on(raised):
            made = world.run(
                handle_raise_technical,
                RaiseTechnical,
                by=AUTHOR,
                subtype=subtype,
                subject=subject,
                question=question,
                discipline=rng.choice(DISCIPLINES),
                required_by=needed.isoformat(),
                potential_cost_impact=rng.choice(("no", "no", "yes", "unknown")),
                potential_schedule_impact=rng.choice(("no", "yes", "unknown")),
                to=[to],
                references=refs,
            )
        item = made.stream_id
        if outcome == "draft":
            continue
        with world.on(raised + timedelta(days=1)):
            world.run(handle_submit_technical, SubmitTechnical, by=AUTHOR, stream_id=item)
        if outcome == "review":
            continue
        with world.on(issued):
            world.run(handle_issue_technical, IssueTechnical, by=CONTROLLER, stream_id=item)
        if outcome in ("overdue", "waiting"):
            continue
        if outcome == "closed":
            with world.on(min(issued + timedelta(days=rng.randint(5, 12)), TODAY)):
                world.run(
                    handle_close_technical,
                    CloseTechnical,
                    by=AUTHOR,
                    stream_id=item,
                    reason="Overtaken by the design change; no answer needed",
                )
            continue
        answered = min(issued + timedelta(days=rng.randint(3, 9)), TODAY - timedelta(days=1))
        with world.on(answered):
            world.run(
                handle_answer_technical,
                AnswerTechnical,
                by=ENGINEER,
                stream_id=item,
                answer=ANSWERS[position % len(ANSWERS)],
                cost_impact=rng.choice(("no", "no", "yes")),
                schedule_impact=rng.choice(("no", "no", "yes")),
            )
        if outcome == "answered":
            continue
        with world.on(min(answered + timedelta(days=1), TODAY)):
            if outcome == "accepted":
                world.run(
                    handle_review_technical_answer,
                    ReviewTechnicalAnswer,
                    by=AUTHOR,
                    stream_id=item,
                    decision="accepted",
                )
            else:
                world.run(
                    handle_review_technical_answer,
                    ReviewTechnicalAnswer,
                    by=AUTHOR,
                    stream_id=item,
                    decision="rejected",
                    note=REJECT_NOTE,
                )


def references(world: World, values: dict[str, str], position: int) -> list[str]:
    """The ids of the tag and the document an RFI names, when they are in the ledger."""
    found: list[str] = []
    for key in (values["tag"], values["doc"]):
        rows = world.rows(
            "SELECT id FROM cur_core_record WHERE scope = 'project:P200' AND key = :k", k=key
        )
        if rows and position % 3 != 2:
            found.append(str(rows[0]["id"]))
    return found


def letters(world: World, rng: random.Random, parties: dict[str, str]) -> None:
    senders = ("CLIENT", "DESIGN", "MERIDIAN", "NORTHLINE", "BAYFIELD", "KESTREL")
    incoming: list[tuple[str, str]] = []
    for position, (subject, body) in enumerate(LETTERS):
        code = senders[position % len(senders)]
        row = next(p for p in PARTIES if p[0] == code)
        day = TODAY - timedelta(days=rng.randint(4, 55))
        with world.on(day):
            made = world.run(
                handle_receive_correspondence,
                ReceiveCorrespondence,
                by=CONTROLLER,
                subject=subject,
                body=body,
                from_party_id=parties[code],
                from_name=row[4][0][0],
                received_on=day.isoformat(),
                external_ref=f"{code[:3]}-L-{position + 101}",
            )
            world.upload(
                made.stream_id,
                slot="original",
                filename=f"{code.lower()}-letter-{position + 101}.pdf",
                data=make_pdf(subject, [row[1], body, f"Received {day.isoformat()}"]),
                by=CONTROLLER,
            )
        if position % 4 == 3:
            continue  # logged, not yet triaged
        due = day + timedelta(days=rng.choice((7, 14, 21)))
        with world.on(day + timedelta(days=1)):
            world.run(
                handle_confirm_triage,
                ConfirmTriage,
                by=CONTROLLER,
                stream_id=made.stream_id,
                domain="general",
                subtype="letter",
                response_required=position % 3 != 2,
                response_due=due.isoformat() if position % 3 != 2 else None,
                start_clocks=False,
            )
        incoming.append((made.stream_id, subject))
    # we answer some letters: a drafted letter that responds; issuing it marks the letter answered
    for position, (letter_id, subject) in enumerate(incoming[:6]):
        day = TODAY - timedelta(days=rng.randint(2, 12))
        with world.on(day):
            drafted = world.run(
                handle_draft_correspondence,
                DraftCorrespondence,
                by=ENGINEER,
                subject=f"Re: {subject}",
                body="We refer to your letter and confirm the position as follows.",
                to=[recipient(parties, "CLIENT")],
                responds_to_id=letter_id,
                domain="general",
                subtype="letter",
            )
            if position == 5:
                continue  # still a draft
            world.run(
                handle_issue_correspondence,
                IssueCorrespondence,
                by=CONTROLLER,
                stream_id=drafted.stream_id,
            )
            if position < 2:  # issuing a letter that responds moved the letter to Responded
                world.run(
                    handle_close_correspondence,
                    CloseCorrespondence,
                    by=CONTROLLER,
                    stream_id=letter_id,
                )
    for position, (subject, subtype) in enumerate(MINUTES):
        day = TODAY - timedelta(days=rng.randint(3, 30))
        with world.on(day):
            made = world.run(
                handle_receive_correspondence,
                ReceiveCorrespondence,
                by=CONTROLLER,
                subject=subject,
                body="Filed for the record.",
                medium="minutes" if subtype == "minutes" else "other",
                from_name="Project team",
                received_on=day.isoformat(),
            )
        if position != 3:
            with world.on(day + timedelta(days=1)):
                world.run(
                    handle_confirm_triage,
                    ConfirmTriage,
                    by=CONTROLLER,
                    stream_id=made.stream_id,
                    domain="general",
                    subtype=subtype,
                )


register("correspondence", build)
