#!/usr/bin/env python3
"""Make a realistic Primavera P6 XER schedule for the AC20-FZK-Haus sample model (a two-storey masonry house with a timber
roof), plus the 4D configuration that links it to the model.

Writes web/public/samples/fzk-haus.xer and web/public/samples/fzk-haus.4d.json.

Construction logic: site set-up and earthworks, below-ground drainage, ground slab (pour, then a curing lag before masonry),
ground-floor masonry (internal walls start while external walls go up), downstand beam, first-floor slab (props, pour, a
curing lag before the gable walls load it, props struck later), gable walls, roof carpentry (purlins and ridge, then
rafters, topping-out), roof deck and tiling, windows and external doors once the roof keeps the weather out, the
"weathertight" milestone that releases services first fix, plaster, screed and its 20-day drying (the classic critical
path of a house), stair and railings on the finished screed, finishes, second fix, external works in parallel, snagging,
inspection and handover. Activities without geometry in the model (services, plaster, render, drying) stay in the
schedule as they would in a real one; the 4D linker reports them as activities with no elements. The configuration marks them
`notModelled` (config.activities[code].notModelled), so the viewer lists them under "Not in the model" and the film names them
while they run instead of looking broken. A task counts as not modelled when its trade has no trade query.

The schedule is computed with a forward and backward pass on a Mon-Fri calendar with the Baden-Wuerttemberg public holidays
of 2027: target (baseline) dates from the plan, early/late dates and total float from the current schedule, where the
excavation ran two days over (rain) and the data date falls while the rafters go up.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from dataclasses import dataclass, field

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, '..', 'web', 'public', 'samples')

PROJECT_START = dt.date(2027, 3, 1)  # Monday
DATA_DATE = dt.date(2027, 5, 19)     # updated: rafters in progress
HOURS_PER_DAY = 8
HOLIDAYS = [dt.date(2027, 3, 26), dt.date(2027, 3, 29), dt.date(2027, 5, 6), dt.date(2027, 5, 17), dt.date(2027, 5, 27),
            dt.date(2027, 11, 1), dt.date(2027, 12, 24), dt.date(2027, 12, 27)]

# ---------------------------------------------------------------- activities
# code, name, wbs, type ('task' | 'start' | 'finish' milestone), duration (working days), level, trade, phase,
# predecessors [(code, 'FS'|'SS'|'FF', lag days)], crew size


@dataclass
class Act:
    code: str
    name: str
    wbs: str
    kind: str
    days: int
    level: str
    trade: str
    phase: str
    preds: list = field(default_factory=list)
    crew: int = 0
    actual_days: int | None = None  # actual duration when it differs from the plan


ACTS = [
    # milestones and preconstruction
    Act('A1000', 'Building permit approved', 'PRE', 'start', 0, 'SITE', 'GEN', 'PRE'),
    Act('A1010', 'Notice to proceed', 'PRE', 'start', 0, 'SITE', 'GEN', 'PRE', [('A1000', 'FS', 0)]),
    # substructure
    Act('A1100', 'Site set-up, hoarding and welfare', 'SUB', 'task', 3, 'SITE', 'SITE', 'SUB', [('A1010', 'FS', 0)], 3),
    Act('A1110', 'Survey and set-out', 'SUB', 'task', 1, 'SITE', 'SITE', 'SUB', [('A1100', 'FS', 0)], 2),
    Act('A1120', 'Topsoil strip and excavation', 'SUB', 'task', 4, 'SITE', 'EARTH', 'SUB', [('A1110', 'FS', 0)], 3, actual_days=6),
    Act('A1130', 'Below-ground drainage and service ducts', 'SUB', 'task', 3, 'SITE', 'DRAIN', 'SUB', [('A1120', 'FS', 0)], 3),
    Act('A1140', 'Sub-base, blinding and perimeter insulation', 'SUB', 'task', 2, 'EG', 'EARTH', 'SUB', [('A1130', 'FS', 0)], 3),
    Act('A1150', 'Ground slab: edge forms, DPM and reinforcement', 'SUB', 'task', 3, 'EG', 'CONC-PREP', 'SUB', [('A1140', 'FS', 0)], 4),
    Act('A1160', 'Pour ground slab', 'SUB', 'task', 1, 'EG', 'CONC-SLAB', 'SUB', [('A1150', 'FS', 0)], 6),
    # shell, ground floor
    Act('A1200', 'External masonry walls, ground floor', 'SHELL/EG', 'task', 8, 'EG', 'MASON-EXT', 'SHELL', [('A1160', 'FS', 3)], 4),
    Act('A1210', 'Internal masonry walls, ground floor', 'SHELL/EG', 'task', 5, 'EG', 'MASON-INT', 'SHELL', [('A1200', 'SS', 4), ('A1200', 'FF', 1)], 3),
    Act('A1220', 'Downstand beam and lintels', 'SHELL/EG', 'task', 2, 'EG', 'CONC-BEAM', 'SHELL', [('A1200', 'FS', 0), ('A1210', 'FS', 0)], 4),
    Act('A1230', 'First-floor slab: props, formwork and reinforcement', 'SHELL/DG', 'task', 5, 'DG', 'CONC-PREP', 'SHELL', [('A1220', 'FS', 0)], 4),
    Act('A1240', 'Pour first-floor slab', 'SHELL/DG', 'task', 1, 'DG', 'CONC-SLAB', 'SHELL', [('A1230', 'FS', 0)], 6),
    Act('A1250', 'Gable walls, attic', 'SHELL/DG', 'task', 5, 'DG', 'MASON-EXT', 'SHELL', [('A1240', 'FS', 5)], 4),
    Act('A1260', 'Strike props, first-floor slab', 'SHELL/DG', 'task', 1, 'EG', 'CONC-PREP', 'SHELL', [('A1240', 'FS', 10)], 2),
    # roof
    Act('A1300', 'Wall plates, purlins and ridge beam', 'ROOF', 'task', 3, 'DG', 'TIMBER-STRUCT', 'ROOF', [('A1250', 'FS', 0)], 3),
    Act('A1310', 'Rafters', 'ROOF', 'task', 4, 'DG', 'TIMBER-RAFTER', 'ROOF', [('A1300', 'FS', 0)], 3),
    Act('A1320', 'Topping-out (Richtfest)', 'ROOF', 'finish', 0, 'DG', 'GEN', 'ROOF', [('A1310', 'FS', 0)]),
    Act('A1330', 'Roof boarding, membrane and counter-battens', 'ROOF', 'task', 3, 'DG', 'ROOF-DECK', 'ROOF', [('A1310', 'FS', 0)], 3),
    Act('A1340', 'Roof tiling, flashings and gutters', 'ROOF', 'task', 6, 'DG', 'ROOFING', 'ROOF', [('A1330', 'SS', 2), ('A1330', 'FF', 1)], 3),
    # envelope
    Act('A1400', 'Windows, ground floor', 'ENV', 'task', 3, 'EG', 'WINDOWS', 'ENV', [('A1220', 'FS', 0), ('A1330', 'FS', 0)], 2),
    Act('A1410', 'Windows, attic', 'ENV', 'task', 1, 'DG', 'WINDOWS', 'ENV', [('A1250', 'FS', 0), ('A1330', 'FS', 0)], 2),
    Act('A1420', 'External doors', 'ENV', 'task', 1, 'EG', 'DOORS-EXT', 'ENV', [('A1400', 'FS', 0)], 2),
    Act('A1430', 'Building weathertight', 'ENV', 'finish', 0, 'ALL', 'GEN', 'ENV', [('A1340', 'FS', 0), ('A1410', 'FS', 0), ('A1420', 'FS', 0)]),
    Act('A1440', 'External insulation and render (ETICS)', 'ENV', 'task', 10, 'ALL', 'FACADE', 'ENV', [('A1420', 'FS', 0), ('A1340', 'SS', 3)], 3),
    Act('A1450', 'Strike scaffold', 'ENV', 'task', 1, 'ALL', 'SITE', 'ENV', [('A1440', 'FS', 0)], 3),
    # services first fix
    Act('A1500', 'Electrical first fix', 'MEP', 'task', 5, 'ALL', 'MEP-ELEC', 'MEP', [('A1430', 'FS', 0)], 2),
    Act('A1510', 'Plumbing and drainage first fix', 'MEP', 'task', 4, 'ALL', 'MEP-PLUMB', 'MEP', [('A1430', 'SS', 1)], 2),
    Act('A1520', 'Underfloor heating and manifold', 'MEP', 'task', 3, 'EG', 'MEP-HVAC', 'MEP', [('A1510', 'FS', 0), ('A1260', 'FS', 0)], 2),
    # fit-out
    Act('A1600', 'Internal plaster, ground floor', 'FIT/EG', 'task', 5, 'EG', 'FINISH', 'FIT', [('A1500', 'FS', 0), ('A1510', 'FS', 0), ('A1260', 'FS', 0)], 3),
    Act('A1610', 'Internal plaster, attic', 'FIT/DG', 'task', 4, 'DG', 'FINISH', 'FIT', [('A1600', 'SS', 2)], 3),
    Act('A1620', 'Floor screed, ground floor', 'FIT/EG', 'task', 2, 'EG', 'SCREED', 'FIT', [('A1520', 'FS', 0), ('A1600', 'FS', 0)], 3),
    Act('A1630', 'Floor screed, attic', 'FIT/DG', 'task', 1, 'DG', 'SCREED', 'FIT', [('A1610', 'FS', 0), ('A1620', 'SS', 1)], 3),
    Act('A1640', 'Screed drying and moisture test', 'FIT', 'task', 20, 'ALL', 'GEN', 'FIT', [('A1630', 'FS', 0)], 0),
    Act('A1650', 'Spiral stair', 'FIT/EG', 'task', 2, 'EG', 'STAIRS', 'FIT', [('A1630', 'FS', 3)], 2),
    Act('A1655', 'Balustrades and railings, attic', 'FIT/DG', 'task', 1, 'DG', 'RAILINGS', 'FIT', [('A1650', 'FS', 0)], 2),
    Act('A1660', 'Internal doors', 'FIT/EG', 'task', 2, 'EG', 'DOORS-INT', 'FIT', [('A1640', 'FS', 0)], 2),
    Act('A1670', 'Floor finishes', 'FIT', 'task', 5, 'ALL', 'FINISH', 'FIT', [('A1640', 'FS', 0)], 2),
    Act('A1680', 'Painting and decorating', 'FIT', 'task', 6, 'ALL', 'FINISH', 'FIT', [('A1670', 'SS', 2), ('A1660', 'FS', 0)], 2),
    Act('A1690', 'Electrical and plumbing second fix', 'MEP', 'task', 4, 'ALL', 'MEP-ELEC', 'MEP', [('A1680', 'SS', 3)], 2),
    Act('A1695', 'Kitchen and sanitaryware', 'FIT', 'task', 3, 'ALL', 'FINISH', 'FIT', [('A1670', 'FS', 0), ('A1690', 'SS', 1)], 2),
    # external works
    Act('A1700', 'Drive, paths and landscaping', 'EXT', 'task', 6, 'SITE', 'LANDSCAPE', 'EXT', [('A1450', 'FS', 0)], 3),
    # handover
    Act('A1800', 'Commissioning and snagging', 'HO', 'task', 3, 'ALL', 'GEN', 'HO', [('A1690', 'FS', 0), ('A1695', 'FS', 0), ('A1655', 'FS', 0), ('A1680', 'FS', 0)], 2),
    Act('A1810', 'Final inspection', 'HO', 'finish', 0, 'ALL', 'GEN', 'HO', [('A1800', 'FS', 0), ('A1700', 'FS', 0)]),
    Act('A1820', 'Handover', 'HO', 'finish', 0, 'ALL', 'GEN', 'HO', [('A1810', 'FS', 0)]),
]

WBS = [  # short name, name, parent short name
    ('FZK', 'FZK-Haus single-family house', None),
    ('PRE', 'Preconstruction', 'FZK'),
    ('SUB', 'Substructure', 'FZK'),
    ('SHELL', 'Shell', 'FZK'),
    ('SHELL/EG', 'Ground floor (Erdgeschoss)', 'SHELL'),
    ('SHELL/DG', 'Attic (Dachgeschoss)', 'SHELL'),
    ('ROOF', 'Roof', 'FZK'),
    ('ENV', 'Envelope', 'FZK'),
    ('MEP', 'Building services', 'FZK'),
    ('FIT', 'Fit-out', 'FZK'),
    ('FIT/EG', 'Fit-out ground floor', 'FIT'),
    ('FIT/DG', 'Fit-out attic', 'FIT'),
    ('EXT', 'External works', 'FZK'),
    ('HO', 'Handover', 'FZK'),
]

CODE_TYPES = {
    'Level': {'SITE': 'Site', 'EG': 'Ground floor (Erdgeschoss)', 'DG': 'Attic (Dachgeschoss)', 'ALL': 'Whole building'},
    'Trade': {
        'GEN': 'General / milestones', 'SITE': 'Site set-up', 'EARTH': 'Earthworks', 'DRAIN': 'Below-ground drainage',
        'CONC-PREP': 'Concrete: formwork and reinforcement', 'CONC-SLAB': 'Concrete: slabs', 'CONC-BEAM': 'Concrete: beams and lintels',
        'MASON-EXT': 'Masonry: external walls', 'MASON-INT': 'Masonry: internal walls', 'TIMBER-STRUCT': 'Carpentry: purlins and ridge',
        'TIMBER-RAFTER': 'Carpentry: rafters', 'ROOF-DECK': 'Roof deck', 'ROOFING': 'Roof tiling', 'WINDOWS': 'Windows',
        'DOORS-EXT': 'External doors', 'DOORS-INT': 'Internal doors', 'FACADE': 'Facade: insulation and render',
        'MEP-ELEC': 'Electrical', 'MEP-PLUMB': 'Plumbing', 'MEP-HVAC': 'Heating', 'FINISH': 'Finishes', 'SCREED': 'Screed',
        'STAIRS': 'Stairs', 'RAILINGS': 'Railings and balustrades', 'LANDSCAPE': 'External works',
    },
    'Phase': {'PRE': 'Preconstruction', 'SUB': 'Substructure', 'SHELL': 'Shell', 'ROOF': 'Roof', 'ENV': 'Envelope',
              'MEP': 'Services', 'FIT': 'Fit-out', 'EXT': 'External works', 'HO': 'Handover'},
}

# The elements each trade builds, as criteria queries; the level code picks the storey (Erdgeschoss / Dachgeschoss).
TRADE_QUERIES = {
    'CONC-SLAB': "class = 'IfcSlab' and name in ('Bodenplatte', 'Slab-033')",
    'CONC-BEAM': "class = 'IfcBeam' and name like 'Unterzug%'",
    'MASON-EXT': "class = 'IfcWallStandardCase' and name like 'Wand-Ext%'",
    'MASON-INT': "class = 'IfcWallStandardCase' and name like 'Wand-Int%'",
    'TIMBER-STRUCT': "class = 'IfcBeam' and (name like 'Pfette%' or name = 'First')",
    'TIMBER-RAFTER': "class = 'IfcMember' and name like 'Sparren%'",
    'ROOF-DECK': "class = 'IfcSlab' and name like 'Dach%'",
    'WINDOWS': "class = 'IfcWindow'",
    'DOORS-EXT': "class = 'IfcDoor' and name in ('Haustuer', 'Terrassentuer')",
    'DOORS-INT': "class = 'IfcDoor' and name like 'Innentuer%'",
    'STAIRS': "class = 'IfcStair'",
    'RAILINGS': "class = 'IfcRailing'",
}
TRADE_COLOURS = {
    'CONC-SLAB': '#9aa5b1', 'CONC-BEAM': '#7f8c99', 'MASON-EXT': '#d9824a', 'MASON-INT': '#e3a671', 'TIMBER-STRUCT': '#a0703c',
    'TIMBER-RAFTER': '#c08a4a', 'ROOF-DECK': '#6b4f3a', 'WINDOWS': '#4aa3df', 'DOORS-EXT': '#2f7fb5', 'DOORS-INT': '#79b8e0',
    'STAIRS': '#8e6bbf', 'RAILINGS': '#b39ddb',
}
SPLITS = {'MASON-EXT': 'sweep_x', 'MASON-INT': 'sweep_x', 'TIMBER-RAFTER': 'sweep_x', 'WINDOWS': 'sweep_x', '*': 'none'}

UDF_RESPONSIBLE = {  # fictional companies
    'SITE': 'Main contractor', 'EARTH': 'Erdbau Neckar GmbH', 'DRAIN': 'Erdbau Neckar GmbH', 'CONC-PREP': 'Rohbau Kraus GmbH',
    'CONC-SLAB': 'Rohbau Kraus GmbH', 'CONC-BEAM': 'Rohbau Kraus GmbH', 'MASON-EXT': 'Rohbau Kraus GmbH', 'MASON-INT': 'Rohbau Kraus GmbH',
    'TIMBER-STRUCT': 'Zimmerei Holzwerk', 'TIMBER-RAFTER': 'Zimmerei Holzwerk', 'ROOF-DECK': 'Zimmerei Holzwerk', 'ROOFING': 'Dachdecker Ziegel & Co',
    'WINDOWS': 'Fensterbau Lichtblick', 'DOORS-EXT': 'Fensterbau Lichtblick', 'DOORS-INT': 'Schreinerei Eiche', 'FACADE': 'Putz & Fassade AG',
    'MEP-ELEC': 'Elektro Funke', 'MEP-PLUMB': 'Sanitaer Quelle', 'MEP-HVAC': 'Sanitaer Quelle', 'FINISH': 'Ausbau Maler Bunt',
    'SCREED': 'Estrich Glatt', 'STAIRS': 'Metallbau Spirale', 'RAILINGS': 'Metallbau Spirale', 'LANDSCAPE': 'Garten Gruen', 'GEN': 'Main contractor',
}

# ---------------------------------------------------------------- calendar


def is_work(d: dt.date) -> bool:
    return d.weekday() < 5 and d not in HOLIDAYS


def next_work(d: dt.date) -> dt.date:
    while not is_work(d):
        d += dt.timedelta(days=1)
    return d


def add_work(d: dt.date, n: int) -> dt.date:
    """The working day n working days after working day d (n may be negative)."""
    step = 1 if n >= 0 else -1
    d = next_work(d) if step > 0 else d
    for _ in range(abs(n)):
        d += dt.timedelta(days=step)
        while not is_work(d):
            d += dt.timedelta(days=step)
    return d


def wdays_between(a: dt.date, b: dt.date) -> int:
    """Working days from a to b (b exclusive, a < b)."""
    n, d = 0, a
    while d < b:
        if is_work(d):
            n += 1
        d += dt.timedelta(days=1)
    return n

# ---------------------------------------------------------------- CPM (day granularity: an activity occupies days [s, f])


def forward(acts, durations, fixed=None, not_before=None):
    """Early start/finish as (start day, finish day) inclusive; milestones have s == f (start of that day for start
    milestones, end of that day for finish milestones). fixed: code -> (s, f) for completed work; not_before: earliest day."""
    by = {a.code: a for a in acts}
    es, ef = {}, {}
    for a in acts:  # ACTS are listed in a valid topological order
        if fixed and a.code in fixed:
            es[a.code], ef[a.code] = fixed[a.code]
            continue
        dur = durations[a.code]
        start = PROJECT_START
        for p, typ, lag in a.preds:
            pk = by[p]
            if typ == 'FS':
                # the day after the predecessor's finish (a start milestone finishes at the start of its day); a finish
                # milestone falls at the end of its predecessor's last day
                if a.kind == 'finish' and pk.kind != 'start':
                    cand = add_work(ef[p], lag)
                else:
                    base = es[p] if pk.kind == 'start' else add_work(ef[p], 1)
                    cand = add_work(base, lag)
            elif typ == 'SS':
                cand = add_work(es[p], lag)
            else:  # FF: finish no earlier than pred finish + lag
                fin = add_work(ef[p], lag)
                cand = add_work(fin, -(dur - 1)) if dur > 0 else fin
            start = max(start, cand)
        if not_before and a.code not in (fixed or {}):
            start = max(start, not_before)
        start = next_work(start)
        es[a.code] = start
        ef[a.code] = start if dur == 0 else add_work(start, dur - 1)
    return es, ef


def backward(acts, durations, es, ef, finish):
    by = {a.code: a for a in acts}
    succ = {a.code: [] for a in acts}
    for a in acts:
        for p, typ, lag in a.preds:
            succ[p].append((a.code, typ, lag))
    ls, lf = {}, {}
    for a in reversed(acts):
        dur = durations[a.code]
        latest_f = finish
        for s, typ, lag in succ[a.code]:
            if typ == 'FS':
                base = add_work(ls[s], -lag)
                cand = base if (a.kind == 'start' or by[s].kind == 'finish') else add_work(base, -1)
            elif typ == 'SS':
                cand_start = add_work(ls[s], -lag)
                cand = cand_start if dur == 0 else add_work(cand_start, dur - 1)
            else:
                cand = add_work(lf[s], -lag)
            latest_f = min(latest_f, cand)
        lf[a.code] = latest_f
        ls[a.code] = latest_f if dur == 0 else add_work(latest_f, -(dur - 1))
    return ls, lf

# ---------------------------------------------------------------- XER writing


def xer_dt(d: dt.date, end: bool) -> str:
    return f"{d.isoformat()} {'17:00' if end else '08:00'}"


def serial(d: dt.date) -> int:
    return (d - dt.date(1899, 12, 30)).days


def calendar_data() -> str:
    days = []
    for i in range(1, 8):  # 1 = Sunday .. 7 = Saturday
        if i in (1, 7):
            days.append(f'(0||{i}()())')
        else:
            days.append(f'(0||{i}()( (0||0(s|08:00|f|12:00)()) (0||1(s|13:00|f|17:00)())))')
    exc = ' '.join(f'(0||{k}(d|{serial(h)})())' for k, h in enumerate(HOLIDAYS))
    return f"(0||CalendarData()( (0||DaysOfWeek()( {' '.join(days)})) (0||VIEW(ShowTotal|Y)()) (0||Exceptions()( {exc}))))"


def table(name, fields, rows):
    out = [f'%T\t{name}', '%F\t' + '\t'.join(fields)]
    for r in rows:
        out.append('%R\t' + '\t'.join('' if r.get(f) is None else str(r.get(f)) for f in fields))
    return out


def main() -> None:
    plan_d = {a.code: a.days for a in ACTS}
    t_es, t_ef = forward(ACTS, plan_d)  # baseline

    # current schedule: completed work keeps its actual dates; the rest is scheduled from the data date
    act_d = {a.code: (a.actual_days if a.actual_days is not None else a.days) for a in ACTS}
    a_es, a_ef = forward(ACTS, act_d)  # what really happened up to the data date
    fixed, status, actual, pct, remain = {}, {}, {}, {}, {}
    for a in ACTS:
        s, f = a_es[a.code], a_ef[a.code]
        if f < DATA_DATE and (a.kind != 'finish' or f < DATA_DATE):
            fixed[a.code] = (s, f)
            status[a.code], actual[a.code], pct[a.code], remain[a.code] = 'TK_Complete', (s, f), 100, 0
        elif s < DATA_DATE <= f and a.days > 0:
            done = wdays_between(s, DATA_DATE)
            status[a.code], actual[a.code] = 'TK_Active', (s, None)
            pct[a.code] = round(100 * done / act_d[a.code])
            remain[a.code] = act_d[a.code] - done
        else:
            status[a.code], actual[a.code], pct[a.code], remain[a.code] = 'TK_NotStart', (None, None), 0, act_d[a.code]

    # in-progress work: started on its actual start, remaining duration from the data date
    cur_fixed = dict(fixed)
    for a in ACTS:
        if status[a.code] == 'TK_Active':
            s = actual[a.code][0]
            cur_fixed[a.code] = (s, add_work(DATA_DATE, remain[a.code] - 1))
    e_es, e_ef = forward(ACTS, act_d, fixed=cur_fixed, not_before=DATA_DATE)
    finish = max(e_ef.values())
    l_es, l_ef = backward(ACTS, act_d, e_es, e_ef, finish)

    proj_id, clndr_id = 4711, 1001
    wbs_ids = {short: 2000 + i for i, (short, _, _) in enumerate(WBS)}
    lines = [f'ERMHDR\t19.12\t{DATA_DATE.isoformat()}\tProject\tplanner\tPMDB\tProject Management\tEUR']
    lines += table('CURRTYPE', ['curr_id', 'decimal_digit_cnt', 'curr_symbol', 'curr_short_name', 'curr_type'],
                   [{'curr_id': 1, 'decimal_digit_cnt': 2, 'curr_symbol': 'EUR', 'curr_short_name': 'EUR', 'curr_type': 'Euro'}])
    lines += table('PROJECT', ['proj_id', 'proj_short_name', 'clndr_id', 'plan_start_date', 'scd_end_date', 'last_recalc_date', 'def_duration_type', 'task_code_base', 'task_code_step'],
                   [{'proj_id': proj_id, 'proj_short_name': 'FZK-HAUS', 'clndr_id': clndr_id, 'plan_start_date': xer_dt(PROJECT_START, False),
                     'scd_end_date': xer_dt(finish, True), 'last_recalc_date': xer_dt(DATA_DATE, False), 'def_duration_type': 'DT_FixedDrtn',
                     'task_code_base': 1000, 'task_code_step': 10}])
    lines += table('CALENDAR', ['clndr_id', 'default_flag', 'clndr_name', 'proj_id', 'base_clndr_id', 'last_chng_date', 'clndr_type', 'day_hr_cnt', 'week_hr_cnt', 'month_hr_cnt', 'year_hr_cnt', 'clndr_data'],
                   [{'clndr_id': clndr_id, 'default_flag': 'Y', 'clndr_name': 'Mon-Fri 8h, BW holidays 2027', 'proj_id': proj_id, 'clndr_type': 'CA_Project',
                     'day_hr_cnt': HOURS_PER_DAY, 'week_hr_cnt': 40, 'month_hr_cnt': 172, 'year_hr_cnt': 2000, 'clndr_data': calendar_data()}])
    wbs_rows = [{'wbs_id': 1999, 'proj_id': proj_id, 'obs_id': 1, 'seq_num': 0, 'proj_node_flag': 'Y', 'status_code': 'WS_Open',
                 'wbs_short_name': 'FZK-HAUS', 'wbs_name': 'FZK-Haus', 'parent_wbs_id': ''}]
    for i, (short, name, parent) in enumerate(WBS):
        wbs_rows.append({'wbs_id': wbs_ids[short], 'proj_id': proj_id, 'obs_id': 1, 'seq_num': i + 1, 'proj_node_flag': 'N', 'status_code': 'WS_Open',
                         'wbs_short_name': short.split('/')[-1], 'wbs_name': name, 'parent_wbs_id': wbs_ids[parent] if parent else 1999})
    lines += table('PROJWBS', ['wbs_id', 'proj_id', 'obs_id', 'seq_num', 'proj_node_flag', 'status_code', 'wbs_short_name', 'wbs_name', 'parent_wbs_id'], wbs_rows)

    type_ids = {t: 3000 + i for i, t in enumerate(CODE_TYPES)}
    lines += table('ACTVTYPE', ['actv_code_type_id', 'actv_short_len', 'seq_num', 'actv_code_type', 'proj_id', 'actv_code_type_scope'],
                   [{'actv_code_type_id': type_ids[t], 'actv_short_len': 20, 'seq_num': i, 'actv_code_type': t, 'proj_id': proj_id, 'actv_code_type_scope': 'AS_Project'}
                    for i, t in enumerate(CODE_TYPES)])
    code_ids, code_rows = {}, []
    n = 4000
    for t, values in CODE_TYPES.items():
        for j, (short, long) in enumerate(values.items()):
            code_ids[(t, short)] = n
            code_rows.append({'actv_code_id': n, 'parent_actv_code_id': '', 'actv_code_type_id': type_ids[t], 'actv_code_name': long, 'short_name': short, 'seq_num': j})
            n += 1
    lines += table('ACTVCODE', ['actv_code_id', 'parent_actv_code_id', 'actv_code_type_id', 'actv_code_name', 'short_name', 'seq_num'], code_rows)
    lines += table('UDFTYPE', ['udf_type_id', 'table_name', 'udf_type_name', 'udf_type_label', 'logical_data_type'],
                   [{'udf_type_id': 5001, 'table_name': 'TASK', 'udf_type_name': 'user_field_1', 'udf_type_label': 'Crew size', 'logical_data_type': 'FT_INT'},
                    {'udf_type_id': 5002, 'table_name': 'TASK', 'udf_type_name': 'user_field_2', 'udf_type_label': 'Responsible', 'logical_data_type': 'FT_TEXT'}])

    task_ids = {a.code: 10000 + i for i, a in enumerate(ACTS)}
    task_fields = ['task_id', 'proj_id', 'wbs_id', 'clndr_id', 'phys_complete_pct', 'rev_fdbk_flag', 'complete_pct_type', 'task_type', 'duration_type',
                   'status_code', 'task_code', 'task_name', 'total_float_hr_cnt', 'free_float_hr_cnt', 'remain_drtn_hr_cnt', 'target_drtn_hr_cnt',
                   'act_start_date', 'act_end_date', 'restart_date', 'reend_date', 'target_start_date', 'target_end_date',
                   'early_start_date', 'early_end_date', 'late_start_date', 'late_end_date', 'driving_path_flag', 'create_date', 'update_date']
    task_rows = []
    for a in ACTS:
        c = a.code
        ttype = {'task': 'TT_Task', 'start': 'TT_Mile', 'finish': 'TT_FinMile'}[a.kind]
        mil_end = a.kind == 'finish'
        def dts(s, f):
            if a.kind == 'start':
                return xer_dt(s, False), xer_dt(s, False)
            if a.kind == 'finish':
                return xer_dt(f, True), xer_dt(f, True)
            return xer_dt(s, False), xer_dt(f, True)
        ts, te = dts(t_es[c], t_ef[c])
        es_, ee_ = dts(e_es[c], e_ef[c])
        ls_, le_ = dts(l_es[c], l_ef[c])
        float_days = wdays_between(e_ef[c], l_ef[c]) if l_ef[c] > e_ef[c] else 0
        st = status[c]
        acs, ace = actual[c]
        row = {
            'task_id': task_ids[c], 'proj_id': proj_id, 'wbs_id': wbs_ids[a.wbs], 'clndr_id': clndr_id, 'phys_complete_pct': pct[c],
            'rev_fdbk_flag': 'N', 'complete_pct_type': 'CP_Phys', 'task_type': ttype, 'duration_type': 'DT_FixedDrtn', 'status_code': st,
            'task_code': c, 'task_name': a.name, 'total_float_hr_cnt': float_days * HOURS_PER_DAY, 'free_float_hr_cnt': '',
            'remain_drtn_hr_cnt': remain[c] * HOURS_PER_DAY, 'target_drtn_hr_cnt': a.days * HOURS_PER_DAY,
            'act_start_date': (xer_dt(acs, mil_end) if acs else ''), 'act_end_date': (xer_dt(ace, a.kind != 'start') if ace else ''),
            'restart_date': (xer_dt(DATA_DATE, False) if st == 'TK_Active' else (es_ if st == 'TK_NotStart' else '')),
            'reend_date': (ee_ if st != 'TK_Complete' else ''),
            'target_start_date': ts, 'target_end_date': te, 'early_start_date': es_, 'early_end_date': ee_,
            'late_start_date': ls_, 'late_end_date': le_, 'driving_path_flag': 'Y' if float_days == 0 and st != 'TK_Complete' else 'N',
            'create_date': '2027-01-15 09:00', 'update_date': xer_dt(DATA_DATE, False),
        }
        task_rows.append(row)
    lines += table('TASK', task_fields, task_rows)

    pred_rows, k = [], 20000
    for a in ACTS:
        for p, typ, lag in a.preds:
            pred_rows.append({'task_pred_id': k, 'task_id': task_ids[a.code], 'pred_task_id': task_ids[p], 'proj_id': proj_id, 'pred_proj_id': proj_id,
                              'pred_type': f'PR_{typ}', 'lag_hr_cnt': lag * HOURS_PER_DAY})
            k += 1
    lines += table('TASKPRED', ['task_pred_id', 'task_id', 'pred_task_id', 'proj_id', 'pred_proj_id', 'pred_type', 'lag_hr_cnt'], pred_rows)
    lines += table('TASKACTV', ['task_id', 'actv_code_type_id', 'actv_code_id', 'proj_id'],
                   [{'task_id': task_ids[a.code], 'actv_code_type_id': type_ids[t], 'actv_code_id': code_ids[(t, v)], 'proj_id': proj_id}
                    for a in ACTS for t, v in (('Level', a.level), ('Trade', a.trade), ('Phase', a.phase))])
    udf_rows = []
    for a in ACTS:
        if a.crew:
            udf_rows.append({'udf_type_id': 5001, 'fk_id': task_ids[a.code], 'proj_id': proj_id, 'udf_number': a.crew, 'udf_text': ''})
        udf_rows.append({'udf_type_id': 5002, 'fk_id': task_ids[a.code], 'proj_id': proj_id, 'udf_number': '', 'udf_text': UDF_RESPONSIBLE.get(a.trade, 'Main contractor')})
    lines += table('UDFVALUE', ['udf_type_id', 'fk_id', 'proj_id', 'udf_number', 'udf_text'], udf_rows)
    lines.append('%E')

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, 'fzk-haus.xer'), 'w', encoding='cp1252', newline='\r\n') as f:
        f.write('\n'.join(lines) + '\n')

    config = {
        'schema': 'xray-4d-config/1',
        'schedule': {'project': 'FZK-HAUS', 'location': [{'code': 'Level'}], 'trade': [{'code': 'Trade'}]},
        'model': {'location': [{'property': 'Xray_4D.Location'}, {'storey': True}], 'trade': [{'property': 'Xray_4D.Trade'}]},
        'values': {'location': {'EG': 'Erdgeschoss', 'DG': 'Dachgeschoss'}},
        'tradeQueries': TRADE_QUERIES,
        'activities': {a.code: {'notModelled': True} for a in ACTS if a.kind == 'task' and a.trade not in TRADE_QUERIES},
        'split': SPLITS,
        'style': {
            'view': 'planned', 'unbuilt': 'hidden', 'window': {'kind': 'all'}, 'length': 90, 'pace': 'warp', 'camera': 'director',
            'explode': 'auto', 'xrayFocus': True, 'sectionBox': 'auto', 'labels': 3, 'criticalFloatHours': 0, 'colours': TRADE_COLOURS,
            'captions': True, 'milestoneHold': 1.5,
        },
    }
    with open(os.path.join(OUT_DIR, 'fzk-haus.4d.json'), 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2)
        f.write('\n')

    crit = [a.code for a in ACTS if task_rows[[r['task_code'] for r in task_rows].index(a.code)]['driving_path_flag'] == 'Y']
    print(f'{len(ACTS)} activities, {len(pred_rows)} relationships; baseline finish {max(t_ef.values())}, current finish {finish}; data date {DATA_DATE}')
    print('critical (remaining):', ' '.join(crit))
    print('status:', {s: sum(1 for v in status.values() if v == s) for s in ('TK_Complete', 'TK_Active', 'TK_NotStart')})


if __name__ == '__main__':
    main()
