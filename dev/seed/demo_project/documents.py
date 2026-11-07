"""documents section: 80+ controlled documents, their revisions, supersessions and transmittals.

P&IDs, isometrics, general arrangements, datasheets and specifications, numbered
``P200-200-PID-0012``. Every revision is created, gets a small generated PDF through the file
service, is attached as a rendition and (but for a few drafts) issued; issuing a later revision
supersedes the one before it. Some documents are replaced by another one, and a few transmittals
carry issued revisions to the contractors.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta

from tl_mod_documents.handlers.documents import (
    RegisterDocument,
    SetDocumentConfidentiality,
    SupersedeDocument,
    handle_register_document,
    handle_set_document_confidentiality,
    handle_supersede_document,
)
from tl_mod_documents.handlers.renditions import AttachRendition, handle_attach_rendition
from tl_mod_documents.handlers.revisions import (
    CreateRevision,
    IssueRevision,
    handle_create_revision,
    handle_issue_revision,
)
from tl_mod_documents.handlers.transmittals import (
    CloseTransmittal,
    CreateTransmittal,
    IssueTransmittal,
    RecordTransmittalResponse,
    handle_close_transmittal,
    handle_create_transmittal,
    handle_issue_transmittal,
    handle_record_transmittal_response,
)

from dev.seed.demo_project.anchors import ANCHOR_DOCUMENTS
from dev.seed.demo_project.pdf import make_pdf
from dev.seed.demo_project.registry import register
from dev.seed.demo_project.world import START, TODAY, World

ENGINEER = "lhartmann"
CONTROLLER = "ipetrov"
DESIGNER = "Halden Engineering"

AREA_NAMES = {
    "100": "pipe rack",
    "200": "process unit",
    "300": "tank farm",
    "400": "utilities",
    "500": "substation",
    "600": "tie-ins",
}
PID_SUBJECTS = (
    "reactor feed and effluent",
    "recycle gas loop",
    "fractionator overhead",
    "fractionator bottoms",
    "hydrogen make-up",
    "cooling water supply and return",
    "steam and condensate",
    "nitrogen distribution",
    "flare and relief headers",
    "product storage",
    "tie-in to the live plant",
    "instrument air",
)
GA_SUBJECTS = (
    "plot plan",
    "equipment layout",
    "foundation layout",
    "cable tray layout",
    "rack elevation",
)
DS_SUBJECTS = (
    "centrifugal pump",
    "shell and tube exchanger",
    "pressure vessel",
    "control valve",
    "relief valve",
    "level transmitter",
    "motor",
)
SPC_SUBJECTS = (
    "piping material specification",
    "painting and insulation specification",
    "electrical installation specification",
    "welding and NDE specification",
)


@dataclass(frozen=True)
class Plan:
    doc_type: str
    count: int
    areas: tuple[str, ...]
    discipline: dict[str, str]  # area -> discipline; "*" the default


PLANS = (
    Plan("PID", 24, ("200", "200", "200", "400", "400", "100", "300", "600"), {"*": "PIP"}),
    Plan("ISO", 36, ("200", "200", "100", "100", "300", "400", "600"), {"*": "PIP"}),
    Plan(
        "GA",
        12,
        ("100", "200", "300", "400", "500", "600"),
        {"100": "STR", "200": "MEC", "300": "CIV", "400": "MEC", "500": "ELE", "600": "PIP"},
    ),
    Plan(
        "DS",
        14,
        ("200", "200", "300", "400", "500"),
        {"200": "MEC", "300": "MEC", "400": "MEC", "500": "ELE", "*": "INS"},
    ),
    Plan(
        "SPC",
        4,
        ("200", "400", "500", "600"),
        {"200": "PIP", "400": "PNT", "500": "ELE", "600": "ISL"},
    ),
)
REVISIONS = (1, 1, 1, 2, 2, 2, 2, 3, 3, 4)  # how many revisions a document gets (drawn)
TRANSMITTAL_PURPOSE = ("for_review", "for_construction", "for_information", "for_review")
CONTRACTORS = (
    ("Meridian Mechanical", "Meridian Mechanical Ltd", "docs@meridian-mech.example"),
    ("Northline Civil", "Northline Civil Ltd", "docs@northline-civil.example"),
    ("Bayfield Electrical", "Bayfield Electrical Ltd", "docs@bayfield-elec.example"),
    ("Kestrel Insulation", "Kestrel Insulation Ltd", "docs@kestrel-ins.example"),
)


@dataclass
class Doc:
    number: str
    doc_type: str
    area: str
    title: str
    id: str = ""
    issued: list[str] = None  # type: ignore[assignment]  # revision ids, issued, in order
    superseded: bool = False

    def __post_init__(self) -> None:
        self.issued = []


def title_for(rng: random.Random, doc_type: str, area: str) -> str:
    where = AREA_NAMES[area]
    if doc_type == "PID":
        return f"P&ID, {rng.choice(PID_SUBJECTS)}, {where}"
    if doc_type == "ISO":
        size = rng.choice(('2"', '3"', '4"', '6"', '8"', '12"'))
        service = rng.choice(("P", "HC", "CW", "ST", "N2", "FG"))
        return f"Isometric, line {size}-{service}-{area}-{rng.randint(1001, 1099):04d}"
    if doc_type == "GA":
        return f"General arrangement, {rng.choice(GA_SUBJECTS)}, {where}"
    if doc_type == "DS":
        return f"Datasheet, {rng.choice(DS_SUBJECTS)}, {where}"
    return f"Specification, {rng.choice(SPC_SUBJECTS)}"


def plan_documents(rng: random.Random) -> list[Doc]:
    docs: list[Doc] = []
    for plan in PLANS:
        counters: dict[str, int] = {}
        for _ in range(plan.count):
            area = rng.choice(plan.areas)
            counters[area] = counters.get(area, 0) + rng.randint(1, 3)
            number = f"P200-{area}-{plan.doc_type}-{counters[area]:04d}"
            docs.append(Doc(number, plan.doc_type, area, title_for(rng, plan.doc_type, area)))
    rng.shuffle(docs)
    return docs


def advance(day: date, rng: random.Random, low: int, high: int) -> date:
    """``day`` plus a few days, never later than the day before the project's today."""
    return min(day + timedelta(days=rng.randint(low, high)), TODAY - timedelta(days=1))


def build(world: World, rng: random.Random) -> None:
    docs = plan_documents(rng)
    plan_of = {p.doc_type: p for p in PLANS}
    span = (TODAY - START).days - 14
    for position, doc in enumerate(docs):
        day = START + timedelta(days=7 + position * span // len(docs))
        plan = plan_of[doc.doc_type]
        discipline = plan.discipline.get(doc.area, plan.discipline.get("*", "PIP"))
        with world.on(day):
            made = world.run(
                handle_register_document,
                RegisterDocument,
                by=ENGINEER,
                number=doc.number,
                title=doc.title,
                doc_type=doc.doc_type,
                discipline=discipline,
                originator=DESIGNER,
            )
        doc.id = made.stream_id
        revisions = rng.choice(REVISIONS)
        leave_draft = revisions > 1 and rng.random() < 0.12  # the last revision is still a draft
        for n in range(revisions):
            day = advance(day, rng, 3, 12)
            code = chr(ord("A") + n)
            last = n == revisions - 1
            status = "IFR" if n == 0 and revisions > 1 or rng.random() < 0.2 else "IFC"
            with world.on(day):
                rev = world.run(
                    handle_create_revision,
                    CreateRevision,
                    by=ENGINEER,
                    document_id=doc.id,
                    purpose="for review" if status == "IFR" else "for construction",
                    change_note=None
                    if n == 0
                    else f"Revision {code}: comments of {DESIGNER} incorporated",
                )
                pdf = make_pdf(
                    f"{doc.number} rev {code}",
                    [
                        doc.title,
                        "Project P200, North Refinery HT-2",
                        f"Issue status {status}",
                        f"Date {day.isoformat()}",
                    ],
                )
                uploaded = world.upload(
                    rev.stream_id,
                    slot="pdf",
                    filename=f"{doc.number}-{code}.pdf",
                    data=pdf,
                    by=ENGINEER,
                )
                world.run(
                    handle_attach_rendition,
                    AttachRendition,
                    by=ENGINEER,
                    revision_id=rev.stream_id,
                    file_id=uploaded.file_id,
                    page_count=1,
                )
                if last and leave_draft:
                    continue
                world.run(
                    handle_issue_revision,
                    IssueRevision,
                    by=CONTROLLER,
                    stream_id=rev.stream_id,
                    issue_status=status,
                )
            doc.issued.append(rev.stream_id)
    anchor_documents(world)
    supersede(world, rng, docs)
    transmit(world, rng, docs)


def anchor_revision(
    world: World,
    day: date,
    doc_id: str,
    number: str,
    title: str,
    code: str,
    sheets: int,
    note: str | None,
) -> str:
    """One issued (IFC) revision of an anchor P&ID, with its PDF rendition; returns its id."""
    with world.on(day):
        rev = world.run(
            handle_create_revision,
            CreateRevision,
            by=ENGINEER,
            document_id=doc_id,
            purpose="for construction",
            change_note=note,
        )
        pdf = make_pdf(
            f"{number} rev {code}",
            [
                title,
                "Project P200, North Refinery HT-2",
                f"Sheets {sheets}",
                f"Date {day.isoformat()}",
            ],
        )
        uploaded = world.upload(
            rev.stream_id, slot="pdf", filename=f"{number}-{code}.pdf", data=pdf, by=ENGINEER
        )
        world.run(
            handle_attach_rendition,
            AttachRendition,
            by=ENGINEER,
            revision_id=rev.stream_id,
            file_id=uploaded.file_id,
            page_count=sheets,
        )
        world.run(
            handle_issue_revision,
            IssueRevision,
            by=CONTROLLER,
            stream_id=rev.stream_id,
            issue_status="IFC",
        )
    return rev.stream_id


def anchor_documents(world: World) -> None:
    """The two fixed P&IDs (anchors.py).

    ``P200-200-PID-4701``: 3 sheets, restricted, one issued revision A. ``P200-200-PID-4702``:
    revisions A and B; issuing B supersedes A. Draws no random numbers, so the generated ones
    do not move.
    """
    restricted, revised = ANCHOR_DOCUMENTS
    title_4701 = "P&ID, reactor feed and effluent, process unit"
    title_4702 = "P&ID, fractionator overhead, process unit"
    day = START + timedelta(days=8)
    with world.on(day):
        made = world.run(
            handle_register_document,
            RegisterDocument,
            by=ENGINEER,
            number=restricted,
            title=title_4701,
            doc_type="PID",
            discipline="PIP",
            originator=DESIGNER,
            revision_scheme="alpha",  # revised A, B; the project default for P&IDs is numeric
        )
    anchor_revision(
        world, day + timedelta(days=1), made.stream_id, restricted, title_4701, "A", 3, None
    )
    # restricted last: a restricted record is hidden from the writer, so it is set after its work
    with world.on(day + timedelta(days=2)):
        world.run(
            handle_set_document_confidentiality,
            SetDocumentConfidentiality,
            by=CONTROLLER,
            stream_id=made.stream_id,
            confidentiality="restricted",
            reason="Reactor feed P&ID of the anchor set: restricted to the project team",
        )
    with world.on(day):
        made = world.run(
            handle_register_document,
            RegisterDocument,
            by=ENGINEER,
            number=revised,
            title=title_4702,
            doc_type="PID",
            discipline="PIP",
            originator=DESIGNER,
            revision_scheme="alpha",  # revised A, B; the project default for P&IDs is numeric
        )
    anchor_revision(
        world, day + timedelta(days=2), made.stream_id, revised, title_4702, "A", 1, None
    )
    anchor_revision(
        world,
        day + timedelta(days=9),
        made.stream_id,
        revised,
        title_4702,
        "B",
        1,
        f"Revision B: comments of {DESIGNER} incorporated",
    )


def supersede(world: World, rng: random.Random, docs: list[Doc]) -> None:
    """Eight documents are replaced by another document of the same type that is in force."""
    by_type: dict[str, list[Doc]] = {}
    for doc in docs:
        if doc.issued:
            by_type.setdefault(doc.doc_type, []).append(doc)
    for doc_type in ("PID", "PID", "ISO", "ISO", "ISO", "GA", "DS", "ISO"):
        pool = [d for d in by_type[doc_type] if not d.superseded]
        if len(pool) < 2:
            continue
        old, new = rng.sample(pool, 2)
        with world.on(TODAY - timedelta(days=rng.randint(2, 20))):
            world.run(
                handle_supersede_document,
                SupersedeDocument,
                by=CONTROLLER,
                stream_id=old.id,
                superseded_by_id=new.id,
                reason=f"Replaced by {new.number} after the design change of the area",
            )
        old.superseded = True
        by_type[doc_type] = [d for d in by_type[doc_type] if d is not old]


def transmit(world: World, rng: random.Random, docs: list[Doc]) -> None:
    """Six transmittals of issued revisions: one stays a draft, others sent, answered, closed."""
    carriable = [d for d in docs if d.issued and not d.superseded]
    for index in range(6):
        contractor = CONTRACTORS[index % len(CONTRACTORS)]
        picked = rng.sample(carriable, 5)
        day = TODAY - timedelta(days=45 - index * 7)
        with world.on(day):
            made = world.run(
                handle_create_transmittal,
                CreateTransmittal,
                by=CONTROLLER,
                subject=f"Drawings for {contractor[0]}, batch {index + 1}",
                purpose=TRANSMITTAL_PURPOSE[index % len(TRANSMITTAL_PURPOSE)],
                recipients=[
                    {"name": contractor[0], "organisation": contractor[1], "email": contractor[2]}
                ],
                revision_ids=[d.issued[-1] for d in picked],
                due_date=(day + timedelta(days=14)).isoformat(),
            )
            if index == 5:
                continue  # still a draft
            world.run(
                handle_issue_transmittal, IssueTransmittal, by=CONTROLLER, stream_id=made.stream_id
            )
        if index < 3:
            with world.on(day + timedelta(days=9)):
                world.run(
                    handle_record_transmittal_response,
                    RecordTransmittalResponse,
                    by=CONTROLLER,
                    stream_id=made.stream_id,
                    response_code=rng.choice(("approved", "approved_with_comments", "noted")),
                    response_note="Received and registered by the contractor",
                )
        if index < 2:
            with world.on(day + timedelta(days=12)):
                world.run(
                    handle_close_transmittal,
                    CloseTransmittal,
                    by=CONTROLLER,
                    stream_id=made.stream_id,
                )


register("documents", build)
