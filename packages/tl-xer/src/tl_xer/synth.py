"""Synthetic P6 schedules as XER bytes: for tests, the demo and the simulated planner (P1-I4).

Nothing here is a real project. ``Scenario`` is a small network of activities with progress at a
data date; ``schedule`` runs a forward and backward pass over a five-day working week (8 hours a
day, no holidays) and ``make_xer`` writes the file P6 would: ``ERMHDR``, ``PROJECT``, ``PROJWBS``,
``CALENDAR``, ``TASK``, ``TASKPRED``, activity codes, a user field, and two tables the snapshot is
not typed from (``RSRC``, ``OBS``) so the raw bundle has something verbatim to keep. The text is
Windows-1252, with an en dash in one name, as P6 writes it by default.

``week_pair()`` is the demo's pair of files, one week apart: the second has slips, float erosion,
one activity added and one removed, a changed relationship, percent complete moving and the
critical path moving. It is a pure function: the same call gives the same bytes (no clock, no
randomness). ``slipped`` derives a later file from a scenario for the simulated planner.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace
from datetime import date, timedelta

HOURS_PER_DAY = 8
START_TIME = "08:00"
FINISH_TIME = "16:00"
_ID_BASE = 1000  # task_id = base + position; PROJECT 1; calendar 1; WBS ids from 100


@dataclass(frozen=True)
class Spec:
    """One activity of the network, in whole working days."""

    code: str
    name: str
    wbs: str  # ENG, PROC or CON
    days: int  # original duration; 0 makes a milestone
    preds: tuple[str, ...] = ()


@dataclass(frozen=True)
class Progress:
    """What has happened to an activity at the data date."""

    start: date  # actual start
    percent: float = 0.0  # duration percent complete
    finish: date | None = None  # actual finish (the activity is complete)


@dataclass(frozen=True)
class Scenario:
    name: str  # P6 project short name
    data_date: date
    specs: tuple[Spec, ...]
    progress: dict[str, Progress] = field(default_factory=lambda: {})
    deadline: date = date(2026, 12, 3)  # the finish the late dates are computed back from
    project_start: date = date(2026, 8, 3)


@dataclass(frozen=True)
class Dates:
    es: date | None
    ef: date | None
    ls: date | None
    lf: date | None
    total_float_days: int | None
    free_float_days: int | None
    remaining_days: int


# --- working days --------------------------------------------------------------------------------


def _is_workday(day: date) -> bool:
    return day.weekday() < 5


def to_index(day: date) -> int:
    """Working-day number of ``day`` (the next working day when it is a weekend)."""
    while not _is_workday(day):
        day += timedelta(days=1)
    return (day - date(2026, 1, 5)).days // 7 * 5 + day.weekday()


def from_index(index: int) -> date:
    weeks, weekday = divmod(index, 5)
    return date(2026, 1, 5) + timedelta(days=weeks * 7 + weekday)


# --- the passes -----------------------------------------------------------------------------------


def _order(specs: tuple[Spec, ...]) -> list[Spec]:
    done: dict[str, Spec] = {}
    pending = list(specs)
    while pending:
        ready = [s for s in pending if all(p in done for p in s.preds)]
        if not ready:
            raise ValueError("the network has a loop or a predecessor that does not exist")
        for spec in ready:
            done[spec.code] = spec
            pending.remove(spec)
    return list(done.values())


def schedule(scenario: Scenario) -> dict[str, Dates]:
    """Early and late dates and floats of every activity at the scenario's data date."""
    order = _order(scenario.specs)
    dd = to_index(scenario.data_date)
    deadline = to_index(scenario.deadline)
    succs: dict[str, list[str]] = {s.code: [] for s in order}
    for spec in order:
        for pred in spec.preds:
            succs[pred].append(spec.code)
    es: dict[str, int] = {}
    ef: dict[str, int] = {}
    remaining: dict[str, int] = {}
    complete: set[str] = set()
    for spec in order:
        done = scenario.progress.get(spec.code)
        if done is not None and done.finish is not None:
            es[spec.code], ef[spec.code], remaining[spec.code] = (
                to_index(done.start),
                to_index(done.finish),
                0,
            )
            complete.add(spec.code)
        elif done is not None:
            left = max(1, round(spec.days * (1 - done.percent / 100)))
            es[spec.code], remaining[spec.code] = to_index(done.start), left
            ef[spec.code] = dd + left - 1
        else:
            start = max([dd, *(ef[p] + (0 if spec.days == 0 else 1) for p in spec.preds)])
            es[spec.code] = start
            remaining[spec.code] = spec.days
            ef[spec.code] = start + max(spec.days, 1) - 1 if spec.days else start
    ls: dict[str, int] = {}
    lf: dict[str, int] = {}
    for spec in reversed(order):
        if spec.code in complete:
            continue
        later = [ls[s] - (0 if _is_milestone(order, s) else 1) for s in succs[spec.code] if s in ls]
        lf[spec.code] = min(later) if later else deadline
        length = remaining[spec.code]
        ls[spec.code] = lf[spec.code] - max(length, 1) + 1 if length else lf[spec.code]
    result: dict[str, Dates] = {}
    for spec in order:
        code = spec.code
        if code in complete:
            result[code] = Dates(
                from_index(es[code]), from_index(ef[code]), None, None, None, None, 0
            )
            continue
        total = lf[code] - ef[code]
        gaps = [es[s] - ef[code] - (0 if _is_milestone(order, s) else 1) for s in succs[code]]
        result[code] = Dates(
            from_index(es[code]),
            from_index(ef[code]),
            from_index(ls[code]),
            from_index(lf[code]),
            total,
            min(gaps) if gaps else total,
            remaining[code],
        )
    return result


def _is_milestone(order: list[Spec], code: str) -> bool:
    return next(s for s in order if s.code == code).days == 0


# --- the XER text ---------------------------------------------------------------------------

_WBS = {"ROOT": 100, "ENG": 101, "PROC": 102, "CON": 103}
_WBS_NAMES = {
    "ROOT": ("DEMO", "Demo plant pipe rack"),
    "ENG": ("ENG", "Engineering"),
    "PROC": ("PROC", "Procurement"),
    "CON": ("CON", "Construction"),
}


def _stamp(day: date | None, time: str) -> str:
    return "" if day is None else f"{day.isoformat()} {time}"


def _status(spec: Spec, scenario: Scenario) -> str:
    done = scenario.progress.get(spec.code)
    if done is None:
        return "TK_NotStart"
    return "TK_Complete" if done.finish is not None else "TK_Active"


def make_xer(scenario: Scenario) -> bytes:
    """The XER file of ``scenario`` as P6 writes it (Windows-1252, CRLF)."""
    dates = schedule(scenario)
    order = list(scenario.specs)
    ids = {spec.code: _ID_BASE + n for n, spec in enumerate(order, 1)}
    out: list[str] = []

    def table(name: str, columns: list[str], rows: list[list[str]]) -> None:
        out.append(f"%T\t{name}")
        out.append("\t".join(["%F", *columns]))
        out.extend("\t".join(["%R", *row]) for row in rows)

    out.append(
        "\t".join(
            [
                "ERMHDR",
                "20.12",
                scenario.data_date.isoformat(),
                "Project",
                "planner",
                "Demo Planner",
                "DEMODB",
                "Project Management",
                "USD",
            ]  # fmt: skip
        )
    )
    table(
        "PROJECT",
        [
            "proj_id",
            "proj_short_name",
            "clndr_id",
            "last_recalc_date",
            "plan_start_date",
            "scd_end_date",
            "add_date",
        ],  # fmt: skip
        [
            [
                "1",
                scenario.name,
                "1",
                _stamp(scenario.data_date, START_TIME),
                _stamp(scenario.project_start, START_TIME),
                _stamp(scenario.deadline, FINISH_TIME),
                _stamp(scenario.project_start, START_TIME),
            ]
        ],  # fmt: skip
    )
    table(
        "CALENDAR",
        [
            "clndr_id",
            "clndr_name",
            "day_hr_cnt",
            "week_hr_cnt",
            "month_hr_cnt",
            "year_hr_cnt",
            "default_flag",
            "clndr_data",
        ],  # fmt: skip
        [
            ["1", "Five-day week", "8", "40", "172", "2000", "Y", "(0||CalendarData()())"],
            [
                "2",
                "Unused seven-day calendar",
                "8",
                "56",
                "240",
                "2920",
                "N",
                "(0||CalendarData()())",
            ],
        ],  # fmt: skip
    )
    wbs_rows = []
    for seq, key in enumerate(("ROOT", "ENG", "PROC", "CON"), 1):
        short, name = _WBS_NAMES[key]
        wbs_rows.append(
            [
                str(_WBS[key]),
                "1",
                str(seq * 10),
                "Y" if key == "ROOT" else "N",
                short,
                name,
                "" if key == "ROOT" else str(_WBS["ROOT"]),
            ]  # fmt: skip
        )
    table(
        "PROJWBS",
        [
            "wbs_id",
            "proj_id",
            "seq_num",
            "proj_node_flag",
            "wbs_short_name",
            "wbs_name",
            "parent_wbs_id",
        ],  # fmt: skip
        wbs_rows,
    )
    task_rows: list[list[str]] = []
    for spec in order:
        d = dates[spec.code]
        done = scenario.progress.get(spec.code)
        status = _status(spec, scenario)
        if spec.days == 0:
            kind = "TT_FinMile" if spec.preds else "TT_Mile"
        else:
            kind = "TT_Task"
        total = "" if d.total_float_days is None else str(d.total_float_days * HOURS_PER_DAY)
        free = "" if d.free_float_days is None else str(d.free_float_days * HOURS_PER_DAY)
        if status == "TK_Complete":
            phys = "100"
        else:
            phys = str(round(done.percent)) if done else "0"
        task_rows.append(
            [
                str(ids[spec.code]), "1", str(_WBS[spec.wbs]), "1", phys, "CP_Drtn", kind,
                "DT_FixedDrtn", status, spec.code, spec.name, total, free,
                str(spec.days * HOURS_PER_DAY), str(d.remaining_days * HOURS_PER_DAY),
                _stamp(d.es, START_TIME), _stamp(d.ef, FINISH_TIME),
                _stamp(d.ls, START_TIME), _stamp(d.lf, FINISH_TIME),
                _stamp(done.start, START_TIME) if done else "",
                _stamp(done.finish, FINISH_TIME) if done else "",
                _stamp(d.es, START_TIME), _stamp(d.ef, FINISH_TIME), "",
                "Y" if d.total_float_days == 0 else "N",
            ]
        )  # fmt: skip
    table(
        "TASK",
        ["task_id", "proj_id", "wbs_id", "clndr_id", "phys_complete_pct", "complete_pct_type",
         "task_type", "duration_type", "status_code", "task_code", "task_name",
         "total_float_hr_cnt", "free_float_hr_cnt", "target_drtn_hr_cnt", "remain_drtn_hr_cnt",
         "early_start_date", "early_end_date", "late_start_date", "late_end_date",
         "act_start_date", "act_end_date", "target_start_date", "target_end_date", "cstr_type",
         "driving_path_flag"],
        task_rows,
    )  # fmt: skip
    pred_rows = []
    for spec in order:
        for pred in spec.preds:
            pred_rows.append(
                [
                    str(len(pred_rows) + 1),
                    str(ids[spec.code]),
                    str(ids[pred]),
                    "1",
                    "1",
                    "PR_FS",
                    "0",
                ]
            )
    table(
        "TASKPRED",
        [
            "task_pred_id",
            "task_id",
            "pred_task_id",
            "proj_id",
            "pred_proj_id",
            "pred_type",
            "lag_hr_cnt",
        ],  # fmt: skip
        pred_rows,
    )
    table("ACTVTYPE", ["actv_code_type_id", "actv_code_type", "proj_id"], [["1", "Area", "1"]])
    table(
        "ACTVCODE",
        ["actv_code_id", "actv_code_type_id", "short_name", "actv_code_name"],
        [
            ["11", "1", "ENG", "Engineering"],
            ["12", "1", "PROC", "Procurement"],
            ["13", "1", "CON", "Construction"],
        ],  # fmt: skip
    )
    area = {"ENG": "11", "PROC": "12", "CON": "13"}
    table(
        "TASKACTV",
        ["task_id", "actv_code_type_id", "actv_code_id", "proj_id"],
        [[str(ids[s.code]), "1", area[s.wbs], "1"] for s in order],
    )
    table(
        "UDFTYPE",
        ["udf_type_id", "table_name", "udf_type_name", "udf_type_label", "logical_data_type"],
        [["501", "TASK", "user_field_1", "Contractor reference", "FT_TEXT"]],
    )
    table(
        "UDFVALUE",
        ["udf_type_id", "fk_id", "proj_id", "udf_text"],
        [["501", str(ids[s.code]), "1", f"CR-{s.code[1:]}"] for s in order if s.wbs == "CON"],
    )
    table(
        "RSRC",
        ["rsrc_id", "rsrc_short_name", "rsrc_name", "rsrc_type"],
        [["7", "WLD", "Pipe welder", "RT_Labor"], ["8", "CRN", "Crane \u2013 50 t", "RT_Equip"]],
    )
    table("OBS", ["obs_id", "obs_name", "parent_obs_id"], [["1", "Enterprise", ""]])
    out.append("%E")
    return ("\r\n".join(out) + "\r\n").encode("cp1252")


# --- the demo's pair of files ---------------------------------------------------------------


def _network() -> tuple[Spec, ...]:
    return (
        Spec("A1000", "Issue P&IDs IFC", "ENG", 10),
        Spec("A1010", "Issue piping isometrics IFC", "ENG", 15, ("A1000",)),
        Spec("A1020", "Issue civil foundations IFC", "ENG", 12, ("A1000",)),
        Spec("A1100", "Award valves purchase order", "PROC", 5, ("A1000",)),
        Spec("A1110", "Fabricate valves", "PROC", 60, ("A1100",)),
        Spec("A1120", "Deliver valves to site", "PROC", 5, ("A1110",)),
        Spec("A1130", "Award pipe spools purchase order", "PROC", 5, ("A1010",)),
        Spec("A1140", "Fabricate pipe spools", "PROC", 25, ("A1130",)),
        Spec("A1150", "Deliver pipe spools to site", "PROC", 5, ("A1140",)),
        Spec("A1200", "Mobilise site", "CON", 5),
        Spec("A1210", "Excavate foundations", "CON", 8, ("A1200", "A1020")),
        Spec("A1220", "Pour foundations", "CON", 6, ("A1210",)),
        Spec("A1230", "Install pipe rack supports", "CON", 10, ("A1220",)),
        Spec("A1240", "Erect pipe spools on rack", "CON", 15, ("A1230", "A1150")),
        Spec("A1250", "Install valves", "CON", 5, ("A1240", "A1120")),
        Spec("A1260", "Hydrotest – pipe rack lines", "CON", 4, ("A1250",)),
        Spec("A1270", "Punchlist and handover", "CON", 5, ("A1260",)),
        Spec("A1280", "Paint pipe rack", "CON", 8, ("A1240",)),
        Spec("A1290", "Insulate lines", "CON", 8, ("A1250",)),
        Spec("A1300", "Project complete", "CON", 0, ("A1270", "A1290")),
        Spec("A1990", "Temporary fencing", "CON", 20, ("A1200",)),
    )


def _d(month: int, day: int) -> date:
    return date(2026, month, day)


def week_pair() -> tuple[Scenario, Scenario]:
    """The scenarios of the demo's two files: data dates 2026-10-05 and 2026-10-12."""
    base = _network()
    progress_1 = {
        "A1000": Progress(_d(8, 3), 100, _d(8, 14)),
        "A1010": Progress(_d(8, 17), 100, _d(9, 4)),
        "A1020": Progress(_d(8, 17), 100, _d(9, 1)),
        "A1100": Progress(_d(8, 17), 100, _d(8, 21)),
        "A1110": Progress(_d(8, 24), 65),
        "A1130": Progress(_d(9, 7), 100, _d(9, 11)),
        "A1140": Progress(_d(9, 14), 60),
        "A1200": Progress(_d(8, 3), 100, _d(8, 7)),
        "A1210": Progress(_d(9, 2), 100, _d(9, 11)),
        "A1220": Progress(_d(9, 14), 100, _d(9, 23)),
        "A1230": Progress(_d(9, 24), 40),
        "A1990": Progress(_d(8, 10), 100, _d(9, 4)),
    }
    first = Scenario("DEMO-RACK", _d(10, 5), base, progress_1)
    # a week later: the valve fabrication and the pipe rack supports have stalled, the spools are
    # on plan, one activity is gone (A1990), one is new (A2500) and the insulation also waits for
    # the valves (a relationship added)
    network_2 = tuple(
        replace(s, preds=(*s.preds, "A1120")) if s.code == "A1290" else s
        for s in base
        if s.code != "A1990"
    ) + (Spec("A2500", "Weld inspection hold point", "CON", 3, ("A1230",)),)
    progress_2 = {k: v for k, v in progress_1.items() if k != "A1990"}
    progress_2["A1140"] = Progress(_d(9, 14), 80)
    second = Scenario("DEMO-RACK", _d(10, 12), network_2, progress_2)
    return first, second


def slipped(scenario: Scenario, *, days: int, codes: tuple[str, ...]) -> Scenario:
    """The scenario one week later with the activities ``codes`` lengthened by ``days``.

    For the simulated planner: each call moves the data date one week on, completes what the
    schedule says should be finished by then and lengthens the named activities.
    """
    moved = scenario.data_date + timedelta(days=7)
    specs = tuple(replace(s, days=s.days + days) if s.code in codes else s for s in scenario.specs)
    return replace(scenario, data_date=moved, specs=specs)


# --- a series of weekly updates -----------------------------------------------------------------

#: Weeks of a series are Mondays; the working week before a data date ends on this day earlier.
_LAST_WORKDAY_BEFORE = timedelta(days=3)


def _pick(seed: int, *parts: object) -> int:
    """A number from the seed and the parts: the same arguments give the same number, and nothing
    else does (a hash, not a random generator, so no state and no clock)."""
    text = ":".join(str(part) for part in (seed, *parts))
    return int.from_bytes(hashlib.sha256(text.encode()).digest()[:4], "big")


def next_week(scenario: Scenario, seed: int, week: int) -> Scenario:
    """The scenario one week on: work done, a few activities slipped, now and then one added.

    ``week`` counts the update (1 for the first after ``scenario``). The data date moves seven
    days. An activity in progress advances by the share of its duration a working week is, unless
    it slipped that week (it stalls and is lengthened by one to four days); one whose predecessors
    are complete starts on its early start; a milestone is reached when its predecessors are. One
    to three activities slip a week. Every third week an inspection of two to five days is added
    after an unfinished activity.
    """
    moved = scenario.data_date + timedelta(days=7)
    last_workday = moved - _LAST_WORKDAY_BEFORE
    early = schedule(scenario)
    open_codes = sorted(
        s.code
        for s in scenario.specs
        if s.days > 0 and not (scenario.progress.get(s.code) or Progress(moved)).finish
    )
    ranked = sorted(open_codes, key=lambda code: _pick(seed, week, "slip", code))
    slips = {
        code: 1 + _pick(seed, week, "by", code) % 4
        for code in ranked[: 1 + _pick(seed, week, "n") % 3]
    }
    progress = dict(scenario.progress)
    for spec in scenario.specs:
        done = progress.get(spec.code)
        if done is not None and done.finish is not None:
            continue
        if not all((progress.get(p) or Progress(moved)).finish for p in spec.preds):
            continue
        if spec.days == 0:
            reached = max(
                [early[spec.code].es or moved, *(progress[p].finish or moved for p in spec.preds)]
            )
            progress[spec.code] = Progress(reached, 100, reached)
            continue
        if spec.code in slips:
            continue  # it stalls: an activity due to start does not, one under way does not advance
        start = done.start if done is not None else early[spec.code].es
        if start is None or start >= moved:
            continue
        percent = (done.percent if done is not None else 0.0) + 100.0 * 5 / spec.days
        if percent >= 100:
            progress[spec.code] = Progress(start, 100, max(start, last_workday))
        else:
            progress[spec.code] = Progress(start, round(percent, 1))
    specs = tuple(
        replace(s, days=s.days + slips[s.code]) if s.code in slips else s for s in scenario.specs
    )
    if week % 3 == 0 and open_codes:
        after = open_codes[_pick(seed, week, "after") % len(open_codes)]
        extra = Spec(
            f"A25{week:02d}", f"Extra inspection {week}", "CON", 2 + _pick(seed, week, "len") % 4,
            (after,),
        )  # fmt: skip
        specs = (*specs, extra)
    return replace(scenario, data_date=moved, specs=specs, progress=progress)


def series(seed: int, weeks: int, *, start: Scenario | None = None) -> tuple[Scenario, ...]:
    """``weeks`` weekly updates of a schedule, the first being ``start`` (the demo's first file).

    A pure function of its arguments: the same seed gives the same files byte for byte, another
    seed gives other slips. Each file is a valid P6 export (``make_xer``), a week after the one
    before. ``ValueError`` for fewer than one week or more than 52.
    """
    if not 1 <= weeks <= 52:
        raise ValueError("a series has 1 to 52 weekly updates")
    scenarios = [start or week_pair()[0]]
    for week in range(1, weeks):
        scenarios.append(next_week(scenarios[-1], seed, week))
    return tuple(scenarios)
